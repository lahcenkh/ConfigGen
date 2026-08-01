"""Login + forced first-login password change (§13.6, §15).

Two stacked pages: credentials, then — only if the account has
`force_password_change` set (true for the bootstrap admin/admin account,
§13.8) — a mandatory new-password page. The dialog only accept()s once
both steps succeed.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from configgen.appinfo import APP_NAME, __version__
from configgen.core.auth import AccountLocked, AuthError, AuthStore, InvalidCredentials, User
from configgen.ui import theme
from configgen.ui.icons import eye_icon, lock_icon, person_icon

_CARD_WIDTH = 380


def _field_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("label-sm")
    return label


class LoginWindow(QDialog):
    def __init__(self, store: AuthStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.authenticated_user: User | None = None
        self._pending_user: User | None = None

        self.setWindowTitle(f"{APP_NAME} — Log in")
        self.setModal(True)
        # Fixed, not just an initial resize() — a resizable login dialog can
        # be dragged smaller than the card's own minimum size, which jams
        # the card against the window edges and clips the status bar
        # entirely (nothing forces this window back to a sane size).
        self.setFixedSize(520, 640)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_credentials_page())
        self.stack.addWidget(self._build_password_change_page())

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(_CARD_WIDTH)
        card_layout = QVBoxLayout(card)

        title = QLabel(APP_NAME)
        title.setObjectName("headline-lg")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        subtitle = QLabel("Network Infrastructure Portal")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(subtitle)

        card_layout.addWidget(self.stack)

        outer = QVBoxLayout(self)
        outer.addStretch()
        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()
        outer.addLayout(self._build_status_bar())

    def _build_status_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        ready = QLabel("● System Ready")
        ready.setObjectName("muted")
        bar.addWidget(ready)

        version = QLabel(f"v{__version__}")
        version.setObjectName("muted")
        bar.addWidget(version)

        bar.addStretch()

        secure = QLabel("Local authentication")
        secure.setObjectName("muted")
        bar.addWidget(secure)
        return bar

    def _build_credentials_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        self.login_error_box = QFrame()
        self.login_error_box.setObjectName("alert-danger")
        self.login_error_box.setVisible(False)
        error_layout = QHBoxLayout(self.login_error_box)
        warning_icon = QLabel()
        warning_icon.setPixmap(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(18, 18)
        )
        error_layout.addWidget(warning_icon, alignment=Qt.AlignmentFlag.AlignTop)
        self.login_error = QLabel()
        self.login_error.setObjectName("error")
        self.login_error.setWordWrap(True)
        self.login_error.setVisible(False)
        error_layout.addWidget(self.login_error, stretch=1)
        layout.addWidget(self.login_error_box)

        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(12)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g. admin")
        self.username_input.addAction(
            person_icon(theme.DARK.text_muted), QLineEdit.ActionPosition.LeadingPosition
        )
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.addAction(
            lock_icon(theme.DARK.text_muted), QLineEdit.ActionPosition.LeadingPosition
        )
        self._password_visible = False
        self._toggle_password_action = self.password_input.addAction(
            eye_icon(theme.DARK.text_muted, visible=False),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._toggle_password_action.triggered.connect(self._toggle_password_visibility)
        form.addRow(_field_label("Username"), self.username_input)
        form.addRow(_field_label("Password"), self.password_input)
        layout.addLayout(form)

        login_button = QPushButton("Log in  →")
        login_button.setDefault(True)
        login_button.clicked.connect(self._attempt_login)
        self.username_input.returnPressed.connect(self._attempt_login)
        self.password_input.returnPressed.connect(self._attempt_login)
        layout.addWidget(login_button)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("divider")
        layout.addWidget(divider)

        links_row = QHBoxLayout()
        first_time = QLabel("First-time login? Use the password your admin gave you.")
        first_time.setObjectName("muted")
        first_time.setWordWrap(True)
        links_row.addWidget(first_time, stretch=1)

        forgot = QLabel("Forgot password? Ask your admin.")
        forgot.setObjectName("muted")
        forgot.setAlignment(Qt.AlignmentFlag.AlignRight)
        links_row.addWidget(forgot)
        layout.addLayout(links_row)

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
        form.addRow(_field_label("New password"), self.new_password_input)
        form.addRow(_field_label("Confirm password"), self.confirm_password_input)
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
        self.login_error_box.setVisible(False)
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

    def _toggle_password_visibility(self) -> None:
        self._password_visible = not self._password_visible
        self.password_input.setEchoMode(
            QLineEdit.EchoMode.Normal if self._password_visible else QLineEdit.EchoMode.Password
        )
        self._toggle_password_action.setIcon(
            eye_icon(theme.DARK.text_muted, visible=self._password_visible)
        )

    def _show_login_error(self, message: str) -> None:
        self.login_error.setText(message)
        self.login_error.setVisible(True)
        self.login_error_box.setVisible(True)

    def _show_password_error(self, message: str) -> None:
        self.password_error.setText(message)
        self.password_error.setVisible(True)
