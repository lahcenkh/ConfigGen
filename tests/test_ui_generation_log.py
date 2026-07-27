from pathlib import Path

from PySide6.QtWidgets import QDialog

from configgen.core.auth import AuthStore
from configgen.ui.generation_log import GenerationLogDialog


def _store_with_entries(tmp_path: Path):
    store = AuthStore(tmp_path / "users.db")
    admin = store.authenticate("admin", "admin")
    store.create_user("carol", "hunter22pw", "config_engineer")
    carol = store.authenticate("carol", "hunter22pw")

    store.record_generation(
        carol,
        schema_id="router_base",
        schema_version=1,
        form_inputs={"hostname": "r1"},
        output_filename="r1.txt",
        group_name="NetworkTeam",
    )
    store.record_generation(
        admin,
        schema_id="switch_base",
        schema_version=2,
        form_inputs={"hostname": "s1"},
        output_filename="s1.txt",
    )
    return store, admin, carol


def test_admin_sees_all_entries(qtbot, tmp_path: Path):
    store, admin, _carol = _store_with_entries(tmp_path)
    dialog = GenerationLogDialog(store, admin)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 2


def test_config_engineer_sees_only_own_entries(qtbot, tmp_path: Path):
    store, _admin, carol = _store_with_entries(tmp_path)
    dialog = GenerationLogDialog(store, carol)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "carol"


def test_user_filter_narrows_rows(qtbot, tmp_path: Path):
    store, admin, _carol = _store_with_entries(tmp_path)
    dialog = GenerationLogDialog(store, admin)
    qtbot.addWidget(dialog)

    dialog.user_filter.setCurrentText("carol")
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 3).text() == "router_base"


def test_schema_filter_narrows_rows(qtbot, tmp_path: Path):
    store, admin, _carol = _store_with_entries(tmp_path)
    dialog = GenerationLogDialog(store, admin)
    qtbot.addWidget(dialog)

    dialog.schema_filter.setCurrentText("switch_base")
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "admin"


def test_group_filter_narrows_rows(qtbot, tmp_path: Path):
    store, admin, _carol = _store_with_entries(tmp_path)
    dialog = GenerationLogDialog(store, admin)
    qtbot.addWidget(dialog)

    dialog.group_filter.setCurrentText("NetworkTeam")
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 3).text() == "router_base"


def test_regenerate_emits_schema_id_and_form_inputs(qtbot, tmp_path: Path):
    store, admin, _carol = _store_with_entries(tmp_path)
    dialog = GenerationLogDialog(store, admin)
    qtbot.addWidget(dialog)

    captured = {}
    dialog.regenerateRequested.connect(
        lambda schema_id, inputs: captured.update(schema_id=schema_id, inputs=inputs)
    )

    sub_dialog = QDialog()
    dialog._regenerate("switch_base", {"hostname": "s1"}, sub_dialog)

    assert captured == {"schema_id": "switch_base", "inputs": {"hostname": "s1"}}
    assert sub_dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_show_selected_parses_form_inputs_json(qtbot, tmp_path: Path, monkeypatch):
    store, admin, _carol = _store_with_entries(tmp_path)
    dialog = GenerationLogDialog(store, admin)
    qtbot.addWidget(dialog)

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    dialog.table.selectRow(0)
    dialog._show_selected()  # should not raise; exercises the JSON round-trip
