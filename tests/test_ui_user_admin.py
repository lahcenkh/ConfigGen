from pathlib import Path

from PySide6.QtWidgets import QDialog, QMessageBox

from configgen.core.auth import AuthStore
from configgen.ui.user_admin import CreateUserDialog, UserAdminWindow


def _store(tmp_path: Path) -> AuthStore:
    return AuthStore(tmp_path / "users.db")


def _window(tmp_path: Path, qtbot) -> tuple[UserAdminWindow, AuthStore]:
    store = _store(tmp_path)
    admin = store.authenticate("admin", "admin")
    window = UserAdminWindow(store, admin)
    qtbot.addWidget(window)
    return window, store


# -- users ---------------------------------------------------------


def test_lists_existing_users_on_open(qtbot, tmp_path: Path):
    window, store = _window(tmp_path, qtbot)
    assert window.users_table.rowCount() == 1
    assert window.users_table.item(0, 0).text() == "admin"


def test_create_user_dialog_reports_entered_values(qtbot):
    dialog = CreateUserDialog()
    qtbot.addWidget(dialog)
    dialog.username_input.setText("bob")
    dialog.password_input.setText("hunter22pw")
    dialog.role_input.setCurrentText("config_engineer")
    assert dialog.values() == ("bob", "hunter22pw", "config_engineer")


def test_create_user_adds_a_row(qtbot, tmp_path: Path, monkeypatch):
    window, store = _window(tmp_path, qtbot)
    monkeypatch.setattr(
        "configgen.ui.user_admin.CreateUserDialog.exec",
        lambda self: QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(
        "configgen.ui.user_admin.CreateUserDialog.values",
        lambda self: ("bob", "hunter22pw", "config_engineer"),
    )
    window._create_user()
    assert store.get_user("bob") is not None
    assert window.users_table.rowCount() == 2


def test_change_role_updates_store(qtbot, tmp_path: Path, monkeypatch):
    window, store = _window(tmp_path, qtbot)
    store.create_user("bob", "hunter22pw", "config_engineer")
    window.refresh_users()
    window.users_table.selectRow(1 if window.users_table.item(0, 0).text() == "admin" else 0)

    monkeypatch.setattr(
        "configgen.ui.user_admin.QInputDialog.getItem",
        staticmethod(lambda *a, **k: ("template_engineer", True)),
    )
    window._change_role()
    assert store.get_user("bob").role == "template_engineer"


def test_delete_user_removes_row(qtbot, tmp_path: Path, monkeypatch):
    window, store = _window(tmp_path, qtbot)
    store.create_user("bob", "hunter22pw", "config_engineer")
    window.refresh_users()
    row = 0 if window.users_table.item(0, 0).text() == "bob" else 1
    window.users_table.selectRow(row)

    monkeypatch.setattr(
        "configgen.ui.user_admin.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    window._delete_user()
    assert store.get_user("bob") is None
    assert window.users_table.rowCount() == 1


def test_cannot_delete_own_account(qtbot, tmp_path: Path, monkeypatch):
    window, store = _window(tmp_path, qtbot)
    window.users_table.selectRow(0)  # admin, the actor's own row

    calls = []
    monkeypatch.setattr(
        "configgen.ui.user_admin.QMessageBox.warning",
        staticmethod(lambda *a, **k: calls.append(a)),
    )
    window._delete_user()
    assert calls
    assert store.get_user("admin") is not None


# -- groups ---------------------------------------------------------


def test_create_group_and_add_member(qtbot, tmp_path: Path, monkeypatch):
    window, store = _window(tmp_path, qtbot)
    store.create_user("bob", "hunter22pw", "config_engineer")

    monkeypatch.setattr(
        "configgen.ui.user_admin.QInputDialog.getText",
        staticmethod(lambda *a, **k: ("NetworkTeam", True)),
    )
    window._create_group()
    assert window.groups_table.rowCount() == 1

    window.groups_table.selectRow(0)
    monkeypatch.setattr(
        "configgen.ui.user_admin.QInputDialog.getItem",
        staticmethod(lambda *a, **k: ("bob", True)),
    )
    window._add_member()
    assert store.groups_for_user("bob") == {"NetworkTeam"}
    assert window.members_table.rowCount() == 1


def test_remove_member(qtbot, tmp_path: Path, monkeypatch):
    window, store = _window(tmp_path, qtbot)
    store.create_user("bob", "hunter22pw", "config_engineer")
    store.create_group("NetworkTeam")
    store.assign_user_to_group("bob", "NetworkTeam")
    window.refresh_groups()
    window.groups_table.selectRow(0)
    window.members_table.selectRow(0)

    window._remove_member()
    assert store.groups_for_user("bob") == set()


# -- API keys ---------------------------------------------------------


def test_create_api_key_lists_it_active(qtbot, tmp_path: Path, monkeypatch):
    window, store = _window(tmp_path, qtbot)
    monkeypatch.setattr(
        "configgen.ui.user_admin.QInputDialog.getItem",
        staticmethod(lambda *a, **k: ("admin", True)),
    )
    monkeypatch.setattr(
        "configgen.ui.user_admin.QInputDialog.getText",
        staticmethod(lambda *a, **k: ("CI pipeline", True)),
    )
    shown = []
    monkeypatch.setattr(
        "configgen.ui.user_admin.QMessageBox.information",
        staticmethod(lambda self, title, text: shown.append(text)),
    )
    window._create_api_key()

    assert window.keys_table.rowCount() == 1
    assert window.keys_table.item(0, 1).text() == "admin"
    assert window.keys_table.item(0, 3).text() == "active"
    assert "shown once" in shown[0]


def test_revoke_api_key_updates_status(qtbot, tmp_path: Path):
    window, store = _window(tmp_path, qtbot)
    admin = store.get_user("admin")
    store.create_api_key(admin.username, label="test")
    window.refresh_api_keys()
    window.keys_table.selectRow(0)

    window._revoke_api_key()
    assert window.keys_table.item(0, 3).text() == "revoked"
