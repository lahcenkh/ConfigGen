"""Template editor (§13.4 Template Engineer flow) — create/edit schema +
template source, Check (structural + StrictUndefined variable check),
Extract Variables, Test Render, Version History (diff/restore),
publish/unpublish/deprecate, and (Admin only) delete.

Every button here calls the same core functions the CLI's `configgen
check` / `--scaffold` / `history` commands use — this module only adds
the editing surface (raw text + syntax highlighting) around them.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from pathlib import Path

import yaml
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from configgen.core.auth import ROLE_ADMIN, AuthStore, User
from configgen.core.configpack import export_config_pack
from configgen.core.db import DatabaseError, database_for_schema
from configgen.core.extractor import classify_variables, extract_variables_from_file
from configgen.core.registry import load_project_filters
from configgen.core.renderer import RenderError, render_documents
from configgen.core.schema import (
    Schema,
    find_schema_files,
    load_schema,
    project_dirs_for,
    project_history_dir_for,
    project_root_for,
    schema_from_dict,
)
from configgen.core.schema_validator import SchemaValidationError, validate_schema
from configgen.core.versioning import (
    VersioningError,
    diff_versions,
    list_versions,
    restore_version,
    save_version,
)
from configgen.hooks import HookError, run_hook, services_for_schema
from configgen.ui import theme
from configgen.ui.form_builder import FormBuilder
from configgen.ui.highlighters import ConfigHighlighter, JinjaHighlighter, YamlHighlighter
from configgen.ui.widgets import StatusBadge

logger = logging.getLogger(__name__)

_STATUS_RE = re.compile(r"(?m)^status:\s*\w+")
_NAME_RE = re.compile(r"(?m)^name:\s*.*$")

_NEW_SCHEMA_TEMPLATE = """name: {name}
id: {id}
version: 1
status: draft
identity_field: name
template: {id}.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""

_NEW_TEMPLATE_STUB = "# {{ name }}\n"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_") or "schema"


def _set_status_line(text: str, new_status: str) -> str:
    new_text, count = _STATUS_RE.subn(f"status: {new_status}", text, count=1)
    if count == 0:
        # No status line yet (defaults to draft) — add one after the id line.
        new_text = text.rstrip("\n") + f"\nstatus: {new_status}\n"
    return new_text


def _set_name_line(text: str, new_name: str) -> str:
    # json.dumps produces a properly escaped double-quoted YAML scalar —
    # safe even if the new name itself contains a colon/quote/# etc.,
    # unlike the bare `name: {name}` interpolation _NEW_SCHEMA_TEMPLATE
    # uses (fine there since a slug-derived id has already ruled out
    # anything exotic; not fine for a name someone just typed by hand).
    quoted = json.dumps(new_name)
    new_text, count = _NAME_RE.subn(f"name: {quoted}", text, count=1)
    if count == 0:
        new_text = text.rstrip("\n") + f"\nname: {quoted}\n"
    return new_text


