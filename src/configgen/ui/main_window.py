"""Stacked dashboard/generator, preview, diff, save, keyboard shortcuts
(§15/§15.2).

Every action here — validate, run the prepare hook, render, preflight,
save, log — calls straight into the same core functions the CLI uses.
This module's job is only to collect form input and show results; it
never re-implements what "valid"/"rendered"/"saved" mean.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from configgen.appinfo import APP_NAME, __version__
from configgen.core.auth import AuthStore, User
from configgen.core.db import DatabaseError, database_for_schema
from configgen.core.differ import find_recent_outputs, unified_diff
from configgen.core.exporter import resolve_output_dir, save_documents
from configgen.core.preflight import run_preflight
from configgen.core.registry import load_project_filters
from configgen.core.renderer import RenderError, render_documents
from configgen.core.schema import (
    Schema,
    find_schema_files,
    load_schema,
    load_schema_dict,
    project_dirs_for,
    project_preflight_dir_for,
    project_root_for,
)
from configgen.paths import output_dir
from configgen.prepare import PrepareError, run_prepare_hook, services_for_schema
from configgen.ui import theme
from configgen.ui.about import AboutDialog
from configgen.ui.bulk_dialog import BulkDialog
from configgen.ui.config_pack_import import ImportConfigPackDialog
from configgen.ui.dashboard import Dashboard
from configgen.ui.form_builder import FormBuilder
from configgen.ui.generation_log import GenerationLogDialog
from configgen.ui.highlighters import ConfigHighlighter
from configgen.ui.template_editor import TemplateEditorWindow
from configgen.ui.user_admin import UserAdminWindow


class GeneratorView(QWidget):
    """One schema's form + preview panes (tabs for multi-document, a
    single pane for one — §7)."""

    def __init__(
        self,
        schema: Schema,
        schema_path: Path,
        database,
        palette: theme.Palette,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.schema = schema
        self.schema_path = schema_path
        self.database = database
        self.palette = palette
        self.last_rendered: dict[str, str] = {}
        self._highlighters: list[ConfigHighlighter] = []

        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        title = QLabel(schema.name)
        title.setStyleSheet("font-weight: 600; font-size: 15px;")
        left_layout.addWidget(title)

        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form = FormBuilder(schema, database=database)
        self.form_scroll.setWidget(self.form)
        left_layout.addWidget(self.form_scroll, stretch=1)

        button_row = QHBoxLayout()
        self.preview_button = QPushButton("Preview  (Ctrl+P)")
        self.preview_button.setObjectName("secondary")
        self.generate_button = QPushButton("Generate  (Ctrl+G)")
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.generate_button)
        left_layout.addLayout(button_row)

        self.status_label = QLabel()
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Preview"))
        self.preview_tabs = QTabWidget()
        right_layout.addWidget(self.preview_tabs, stretch=1)
        splitter.addWidget(right)
        splitter.setSizes([420, 520])

        layout.addWidget(splitter)

    def show_rendered(self, rendered: dict[str, str]) -> None:
        self.last_rendered = rendered
        self.preview_tabs.clear()
        self._highlighters.clear()

        docs_by_key = {doc.key: doc for doc in self.schema.document_list()}
        for doc_key, text in rendered.items():
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            editor.setPlainText(text)
            self._highlighters.append(ConfigHighlighter(editor.document(), self.palette))
            label = docs_by_key[doc_key].label if doc_key in docs_by_key else doc_key
            self.preview_tabs.addTab(editor, label)

        self.preview_tabs.tabBar().setVisible(len(rendered) > 1)

    def refresh_palette(self, palette: theme.Palette) -> None:
        self.palette = palette
        for highlighter in self._highlighters:
            highlighter.set_palette(palette)


class MainWindow(QMainWindow):
    def __init__(
        self,
        user: User,
        store: AuthStore,
        schemas_dir: str | Path,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.user = user
        self.store = store
        self.schemas_dir = Path(schemas_dir)
        self.dark = theme.load_dark_mode(user.username)
        self.palette = theme.palette_for(self.dark)
        self.generator_view: GeneratorView | None = None

        self.setWindowTitle(f"{APP_NAME} v{__version__} — {user.username}")
        self.resize(1150, 780)

        self.user_groups = store.groups_for_user(user.username)
        self.schemas = self._load_schemas()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.dashboard = self._build_dashboard()
        self.stack.addWidget(self.dashboard)

        self._build_toolbar()
        self._build_shortcuts()
        self._apply_theme()

    # -- setup ---------------------------------------------------------

    def _load_schemas(self) -> list[Schema]:
        schemas = []
        for path in find_schema_files(self.schemas_dir):
            try:
                schemas.append(load_schema(path))
            except Exception:  # noqa: BLE001 - a malformed schema just doesn't get a tile
                continue
        return schemas

    def _build_dashboard(self) -> Dashboard:
        recent = self.store.list_generation_log(self.user)
        dashboard = Dashboard(
            self.user, self.schemas, self.user_groups, self.palette, recent_log_entries=recent
        )
        dashboard.templateSelected.connect(self._open_generator)
        dashboard.bulkGenerateRequested.connect(self._open_bulk_dialog)
        dashboard.templateEditorRequested.connect(self._open_template_editor)
        dashboard.userAdminRequested.connect(self._open_user_admin)
        dashboard.importConfigPackRequested.connect(self._open_import_config_pack)
        dashboard.generationLogRequested.connect(self._open_generation_log)
        return dashboard

    def _refresh_dashboard(self) -> None:
        """Rebuilds the dashboard from disk — needed after the template
        editor or bulk dialog change what's visible (schema status/list,
        recent generations)."""
        self.schemas = self._load_schemas()
        old_dashboard = self.dashboard
        was_current = self.stack.currentWidget() is old_dashboard
        self.dashboard = self._build_dashboard()
        self.stack.addWidget(self.dashboard)
        self.stack.removeWidget(old_dashboard)
        old_dashboard.deleteLater()
        if was_current:
            self.stack.setCurrentWidget(self.dashboard)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("View")
        dark_action = QAction("Dark Mode", self)
        dark_action.setCheckable(True)
        dark_action.setChecked(self.dark)
        dark_action.toggled.connect(self._on_dark_mode_toggled)
        toolbar.addAction(dark_action)

        about_action = QAction("About", self)
        about_action.triggered.connect(self._open_about)
        toolbar.addAction(about_action)

    def _build_shortcuts(self) -> None:
        def bind(sequence: str, handler) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)

        bind("Ctrl+G", lambda: self.generator_view and self._generate(self.generator_view))
        bind("Ctrl+P", lambda: self.generator_view and self._preview(self.generator_view))
        bind("Ctrl+S", lambda: self.generator_view and self._save_as(self.generator_view))
        bind("Ctrl+D", lambda: self.generator_view and self._diff(self.generator_view))
        bind("Ctrl+N", self._back_to_dashboard)
        bind("Ctrl+B", self._open_bulk_dialog)
        bind("Escape", self._back_to_dashboard)

    # -- theme ---------------------------------------------------------

    def _apply_theme(self) -> None:
        self.setStyleSheet(theme.stylesheet(self.palette))

    def _on_dark_mode_toggled(self, checked: bool) -> None:
        self.dark = checked
        self.palette = theme.palette_for(checked)
        theme.save_dark_mode(self.user.username, checked)
        self._apply_theme()
        if self.generator_view is not None:
            self.generator_view.refresh_palette(self.palette)

    # -- navigation ------------------------------------------------------

    def _not_yet_available(self, feature: str) -> None:
        QMessageBox.information(
            self, feature, f"{feature} isn't in this build yet — use the CLI for now."
        )

    def _back_to_dashboard(self) -> None:
        self.stack.setCurrentWidget(self.dashboard)

    def _open_about(self) -> None:
        AboutDialog(self).exec()

    def _open_bulk_dialog(self) -> None:
        schema_paths = {s.id: s.source_path for s in self.schemas if s.source_path}
        dialog = BulkDialog(
            self.user, self.store, self.schemas, schema_paths, self.user_groups, self
        )
        dialog.exec()
        self._refresh_dashboard()

    def _open_template_editor(self) -> None:
        dialog = TemplateEditorWindow(self.user, self.store, self.schemas_dir, self.palette, self)
        dialog.exec()
        self._refresh_dashboard()

    def _open_user_admin(self) -> None:
        dialog = UserAdminWindow(self.store, self.user, self)
        dialog.exec()
        self.user_groups = self.store.groups_for_user(self.user.username)
        self._refresh_dashboard()

    def _open_generation_log(self) -> None:
        dialog = GenerationLogDialog(self.store, self.user, self)
        dialog.regenerateRequested.connect(self._regenerate_from_log)
        dialog.exec()

    def _regenerate_from_log(self, schema_id: str, form_inputs: dict) -> None:
        self._open_generator(schema_id)
        if self.generator_view is not None:
            self.generator_view.form.set_raw_values(form_inputs)

    def _open_import_config_pack(self) -> None:
        dialog = ImportConfigPackDialog(self.schemas_dir.parent, self)
        dialog.exec()
        self._refresh_dashboard()

    def _schema_path_for(self, schema_id: str) -> Path | None:
        for path in find_schema_files(self.schemas_dir):
            if load_schema_dict(path).get("id") == schema_id:
                return path
        return None

    def _open_generator(self, schema_id: str) -> None:
        schema_path = self._schema_path_for(schema_id)
        if schema_path is None:
            QMessageBox.warning(self, "Not found", f"Schema '{schema_id}' not found.")
            return
        schema = load_schema(schema_path)

        try:
            database = database_for_schema(schema, schema_path)
        except DatabaseError as exc:
            QMessageBox.warning(self, "Database error", str(exc))
            return

        view = GeneratorView(schema, schema_path, database, self.palette)
        view.preview_button.clicked.connect(lambda: self._preview(view))
        view.generate_button.clicked.connect(lambda: self._generate(view))

        if self.generator_view is not None:
            self.stack.removeWidget(self.generator_view)
            self.generator_view.deleteLater()
        self.generator_view = view
        self.stack.addWidget(view)
        self.stack.setCurrentWidget(view)

    # -- generation pipeline: validate -> hook -> render -> preflight ------

    def _render(self, view: GeneratorView) -> dict[str, str] | None:
        values = view.form.validate()
        if values is None:
            view.status_label.setText("Fix the highlighted fields before continuing.")
            return None

        schema, schema_path = view.schema, view.schema_path
        templates_dir, prepare_dir = project_dirs_for(schema_path)
        context = values

        if schema.prepare:
            try:
                services = services_for_schema(schema_path)
                context = run_prepare_hook(
                    prepare_dir,
                    schema.prepare,
                    values,
                    {"username": self.user.username},
                    services,
                )
            except PrepareError as exc:
                for key, message in exc.errors.items():
                    if key in view.form.widgets:
                        view.form.widgets[key].set_error(message)
                view.status_label.setText("Prepare hook rejected this submission.")
                return None
            except DatabaseError as exc:
                view.status_label.setText(str(exc))
                return None

        try:
            filters = load_project_filters(project_root_for(schema_path))
            rendered = render_documents(
                schema,
                context,
                templates_dir=templates_dir,
                username=self.user.username,
                filters=filters,
            )
        except RenderError as exc:
            view.status_label.setText(f"Render failed: {exc}")
            return None

        warnings: list[str] = []
        if schema.preflight:
            preflight_dir = project_preflight_dir_for(schema_path)
            for doc_key, text in rendered.items():
                warnings += [
                    f"{doc_key}: {w}" for w in run_preflight(schema.preflight, text, preflight_dir)
                ]
        view.status_label.setText("\n".join(["Preflight warnings:", *warnings]) if warnings else "")

        view.show_rendered(rendered)
        return rendered

    def _preview(self, view: GeneratorView) -> None:
        self._render(view)

    def _generate(self, view: GeneratorView) -> None:
        rendered = self._render(view)
        if rendered is None:
            return

        raw_values = view.form.raw_values()
        result = save_documents(
            rendered,
            view.schema,
            raw_values=raw_values,
            output_root=output_dir(),
            username=self.user.username,
        )
        for path in result.document_paths.values():
            self.store.record_generation(
                self.user,
                schema_id=view.schema.id,
                schema_version=view.schema.version,
                form_inputs=raw_values,
                output_filename=path.name,
                group_name=view.schema.group,
            )
        view.status_label.setText(f"Saved to {result.output_dir}")

    # -- save as / diff ----------------------------------------------------

    def _current_doc_key(self, view: GeneratorView) -> str | None:
        index = view.preview_tabs.currentIndex()
        if index < 0:
            return None
        return list(view.last_rendered)[index]

    def _save_as(self, view: GeneratorView) -> None:
        if not view.last_rendered:
            QMessageBox.information(self, "Nothing to save", "Preview or Generate first.")
            return
        doc_key = self._current_doc_key(view) or next(iter(view.last_rendered))
        path_str, _ = QFileDialog.getSaveFileName(self, "Save config as", "", "Text files (*.txt)")
        if path_str:
            Path(path_str).write_text(view.last_rendered[doc_key], encoding="utf-8")

    def _diff(self, view: GeneratorView) -> None:
        if not view.last_rendered:
            QMessageBox.information(self, "Nothing to diff", "Preview or Generate first.")
            return

        identity_field = view.schema.identity_field
        identity_value = view.form.raw_values().get(identity_field) if identity_field else None
        if not identity_value:
            QMessageBox.information(
                self, "Can't diff", "This schema has no identity field value to look up history by."
            )
            return

        doc_key = self._current_doc_key(view) or next(iter(view.last_rendered))
        group_dir = resolve_output_dir(output_dir(), self.user.username, view.schema)
        matches = find_recent_outputs(
            group_dir, view.schema.id, str(identity_value), doc_key=doc_key, limit=1
        )
        if not matches:
            QMessageBox.information(
                self, "No history", "No previously saved output to diff against."
            )
            return

        last_path = matches[0]
        diff_text = unified_diff(
            last_path.read_text(encoding="utf-8"),
            view.last_rendered[doc_key],
            label_a=str(last_path),
            label_b="current preview",
        )
        self._show_diff_dialog(diff_text or "No differences.")

    def _show_diff_dialog(self, diff_text: str) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Diff with last generated")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(diff_text)
        layout.addWidget(editor)
        dialog.exec()
