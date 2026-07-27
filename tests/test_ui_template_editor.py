import zipfile
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from configgen.core.auth import AuthStore
from configgen.core.schema import project_history_dir_for
from configgen.ui import theme
from configgen.ui.template_editor import HistoryDialog, TemplateEditorWindow

WIDGET_SCHEMA = """\
name: Widget
id: widget
version: 1
status: draft
identity_field: name
template: widget.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""


def _editor(tmp_path: Path, qtbot, *, role="admin", username="admin"):
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (schemas_dir / "widget.yaml").write_text(WIDGET_SCHEMA, encoding="utf-8")
    (templates_dir / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")

    store = AuthStore(tmp_path / "users.db")
    if username != "admin":
        store.create_user(username, "hunter22pw", role)
    user = store.get_user(username)

    palette = theme.palette_for(False)
    window = TemplateEditorWindow(user, store, schemas_dir, palette)
    qtbot.addWidget(window)
    return window, store


# -- listing / selection ---------------------------------------------------------


def test_lists_existing_schema_and_loads_it_on_select(qtbot, tmp_path: Path):
    window, _store = _editor(tmp_path, qtbot)
    assert window.schema_list.count() == 1
    window.schema_list.setCurrentRow(0)
    assert window.current_schema.id == "widget"
    assert "hello {{ name }}" in window.template_editor.toPlainText()


def test_delete_button_hidden_for_template_engineer(qtbot, tmp_path: Path):
    window, _store = _editor(tmp_path, qtbot, role="template_engineer", username="tina")
    assert window.delete_button.isHidden() is True


def test_delete_button_visible_for_admin(qtbot, tmp_path: Path):
    window, _store = _editor(tmp_path, qtbot)
    assert window.delete_button.isHidden() is False


# -- new schema ---------------------------------------------------------


def test_new_schema_creates_files_and_selects_it(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Router Base", True))
    )
    window._new_schema()

    assert window.schema_list.count() == 2
    assert window.current_schema is not None
    assert window.current_schema.id == "router_base"
    assert (window.schemas_dir / "router_base.yaml").is_file()
    assert (window._templates_dir() / "router_base.j2").is_file()


def test_new_schema_refuses_duplicate_id(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Widget", True)))
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls.append(a)))
    window._new_schema()
    assert calls
    assert window.schema_list.count() == 1  # unchanged


# -- save ---------------------------------------------------------


def test_save_writes_editor_text_to_disk(qtbot, tmp_path: Path):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)
    window.template_editor.setPlainText("hi {{ name }} v2")

    window._save()

    saved_template = (window._templates_dir() / "widget.j2").read_text(encoding="utf-8")
    assert saved_template == "hi {{ name }} v2"
    assert window.message_label.text() == "Saved."


def test_save_rejects_invalid_yaml(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)
    original = window.current_path.read_text(encoding="utf-8")
    window.schema_editor.setPlainText("not: valid: yaml: [")

    calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls.append(a)))
    window._save()

    assert calls
    assert window.current_path.read_text(encoding="utf-8") == original


# -- check / extract ---------------------------------------------------------


def test_check_reports_missing_variable(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)
    window.template_editor.setPlainText("hello {{ name }} at {{ site }}")
    window._save()

    messages = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda self, title, text: messages.append(text))
    )
    window._check()

    assert messages
    assert "site" in messages[0]
    assert "Schema structure: OK" in messages[0]


def test_check_reports_structural_issue_for_bad_field_type(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)
    window.schema_editor.setPlainText(WIDGET_SCHEMA.replace("type: string", "type: not_a_type"))

    messages = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda self, title, text: messages.append(text))
    )
    window._check()

    assert messages
    assert "unrecognized field type" in messages[0]


def test_extract_variables_classifies_by_source(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)
    window.template_editor.setPlainText("{{ name }} {{ site }}")
    window._save()

    messages = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda self, title, text: messages.append(text))
    )
    window._extract_variables()

    assert "name: field" in messages[0]
    assert "site: missing" in messages[0]


# -- test render ---------------------------------------------------------


def test_test_render_opens_and_produces_output(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)

    captured = {}

    def fake_exec(self):
        captured["form"] = self.form
        self.form.set_raw_values({"name": "web01"})
        self._render()
        captured["output"] = self.output.toPlainText()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("configgen.ui.template_editor.TestRenderDialog.exec", fake_exec)
    window._test_render()

    assert "hello web01" in captured["output"]


# -- lifecycle ---------------------------------------------------------


def test_publish_unpublish_deprecate_cycle(qtbot, tmp_path: Path):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)
    assert window.current_schema.status == "draft"

    window._set_status("published")
    assert window.current_schema.status == "published"

    window._set_status("deprecated")
    assert window.current_schema.status == "deprecated"

    window._set_status("draft")
    assert window.current_schema.status == "draft"


def test_delete_removes_schema_and_template_files(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)
    schema_path = window.current_path
    template_path = window._templates_dir() / "widget.j2"

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    window._delete_schema()

    assert not schema_path.exists()
    assert not template_path.exists()
    assert window.schema_list.count() == 0


# -- history ---------------------------------------------------------


def test_history_save_diff_and_restore(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)

    history_root = project_history_dir_for(window.current_path)
    history = HistoryDialog(
        window.current_path,
        window._templates_dir(),
        history_root,
        window.current_schema.id,
        "admin",
    )
    qtbot.addWidget(history)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("v1 save", True)))
    history._save_version()
    assert len(history.entries) == 1

    # Bump the version field and template text, then save a second version.
    text = window.current_path.read_text(encoding="utf-8").replace("version: 1", "version: 2")
    window.current_path.write_text(text, encoding="utf-8")
    (window._templates_dir() / "widget.j2").write_text("hi v2 {{ name }}", encoding="utf-8")
    history._save_version()
    assert len(history.entries) == 2

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    history.table.selectRow(0)
    history._diff_selected()  # exercises the diff path without raising

    history._restore_selected()
    assert len(history.entries) == 3
    # Restored content should match v1's template again.
    assert "hello {{ name }}" in (window._templates_dir() / "widget.j2").read_text(encoding="utf-8")


# -- config pack export ---------------------------------------------------------


def test_export_config_pack_writes_a_zip(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)

    out_zip = tmp_path / "widget.configpack.zip"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_zip), ""))
    )
    window._export_config_pack()

    assert out_zip.is_file()
    assert "Exported to" in window.message_label.text()
    with zipfile.ZipFile(out_zip) as zf:
        assert "schema.yaml" in zf.namelist()
        assert "templates/widget.j2" in zf.namelist()


def test_export_config_pack_cancelled_dialog_does_nothing(qtbot, tmp_path: Path, monkeypatch):
    window, _store = _editor(tmp_path, qtbot)
    window.schema_list.setCurrentRow(0)

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    window._export_config_pack()

    assert window.message_label.text() == ""
