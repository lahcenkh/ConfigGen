"""Login + forced first-login password change (§13.6, §15).

Two stacked pages: credentials, then — only if the account has
`force_password_change` set (true for the bootstrap admin/admin account,
§13.8) — a mandatory new-password page. The dialog only accept()s once
both steps succeed.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from configgen.appinfo import APP_NAME
from configgen.core.auth import AccountLocked, AuthError, AuthStore, InvalidCredentials, User


class LoginWindow(QDialog):
    def __init__(self, store: AuthStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.authenticated_user: User | None = None
        self._pending_user: User | None = None

        self.setWindowTitle(f"{APP_NAME} — Log in")
        self.setModal(True)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_credentials_page())
        self.stack.addWidget(self._build_password_change_page())

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

    def _build_credentials_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)
        layout.addLayout(form)

        self.login_error = QLabel()
        self.login_error.setObjectName("error")
        self.login_error.setVisible(False)
        layout.addWidget(self.login_error)

        login_button = QPushButton("Log in")
        login_button.setDefault(True)
        login_button.clicked.connect(self._attempt_login)
        self.username_input.returnPressed.connect(self._attempt_login)
        self.password_input.returnPressed.connect(self._attempt_login)
        layout.addWidget(login_button)

        return page

    def _build_password_change_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Choose a new password to continue."))

        form = QFormLayout()
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("New password", self.new_password_input)
        form.addRow("Confirm password", self.confirm_password_input)
        layout.addLayout(form)

        self.password_error = QLabel()
        self.password_error.setObjectName("error")
        self.password_error.setVisible(False)
        layout.addWidget(self.password_error)

        set_button = QPushButton("Set password")
        set_button.setDefault(True)
        set_button.clicked.connect(self._attempt_password_change)
        self.confirm_password_input.returnPressed.connect(self._attempt_password_change)
        layout.addWidget(set_button)

        return page

    def _attempt_login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        self.login_error.setVisible(False)
        try:
            user = self.store.authenticate(username, password)
        except AccountLocked as exc:
            locked_until = exc.locked_until.strftime("%H:%M:%S")
            self._show_login_error(f"Account locked until {locked_until}.")
            return
        except InvalidCredentials:
            self._show_login_error("Invalid username or password.")
            return

        if user.force_password_change:
            self._pending_user = user
            self.stack.setCurrentIndex(1)
            return

        self.authenticated_user = user
        self.accept()

    def _attempt_password_change(self) -> None:
        new_password = self.new_password_input.text()
        confirm = self.confirm_password_input.text()
        self.password_error.setVisible(False)
        if new_password != confirm:
            self._show_password_error("Passwords do not match.")
            return
        try:
            self.store.change_password(self._pending_user.username, new_password)
        except AuthError as exc:
            self._show_password_error(str(exc))
            return
        self.authenticated_user = self.store.get_user(self._pending_user.username)
        self.accept()

    def _show_login_error(self, message: str) -> None:
        self.login_error.setText(message)
        self.login_error.setVisible(True)

    def _show_password_error(self, message: str) -> None:
        self.password_error.setText(message)
        self.password_error.setVisible(True)