class TestRenderDialog(QDialog):
    """FormBuilder + render — the same validate/hook/render pipeline
    MainWindow._render uses, so "renders here" means "renders for real"."""

    def __init__(
        self,
        schema: Schema,
        schema_path: Path,
        username: str,
        palette: theme.Palette,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.schema = schema
        self.schema_path = schema_path
        self.username = username
        self.palette = palette
        self._highlighters: list[ConfigHighlighter] = []

        self.setWindowTitle(f"Test Render — {schema.name}")
        self.resize(900, 600)
        layout = QHBoxLayout(self)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        try:
            database = database_for_schema(schema, schema_path)
        except DatabaseError:
            database = None
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.form = FormBuilder(schema, database=database)
        scroll.setWidget(self.form)
        left_layout.addWidget(scroll, stretch=1)

        render_button = QPushButton("Render")
        render_button.clicked.connect(self._render)
        left_layout.addWidget(render_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)
        layout.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Output"))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont(theme.MONO_FONT_FAMILY))
        right_layout.addWidget(self.output, stretch=1)
        layout.addWidget(right)

    def _render(self) -> None:
        values = self.form.validate()
        if values is None:
            self.status_label.setText("Fix the highlighted fields before rendering.")
            return

        templates_dir, hooks_dir = project_dirs_for(self.schema_path)
        context = values
        logger.info("test render: schema=%s starting", self.schema.id)
        if self.schema.hook:
            try:
                services = services_for_schema(self.schema_path)
                context = run_hook(
                    hooks_dir, self.schema.hook, values, {"username": self.username}, services
                )
            except HookError as exc:
                self.status_label.setText(f"Hook rejected input: {exc.errors}")
                return
            except DatabaseError as exc:
                logger.error(
                    "test render: schema=%s hook '%s' database error: %s",
                    self.schema.id,
                    self.schema.hook,
                    exc,
                )
                self.status_label.setText(str(exc))
                return
            except Exception:  # noqa: BLE001 - this dialog exists to surface exactly this
                logger.exception(
                    "test render: schema=%s hook '%s' crashed", self.schema.id, self.schema.hook
                )
                self.status_label.setText(
                    f"Hook '{self.schema.hook}' crashed — traceback below and in logs/app.log."
                )
                self._highlighters.clear()
                self.output.setPlainText(traceback.format_exc())
                return

        try:
            filters = load_project_filters(project_root_for(self.schema_path))
            rendered = render_documents(
                self.schema,
                context,
                templates_dir=templates_dir,
                username=self.username,
                filters=filters,
            )
        except RenderError as exc:
            logger.warning("test render: schema=%s failed: %s", self.schema.id, exc)
            self.status_label.setText(f"Render failed: {exc}")
            return

        self._highlighters.clear()
        self.output.clear()
        text = "\n\n".join(rendered.values())
        self.output.setPlainText(text)
        self._highlighters.append(ConfigHighlighter(self.output.document(), self.palette))
        logger.info("test render: schema=%s succeeded", self.schema.id)
        self.status_label.setText("Rendered successfully.")


class HistoryDialog(QDialog):
    def __init__(
        self,
        schema_path: Path,
        templates_dir: Path,
        history_root: Path,
        schema_id: str,
        author: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.schema_path = schema_path
        self.templates_dir = templates_dir
        self.history_root = history_root
        self.schema_id = schema_id
        self.author = author

        self.setWindowTitle(f"Version History — {schema_id}")
        self.resize(600, 450)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Version", "Author", "Timestamp"])
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save Current as New Version")
        save_button.clicked.connect(self._save_version)
        diff_button = QPushButton("Diff Selected with Latest")
        diff_button.setObjectName("secondary")
        diff_button.clicked.connect(self._diff_selected)
        restore_button = QPushButton("Restore Selected")
        restore_button.setObjectName("secondary")
        restore_button.clicked.connect(self._restore_selected)
        buttons.addWidget(save_button)
        buttons.addWidget(diff_button)
        buttons.addWidget(restore_button)
        layout.addLayout(buttons)

        self.refresh()

    def refresh(self) -> None:
        self.entries = list_versions(self.history_root, self.schema_id)
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            self.table.setItem(row, 0, QTableWidgetItem(str(entry.version)))
            self.table.setItem(row, 1, QTableWidgetItem(entry.author))
            self.table.setItem(row, 2, QTableWidgetItem(entry.timestamp))

    def _save_version(self) -> None:
        note, ok = QInputDialog.getText(self, "Save Version", "Note (optional):")
        if not ok:
            return
        try:
            save_version(
                self.history_root,
                self.schema_path,
                self.templates_dir,
                author=self.author,
                note=note or None,
            )
        except VersioningError as exc:
            QMessageBox.warning(self, "Could not save version", str(exc))
            return
        self.refresh()

    def _selected_version(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.entries[row].version

    def _diff_selected(self) -> None:
        version = self._selected_version()
        if version is None or not self.entries:
            return
        latest = self.entries[-1].version
        if version == latest:
            QMessageBox.information(self, "Nothing to diff", "That's already the latest version.")
            return
        try:
            diffs = diff_versions(self.history_root, self.schema_id, version, latest)
        except VersioningError as exc:
            QMessageBox.warning(self, "Could not diff", str(exc))
            return
        text = "\n".join(diffs.values()) if diffs else "No differences."
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Diff v{version} → v{latest}")
        dialog.resize(700, 500)
        dialog_layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text)
        dialog_layout.addWidget(editor)
        dialog.exec()

    def _restore_selected(self) -> None:
        version = self._selected_version()
        if version is None:
            return
        confirmed = QMessageBox.question(
            self, "Restore version", f"Restore v{version}? This creates a new version from it."
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            restore_version(
                self.history_root,
                self.schema_path,
                self.templates_dir,
                version=version,
                author=self.author,
            )
        except VersioningError as exc:
            QMessageBox.warning(self, "Could not restore", str(exc))
            return
        self.refresh()
        self.accept()  # caller reloads the editor text from disk


class TemplateEditorWindow(QDialog):
    def __init__(
        self,
        user: User,
        store: AuthStore,
        schemas_dir: str | Path,
        palette: theme.Palette,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.user = user
        self.store = store
        self.schemas_dir = Path(schemas_dir)
        self.palette = palette
        self.current_path: Path | None = None
        self.current_schema: Schema | None = None

        self.setWindowTitle("Template Editor")
        self.resize(1000, 650)
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        templates_label = QLabel("TEMPLATES")
        templates_label.setObjectName("label-sm")
        left_layout.addWidget(templates_label)
        self.schema_list = QListWidget()
        self.schema_list.setObjectName("schema-list")
        self.schema_list.setSpacing(2)
        # Every row is one line of text at the same padding, so this is
        # safe — and it's the standard Qt fix for a styled item view
        # (`::item` rules force per-item style recomputation) being slow
        # to repolish after a stylesheet change: it skips per-item size
        # negotiation entirely instead of recalculating it item by item.
        self.schema_list.setUniformItemSizes(True)
        self.schema_list.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.schema_list, stretch=1)
        new_button = QPushButton("New Schema")
        new_button.clicked.connect(self._new_schema)
        left_layout.addWidget(new_button)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        header_row = QHBoxLayout()
        self.status_header = QLabel("(no schema selected)")
        self.status_header.setObjectName("headline-md")
        header_row.addWidget(self.status_header, stretch=1)
        self.status_badge = StatusBadge("draft", palette)
        self.status_badge.setVisible(False)
        header_row.addWidget(self.status_badge)
        self.rename_button = QPushButton("Rename")
        self.rename_button.setObjectName("secondary")
        self.rename_button.clicked.connect(self._rename_schema)
        header_row.addWidget(self.rename_button)
        right_layout.addLayout(header_row)

        schema_label_row = QHBoxLayout()
        schema_label_row.addWidget(QLabel("schema.yaml"), stretch=1)
        schema_expand_button = QPushButton("Expand")
        schema_expand_button.setObjectName("secondary")
        schema_expand_button.clicked.connect(
            lambda: self._open_expanded_editor("schema.yaml", self.schema_editor)
        )
        schema_label_row.addWidget(schema_expand_button)
        right_layout.addLayout(schema_label_row)

        self.schema_editor = QPlainTextEdit()
        self.schema_editor.setFont(QFont(theme.MONO_FONT_FAMILY))
        self.schema_highlighter = YamlHighlighter(self.schema_editor.document(), palette)
        right_layout.addWidget(self.schema_editor, stretch=1)

        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Template"))
        self.document_combo = QComboBox()
        self.document_combo.currentIndexChanged.connect(self._load_template_text)
        template_row.addWidget(self.document_combo, stretch=1)
        template_expand_button = QPushButton("Expand")
        template_expand_button.setObjectName("secondary")
        template_expand_button.clicked.connect(
            lambda: self._open_expanded_editor("Template", self.template_editor)
        )
        template_row.addWidget(template_expand_button)
        right_layout.addLayout(template_row)

        self.template_editor = QPlainTextEdit()
        self.template_editor.setFont(QFont(theme.MONO_FONT_FAMILY))
        self.jinja_highlighter = JinjaHighlighter(self.template_editor.document(), palette)
        right_layout.addWidget(self.template_editor, stretch=1)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        right_layout.addWidget(self.message_label)

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._save)
        self.check_button = QPushButton("Check")
        self.check_button.setObjectName("secondary")
        self.check_button.clicked.connect(self._check)
        self.extract_button = QPushButton("Extract Variables")
        self.extract_button.setObjectName("secondary")
        self.extract_button.clicked.connect(self._extract_variables)
        self.test_render_button = QPushButton("Test Render")
        self.test_render_button.setObjectName("secondary")
        self.test_render_button.clicked.connect(self._test_render)
        self.history_button = QPushButton("History")
        self.history_button.setObjectName("secondary")
        self.history_button.clicked.connect(self._open_history)
        self.export_button = QPushButton("Export Config Pack")
        self.export_button.setObjectName("secondary")
        self.export_button.clicked.connect(self._export_config_pack)
        for button in (
            self.save_button,
            self.check_button,
            self.extract_button,
            self.test_render_button,
            self.history_button,
            self.export_button,
        ):
            button_row.addWidget(button)
        right_layout.addLayout(button_row)

        lifecycle_row = QHBoxLayout()
        self.publish_button = QPushButton("Publish")
        self.publish_button.clicked.connect(lambda: self._set_status("published"))
        self.unpublish_button = QPushButton("Unpublish")
        self.unpublish_button.setObjectName("secondary")
        self.unpublish_button.clicked.connect(lambda: self._set_status("draft"))
        self.deprecate_button = QPushButton("Deprecate")
        self.deprecate_button.setObjectName("secondary")
        self.deprecate_button.clicked.connect(lambda: self._set_status("deprecated"))
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("secondary")
        self.delete_button.clicked.connect(self._delete_schema)
        self.delete_button.setVisible(user.role == ROLE_ADMIN)
        for button in (
            self.publish_button,
            self.unpublish_button,
            self.deprecate_button,
            self.delete_button,
        ):
            lifecycle_row.addWidget(button)
        right_layout.addLayout(lifecycle_row)

        splitter.addWidget(right)
        splitter.setSizes([260, 740])
        layout.addWidget(splitter)

        self._set_editing_enabled(False)
        self.refresh_list()

    # -- listing ---------------------------------------------------------

    def refresh_list(self, select_path: Path | None = None) -> None:
        self.schema_list.blockSignals(True)
        self.schema_list.clear()
        matched_item = None
        for path in find_schema_files(self.schemas_dir):
            try:
                schema = load_schema(path)
                label = f"{schema.name} [{schema.status}]"
            except Exception:  # noqa: BLE001 - a malformed schema still needs to show up to fix
                label = f"{path.name} (invalid)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.schema_list.addItem(item)
            if select_path is not None and path == select_path:
                matched_item = item
        if matched_item is not None:
            self.schema_list.setCurrentItem(matched_item)
        self.schema_list.blockSignals(False)
        if matched_item is not None:
            self._load_schema(select_path)
        else:
            self.current_path = None
            self.current_schema = None
            self._set_editing_enabled(False)

    def _set_editing_enabled(self, enabled: bool) -> None:
        for widget in (
            self.schema_editor,
            self.template_editor,
            self.rename_button,
            self.save_button,
            self.check_button,
            self.extract_button,
            self.test_render_button,
            self.history_button,
            self.export_button,
            self.publish_button,
            self.unpublish_button,
            self.deprecate_button,
            self.delete_button,
        ):
            widget.setEnabled(enabled)

    # -- selection ---------------------------------------------------------

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self._set_editing_enabled(False)
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        self._load_schema(path)

    def _load_schema(self, path: Path) -> None:
        self.current_path = path
        self.schema_editor.setPlainText(path.read_text(encoding="utf-8"))
        try:
            self.current_schema = load_schema(path)
            schema = self.current_schema
            self.status_header.setText(f"{schema.name}  (v{schema.version})")
            self.status_badge.set_status(self.current_schema.status, self.palette)
            self.status_badge.setVisible(True)
            self.document_combo.blockSignals(True)
            self.document_combo.clear()
            for doc in self.current_schema.document_list():
                self.document_combo.addItem(doc.label, doc.template)
            self.document_combo.blockSignals(False)
            self._load_template_text()
        except Exception as exc:  # noqa: BLE001 - shown to the user, not swallowed
            self.current_schema = None
            self.status_header.setText(f"(invalid schema: {exc})")
            self.status_badge.setVisible(False)
            self.document_combo.clear()
            self.template_editor.clear()
        self._set_editing_enabled(True)
        self.message_label.setText("")

    def _templates_dir(self) -> Path:
        templates_dir, _ = project_dirs_for(self.current_path)
        return templates_dir

    def _load_template_text(self) -> None:
        template_name = self.document_combo.currentData()
        if not template_name:
            self.template_editor.clear()
            return
        template_path = self._templates_dir() / template_name
        self.template_editor.setPlainText(
            template_path.read_text(encoding="utf-8") if template_path.is_file() else ""
        )

    def _open_expanded_editor(self, title: str, editor: QPlainTextEdit) -> None:
        """A larger, dedicated window over one editor pane — shares the
        same QTextDocument (Qt supports multiple views of one document
        natively) rather than copying text back and forth, so edits made
        here are already saved into `editor` the moment they're typed,
        with no extra sync step needed when this dialog closes."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)

        expanded = QPlainTextEdit()
        expanded.setFont(editor.font())
        expanded.setReadOnly(editor.isReadOnly())
        expanded.setDocument(editor.document())
        layout.addWidget(expanded, stretch=1)

        done_button = QPushButton("Done")
        done_button.clicked.connect(dialog.accept)
        layout.addWidget(done_button)

        dialog.exec()

    # -- new schema ---------------------------------------------------------

    def _new_schema(self) -> None:
        name, ok = QInputDialog.getText(self, "New Schema", "Schema name:")
        if not ok or not name.strip():
            return
        schema_id = _slug(name)
        schema_path = self.schemas_dir / f"{schema_id}.yaml"
        if schema_path.exists():
            QMessageBox.warning(self, "Already exists", f"'{schema_path.name}' already exists.")
            return

        templates_dir, _ = project_dirs_for(schema_path)
        self.schemas_dir.mkdir(parents=True, exist_ok=True)
        templates_dir.mkdir(parents=True, exist_ok=True)

        schema_path.write_text(
            _NEW_SCHEMA_TEMPLATE.format(name=name, id=schema_id), encoding="utf-8"
        )
        (templates_dir / f"{schema_id}.j2").write_text(_NEW_TEMPLATE_STUB, encoding="utf-8")

        self.refresh_list(select_path=schema_path)

    # -- save ---------------------------------------------------------

    def _save(self) -> None:
        if self.current_path is None:
            return
        schema_text = self.schema_editor.toPlainText()
        try:
            yaml.safe_load(schema_text)
        except yaml.YAMLError as exc:
            QMessageBox.warning(self, "Invalid YAML", f"Not saved — fix the syntax error:\n{exc}")
            return
        self.current_path.write_text(schema_text, encoding="utf-8")

        template_name = self.document_combo.currentData()
        if template_name:
            template_path = self._templates_dir() / template_name
            template_path.write_text(self.template_editor.toPlainText(), encoding="utf-8")

        self.refresh_list(select_path=self.current_path)
        self.message_label.setText("Saved.")

    # -- check / extract ---------------------------------------------------------

    def _parsed_schema(self) -> tuple[dict, Schema] | None:
        try:
            data = yaml.safe_load(self.schema_editor.toPlainText())
            schema = schema_from_dict(data, source_path=self.current_path)
        except Exception as exc:  # noqa: BLE001 - reported to the user, not swallowed
            QMessageBox.warning(self, "Could not parse schema", str(exc))
            return None
        return data, schema

    def _check(self) -> None:
        parsed = self._parsed_schema()
        if parsed is None:
            return
        data, schema = parsed
        templates_dir, hooks_dir = project_dirs_for(self.current_path)

        messages: list[str] = []
        try:
            validate_schema(data, templates_dir=templates_dir, hooks_dir=hooks_dir)
            messages.append("Schema structure: OK")
        except SchemaValidationError as exc:
            messages.append("Schema structure issues:")
            messages += [f"  - {issue}" for issue in exc.issues]

        for doc in schema.document_list():
            template_path = templates_dir / doc.template
            if not template_path.is_file():
                continue
            variables = extract_variables_from_file(template_path)
            statuses = classify_variables(
                variables, set(schema.field_map()), has_hook=bool(schema.hook)
            )
            missing = [s.name for s in statuses if s.source == "missing"]
            if missing:
                messages.append(
                    f"{doc.template}: variables with no field or hook source "
                    f"(would raise StrictUndefined at render time): {', '.join(missing)}"
                )
            else:
                messages.append(f"{doc.template}: all variables accounted for")

        QMessageBox.information(self, "Check results", "\n".join(messages))

    def _extract_variables(self) -> None:
        if self.current_schema is None:
            return
        template_name = self.document_combo.currentData()
        if not template_name:
            return
        template_path = self._templates_dir() / template_name
        if not template_path.is_file():
            QMessageBox.information(self, "No template", "Save the template first.")
            return
        variables = extract_variables_from_file(template_path)
        statuses = classify_variables(
            variables,
            set(self.current_schema.field_map()),
            has_hook=bool(self.current_schema.hook),
        )
        lines = [f"{s.name}: {s.source}" for s in statuses] or ["(no variables found)"]
        QMessageBox.information(self, f"Variables in {template_name}", "\n".join(lines))

    # -- test render ---------------------------------------------------------

    def _test_render(self) -> None:
        if self.current_schema is None or self.current_path is None:
            return
        dialog = TestRenderDialog(
            self.current_schema, self.current_path, self.user.username, self.palette, self
        )
        dialog.exec()

    # -- history ---------------------------------------------------------

    def _open_history(self) -> None:
        if self.current_schema is None or self.current_path is None:
            return
        templates_dir, _ = project_dirs_for(self.current_path)
        history_root = project_history_dir_for(self.current_path)
        dialog = HistoryDialog(
            self.current_path,
            templates_dir,
            history_root,
            self.current_schema.id,
            self.user.username,
            self,
        )
        dialog.exec()
        self._load_schema(self.current_path)  # picks up any restore

    # -- config pack export ---------------------------------------------------------

    def _export_config_pack(self) -> None:
        if self.current_schema is None or self.current_path is None:
            return
        default_name = f"{self.current_schema.id}.configpack.zip"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export Config Pack", default_name, "Config packs (*.zip)"
        )
        if not path_str:
            return
        output_path = export_config_pack(self.current_path, path_str, author=self.user.username)
        self.message_label.setText(f"Exported to {output_path}.")

    # -- rename ---------------------------------------------------------

    def _rename_schema(self) -> None:
        if self.current_path is None or self.current_schema is None:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename Template", "New name:", text=self.current_schema.name
        )
        new_name = new_name.strip()
        if not ok or not new_name:
            return
        text = self.schema_editor.toPlainText()
        new_text = _set_name_line(text, new_name)
        self.schema_editor.setPlainText(new_text)
        self.current_path.write_text(new_text, encoding="utf-8")
        self.refresh_list(select_path=self.current_path)
        self.message_label.setText(f"Renamed to '{new_name}'.")

    # -- lifecycle ---------------------------------------------------------

    def _set_status(self, new_status: str) -> None:
        if self.current_path is None:
            return
        text = self.schema_editor.toPlainText()
        new_text = _set_status_line(text, new_status)
        self.schema_editor.setPlainText(new_text)
        self.current_path.write_text(new_text, encoding="utf-8")
        self.refresh_list(select_path=self.current_path)
        self.message_label.setText(f"Status set to '{new_status}'.")

    def _delete_schema(self) -> None:
        if self.current_path is None or self.current_schema is None:
            return
        confirmed = QMessageBox.question(
            self,
            "Delete template",
            f"Delete '{self.current_schema.name}'? This removes the schema and template "
            "files. Generation history is preserved.",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        templates_dir, hooks_dir = project_dirs_for(self.current_path)
        for doc in self.current_schema.document_list():
            template_path = templates_dir / doc.template
            if template_path.is_file():
                template_path.unlink()
        if self.current_schema.hook:
            hook_path = hooks_dir / f"{self.current_schema.hook}.py"
            if hook_path.is_file():
                hook_path.unlink()
        self.current_path.unlink()

        self.refresh_list()
