import zipfile
from pathlib import Path

from PySide6.QtWidgets import QDialog

from configgen.core.configpack import export_config_pack
from configgen.ui.config_pack_import import ImportConfigPackDialog

WIDGET_SCHEMA = """\
name: Widget
id: widget
version: 1
status: published
identity_field: name
template: widget.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""


def _make_pack(tmp_path: Path) -> Path:
    project = tmp_path / "source"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "widget.yaml").write_text(WIDGET_SCHEMA, encoding="utf-8")
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    return export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "widget.zip")


def test_import_with_no_conflict_succeeds(qtbot, tmp_path: Path):
    pack = _make_pack(tmp_path)
    target = tmp_path / "target"
    dialog = ImportConfigPackDialog(target)
    qtbot.addWidget(dialog)
    dialog.file_input.setText(str(pack))

    dialog._run_import()

    assert dialog.imported_schema_id == "widget"
    assert (target / "schemas" / "widget.yaml").is_file()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_import_without_a_file_shows_warning(qtbot, tmp_path: Path, monkeypatch):
    dialog = ImportConfigPackDialog(tmp_path / "target")
    qtbot.addWidget(dialog)

    calls = []
    monkeypatch.setattr(
        "configgen.ui.config_pack_import.QMessageBox.warning",
        staticmethod(lambda *a, **k: calls.append(a)),
    )
    dialog._run_import()
    assert calls


def test_import_bad_pack_shows_error_and_keeps_dialog_open(qtbot, tmp_path: Path):
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("readme.txt", "not a config pack")

    dialog = ImportConfigPackDialog(tmp_path / "target")
    qtbot.addWidget(dialog)
    dialog.file_input.setText(str(bad_zip))

    dialog._run_import()

    assert "Import failed" in dialog.status_label.text()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_conflict_overwrite_via_dialog(qtbot, tmp_path: Path, monkeypatch):
    pack = _make_pack(tmp_path)
    target = tmp_path / "target"
    first = ImportConfigPackDialog(target)
    qtbot.addWidget(first)
    first.file_input.setText(str(pack))
    first._run_import()
    assert first.imported_schema_id == "widget"

    second = ImportConfigPackDialog(target)
    qtbot.addWidget(second)
    second.file_input.setText(str(pack))

    calls = []

    def fake_resolve(conflict):
        calls.append(conflict.schema_id)
        second._run_import(on_conflict="overwrite")

    monkeypatch.setattr(second, "_resolve_conflict", fake_resolve)
    second._run_import()

    assert calls == ["widget"]
    assert second.imported_schema_id == "widget"


def test_conflict_rename_via_dialog(qtbot, tmp_path: Path, monkeypatch):
    pack = _make_pack(tmp_path)
    target = tmp_path / "target"
    first = ImportConfigPackDialog(target)
    qtbot.addWidget(first)
    first.file_input.setText(str(pack))
    first._run_import()

    second = ImportConfigPackDialog(target)
    qtbot.addWidget(second)
    second.file_input.setText(str(pack))

    calls = []

    def fake_resolve(conflict):
        calls.append(conflict.schema_id)
        second._run_import(on_conflict="rename", new_id="widget_v2")

    monkeypatch.setattr(second, "_resolve_conflict", fake_resolve)
    second._run_import()

    assert calls == ["widget"]
    assert second.imported_schema_id == "widget_v2"
    assert (target / "schemas" / "widget_v2.yaml").is_file()
