"""Persistent left nav rail (§15 GUI redesign) — replaces the old top
QToolBar. Role-gating here is the same logic that used to live in
Dashboard._build_header(), just relocated: the sidebar is built once at
MainWindow startup and never rebuilt, since a user's role can't change
mid-session (unlike Dashboard's tile grid, which does get rebuilt after
template/bulk/import round-trips).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget

from configgen.appinfo import APP_NAME
from configgen.core.auth import ROLE_TEMPLATE_ENGINEER, User
from configgen.ui import theme


class Sidebar(QWidget):
    homeRequested = Signal()
    templateEditorRequested = Signal()
    userAdminRequested = Signal()
    importConfigPackRequested = Signal()
    bulkGenerateRequested = Signal()
    generationLogRequested = Signal()
    aboutRequested = Signal()
    darkModeToggled = Signal(bool)
    autoUpdateToggled = Signal(bool)

    def __init__(
        self,
        user: User,
        palette: theme.Palette,
        *,
        dark: bool,
        auto_update_check: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.user = user
        self.setObjectName("sidebar")
        self.setFixedWidth(theme.SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        app_name = QLabel(APP_NAME)
        app_name.setObjectName("headline-md")
        header_layout.addWidget(app_name)
        role_label = QLabel(user.role.replace("_", " ").upper())
        role_label.setObjectName("muted")
        header_layout.addWidget(role_label)
        layout.addWidget(header)

        self._add_nav_item(layout, "Home", self.homeRequested)
        if user.is_admin or user.role == ROLE_TEMPLATE_ENGINEER:
            self._add_nav_item(layout, "Template Editor", self.templateEditorRequested)
            self._add_nav_item(layout, "Generation Log", self.generationLogRequested)
        if user.is_admin:
            self._add_nav_item(layout, "User Admin", self.userAdminRequested)
            self._add_nav_item(layout, "Import Config Pack", self.importConfigPackRequested)
        self._add_nav_item(layout, "Bulk Generate", self.bulkGenerateRequested)

        layout.addStretch()

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 8, 16, 12)
        bottom_layout.setSpacing(6)

        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.dark_mode_checkbox.setChecked(dark)
        self.dark_mode_checkbox.toggled.connect(self.darkModeToggled)
        bottom_layout.addWidget(self.dark_mode_checkbox)

        self.auto_update_checkbox = QCheckBox("Check for Updates")
        self.auto_update_checkbox.setChecked(auto_update_check)
        self.auto_update_checkbox.toggled.connect(self.autoUpdateToggled)
        bottom_layout.addWidget(self.auto_update_checkbox)

        about_button = QPushButton("About")
        about_button.setObjectName("secondary")
        about_button.clicked.connect(self.aboutRequested)
        bottom_layout.addWidget(about_button)

        layout.addWidget(bottom)

    def _add_nav_item(self, layout: QVBoxLayout, label: str, signal) -> None:
        button = QPushButton(label)
        button.setObjectName("nav-item")
        button.clicked.connect(signal)
        layout.addWidget(button)
