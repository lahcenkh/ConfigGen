from pathlib import Path

from configgen.core.auth import AuthStore
from configgen.ui.login_window import LoginWindow


def _store(tmp_path: Path) -> AuthStore:
    return AuthStore(tmp_path / "users.db")


def test_wrong_password_shows_error_and_stays_on_credentials_page(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    login = LoginWindow(store)
    qtbot.addWidget(login)

    login.username_input.setText("admin")
    login.password_input.setText("wrong-password")
    login._attempt_login()

    assert login.stack.currentIndex() == 0
    assert login.login_error.text() == "Invalid username or password."
    assert login.authenticated_user is None


def test_unknown_user_shows_same_generic_error(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    login = LoginWindow(store)
    qtbot.addWidget(login)

    login.username_input.setText("ghost")
    login.password_input.setText("whatever1")
    login._attempt_login()

    assert login.login_error.text() == "Invalid username or password."


def test_lockout_shows_locked_message(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    for _ in range(5):
        try:
            store.authenticate("carol", "wrong-password")
        except Exception:
            pass

    login = LoginWindow(store)
    qtbot.addWidget(login)
    login.username_input.setText("carol")
    login.password_input.setText("hunter22pw")
    login._attempt_login()

    assert "locked" in login.login_error.text().lower()


def test_bootstrap_admin_login_requires_password_change(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    login = LoginWindow(store)
    qtbot.addWidget(login)

    login.username_input.setText("admin")
    login.password_input.setText("admin")
    login._attempt_login()

    assert login.stack.currentIndex() == 1  # forced password-change page
    assert login.authenticated_user is None


def test_password_change_mismatch_shows_error(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    login = LoginWindow(store)
    qtbot.addWidget(login)
    login.username_input.setText("admin")
    login.password_input.setText("admin")
    login._attempt_login()

    login.new_password_input.setText("newpassword1")
    login.confirm_password_input.setText("different1")
    login._attempt_password_change()

    assert login.password_error.text() == "Passwords do not match."
    assert login.authenticated_user is None


def test_password_change_too_short_shows_auth_error(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    login = LoginWindow(store)
    qtbot.addWidget(login)
    login.username_input.setText("admin")
    login.password_input.setText("admin")
    login._attempt_login()

    login.new_password_input.setText("short")
    login.confirm_password_input.setText("short")
    login._attempt_password_change()

    assert login.password_error.isVisible() or login.password_error.text()
    assert login.authenticated_user is None


def test_successful_password_change_completes_login(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    login = LoginWindow(store)
    qtbot.addWidget(login)
    login.username_input.setText("admin")
    login.password_input.setText("admin")
    login._attempt_login()

    login.new_password_input.setText("newpassword1")
    login.confirm_password_input.setText("newpassword1")
    login._attempt_password_change()

    assert login.authenticated_user is not None
    assert login.authenticated_user.username == "admin"
    assert store.authenticate("admin", "newpassword1").username == "admin"


def test_normal_user_login_does_not_require_password_change(qtbot, tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    login = LoginWindow(store)
    qtbot.addWidget(login)

    login.username_input.setText("carol")
    login.password_input.setText("hunter22pw")
    login._attempt_login()

    assert login.authenticated_user is not None
    assert login.authenticated_user.username == "carol"
