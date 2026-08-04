from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from configgen.core.auth import AuthStore
from configgen.core.schema import Field, Schema
from configgen.ui.bulk_dialog import BulkDialog


def _project(tmp_path: Path) -> tuple[Schema, Path]:
    root = tmp_path / "project"
    (root / "schemas").mkdir(parents=True)
    (root / "templates").mkdir()
    schema_path = root / "schemas" / "widget.yaml"
    schema_path.write_text("placeholder", encoding="utf-8")
    (root / "templates" / "widget.j2").write_text(
        "hello {{ name }} port {{ port }}", encoding="utf-8"
    )

    schema = Schema(
        name="Widget",
        id="widget",
        template="widget.j2",
        identity_field="name",
        fields=[
            Field(key="name", label="Name", type="string", required=True),
            Field(key="port", label="Port", type="int", required=True),
        ],
    )
    return schema, schema_path


def _dialog(tmp_path: Path, qtbot, monkeypatch, *, role="admin", username="admin"):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    schema, schema_path = _project(tmp_path)
    store = AuthStore(tmp_path / "users.db")
    if username != "admin":
        store.create_user(username, "hunter22pw", role)
    user = store.get_user(username)

    dialog = BulkDialog(user, store, [schema], {schema.id: schema_path}, set())
    qtbot.addWidget(dialog)
    return dialog, store


def test_all_valid_rows_generate_and_log(qtbot, tmp_path: Path, monkeypatch):
    dialog, store = _dialog(tmp_path, qtbot, monkeypatch)
    rows_path = tmp_path / "rows.csv"
    rows_path.write_text("name,port\nweb01,22\nweb02,23\n", encoding="utf-8")
    dialog.input_path = rows_path

    dialog._run()

    assert dialog.result.valid_count == 2
    assert dialog.result.error_count == 0
    assert dialog.error_table.rowCount() == 0
    assert not dialog.export_button.isEnabled()
    assert dialog.copy_configs_button.isEnabled()
    assert "2 valid, 0 errors" in dialog.summary_label.text()

    entries = store.list_generation_log(dialog.user)
    assert len(entries) == 2
    assert all(e["bulk_batch_id"] == dialog.result.batch_id for e in entries)


def test_invalid_rows_populate_error_table_and_export(qtbot, tmp_path: Path, monkeypatch):
    dialog, store = _dialog(tmp_path, qtbot, monkeypatch)
    rows_path = tmp_path / "rows.csv"
    rows_path.write_text("name,port\nweb01,22\nweb02,notanumber\n", encoding="utf-8")
    dialog.input_path = rows_path

    dialog._run()

    assert dialog.result.valid_count == 1
    assert dialog.result.error_count == 1
    assert dialog.error_table.rowCount() == 1
    assert dialog.error_table.item(0, 0).text() == "3"
    assert "port" in dialog.error_table.item(0, 1).text()
    assert dialog.export_button.isEnabled()

    out_csv = tmp_path / "errors.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_csv), ""))
    )
    dialog._export_errors()
    content = out_csv.read_text(encoding="utf-8")
    assert "row_number,errors" in content
    assert "port" in content


def test_copy_configs_to_folder_copies_only_txt_files(qtbot, tmp_path: Path, monkeypatch):
    dialog, _store = _dialog(tmp_path, qtbot, monkeypatch)
    rows_path = tmp_path / "rows.csv"
    rows_path.write_text("name,port\nweb01,22\nweb02,23\n", encoding="utf-8")
    dialog.input_path = rows_path
    dialog._run()
    assert dialog.result.valid_count == 2

    dest = tmp_path / "elsewhere"
    dest.mkdir()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest))
    )
    dialog._copy_configs_to_folder()

    copied = sorted(dest.iterdir())
    assert len(copied) == 2
    assert all(p.suffix == ".txt" for p in copied)
    assert not list(dest.glob("*.json"))
    assert "2 config file(s) copied" in dialog.summary_label.text()


def test_copy_configs_without_a_run_does_nothing(qtbot, tmp_path: Path, monkeypatch):
    dialog, _store = _dialog(tmp_path, qtbot, monkeypatch)
    assert not dialog.copy_configs_button.isEnabled()

    calls = []
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: calls.append(1) or "")
    )
    dialog._copy_configs_to_folder()  # no result yet — should not raise
    assert not calls


def test_run_without_schema_or_file_shows_warning_and_does_nothing(
    qtbot, tmp_path: Path, monkeypatch
):
    dialog, store = _dialog(tmp_path, qtbot, monkeypatch)
    calls = []
    monkeypatch.setattr(
        "configgen.ui.bulk_dialog.QMessageBox.warning",
        staticmethod(lambda *a, **k: calls.append(a)),
    )
    dialog._run()  # no input_path set
    assert calls
    assert dialog.result is None


def test_download_template_writes_csv_header_matching_field_keys(
    qtbot, tmp_path: Path, monkeypatch
):
    dialog, _store = _dialog(tmp_path, qtbot, monkeypatch)
    target = tmp_path / "template.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    dialog._download_template()

    assert target.read_text(encoding="utf-8").strip() == "name,port"


def test_download_template_writes_xlsx_header_matching_field_keys(
    qtbot, tmp_path: Path, monkeypatch
):
    import openpyxl

    dialog, _store = _dialog(tmp_path, qtbot, monkeypatch)
    target = tmp_path / "template.xlsx"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    dialog._download_template()

    workbook = openpyxl.load_workbook(target, read_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    assert rows == [("name", "port")]


def test_download_template_without_schema_shows_warning_and_writes_nothing(
    qtbot, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    root = tmp_path / "project"
    (root / "schemas").mkdir(parents=True)
    (root / "templates").mkdir()
    store = AuthStore(tmp_path / "users.db")
    user = store.get_user("admin")

    dialog = BulkDialog(user, store, [], {}, set())
    qtbot.addWidget(dialog)

    calls = []
    monkeypatch.setattr(
        "configgen.ui.bulk_dialog.QMessageBox.warning",
        staticmethod(lambda *a, **k: calls.append(a)),
    )
    dialog._download_template()
    assert calls


def test_only_visible_schemas_are_offered(qtbot, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    root = tmp_path / "project"
    (root / "schemas").mkdir(parents=True)
    (root / "templates").mkdir()
    (root / "templates" / "widget.j2").write_text("{{ name }}", encoding="utf-8")

    published = Schema(
        name="Published Widget",
        id="published_widget",
        status="published",
        template="widget.j2",
        identity_field="name",
        fields=[Field(key="name", label="Name", type="string", required=True)],
    )
    draft = Schema(
        name="Draft Widget",
        id="draft_widget",
        status="draft",
        template="widget.j2",
        identity_field="name",
        fields=[Field(key="name", label="Name", type="string", required=True)],
    )
    schema_paths = {
        "published_widget": root / "schemas" / "published.yaml",
        "draft_widget": root / "schemas" / "draft.yaml",
    }

    store = AuthStore(tmp_path / "users.db")
    store.create_user("carol", "hunter22pw", "config_engineer")
    carol = store.get_user("carol")

    dialog = BulkDialog(carol, store, [published, draft], schema_paths, set())
    qtbot.addWidget(dialog)

    ids = {dialog.schema_combo.itemData(i) for i in range(dialog.schema_combo.count())}
    assert ids == {"published_widget"}
