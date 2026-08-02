"""Persistent left nav rail (§15 GUI redesign) — replaces the old top
QToolBar. Role-gating here is the same logic that used to live in
Dashboard._build_header(), just relocated: the sidebar is built once at
MainWindow startup and never rebuilt, since a user's role can't change
mid-session (unlike Dashboard's tile grid, which does get rebuilt after
template/bulk/import round-trips).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from configgen.appinfo import APP_NAME, __version__
from configgen.core.auth import ROLE_TEMPLATE_ENGINEER, User
from configgen.ui import icons, theme
from configgen.ui.widgets import ToggleSwitch

_NAV_ICON_SIZE = QSize(14, 14)


def _eyebrow(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("label-sm")
    font = label.font()
    font.setFamily(theme.MONO_FONT_FAMILY)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
    label.setFont(font)
    label.setContentsMargins(10, 0, 0, 0)
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setObjectName("divider")
    return line


class Sidebar(QWidget):
    homeRequested = Signal()
    templateEditorRequested = Signal()
    userAdminRequested = Signal()
    importConfigPackRequested = Signal()
    bulkGenerateRequested = Signal()
    generationLogRequested = Signal()
    aboutRequested = Signal()
    highlightRulesRequested = Signal()
    logoutRequested = Signal()
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
        self._palette = palette
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_icon_fns: dict[str, Callable[[str], QIcon]] = {}
        self.setObjectName("sidebar")
        self.setFixedWidth(theme.SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_user_row())

        nav_column = QVBoxLayout()
        nav_column.setContentsMargins(10, 8, 10, 8)
        nav_column.setSpacing(2)

        nav_column.addWidget(_eyebrow("Workspace"))
        self._add_nav_item(nav_column, "home", "Home", icons.home_icon, self.homeRequested)
        if user.is_admin or user.role == ROLE_TEMPLATE_ENGINEER:
            self._add_nav_item(
                nav_column,
                "template_editor",
                "Template Editor",
                icons.template_icon,
                self.templateEditorRequested,
            )
            self._add_nav_item(
                nav_column,
                "generation_log",
                "Generation Log",
                icons.log_icon,
                self.generationLogRequested,
            )
        self._add_nav_item(
            nav_column,
            "bulk_generate",
            "Bulk Generate",
            icons.bulk_icon,
            self.bulkGenerateRequested,
        )

        if user.is_admin:
            nav_column.addSpacing(12)
            nav_column.addWidget(_eyebrow("Administration"))
            self._add_nav_item(
                nav_column, "user_admin", "User Admin", icons.person_icon, self.userAdminRequested
            )
            self._add_nav_item(
                nav_column,
                "import_config_pack",
                "Import Config Pack",
                icons.import_icon,
                self.importConfigPackRequested,
            )

        layout.addLayout(nav_column)
        layout.addStretch()
        layout.addWidget(self._build_footer(dark, auto_update_check))

        self._set_active("home")
        self.homeRequested.connect(lambda: self._set_active("home"))

    def _build_user_row(self) -> QWidget:
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(16, 16, 16, 16)
        row_layout.setSpacing(10)

        app_name = QLabel(APP_NAME)
        app_name.setObjectName("headline-lg")
        row_layout.addWidget(app_name)

        identity_row = QHBoxLayout()
        identity_row.setSpacing(8)

        self._avatar = QLabel(self.user.username[:1].upper())
        self._avatar.setFixedSize(24, 24)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity_row.addWidget(self._avatar)

        username = QLabel(self.user.username)
        identity_row.addWidget(username, stretch=1)

        self._role_chip = QLabel(self.user.role.replace("_", " ").upper())
        identity_row.addWidget(self._role_chip)
        self._style_identity_chips()

        row_layout.addLayout(identity_row)
        return row

    def _style_identity_chips(self) -> None:
        self._avatar.setStyleSheet(
            f"background-color: {self._palette.accent_tint_bg}; color: {self._palette.accent}; "
            f"border: 1px solid {self._palette.accent_tint_border}; border-radius: 12px; "
            f"font-weight: 700; font-size: 11px;"
        )
        self._role_chip.setStyleSheet(
            f"background-color: {self._palette.surface_container_high}; "
            f"color: {self._palette.text_tertiary}; border: 1px solid {self._palette.border}; "
            f"border-radius: {theme.RADIUS_SM}; padding: 1px 6px; font-size: 9px; font-weight: 700;"
        )

    def _add_nav_item(self, layout: QVBoxLayout, route: str, label: str, icon_fn, signal) -> None:
        button = QPushButton(icon_fn(self._palette.text_muted), label)
        button.setIconSize(_NAV_ICON_SIZE)
        button.setObjectName("nav-item")
        button.setProperty("active", False)
        button.clicked.connect(signal)
        layout.addWidget(button)
        self._nav_buttons[route] = button
        self._nav_icon_fns[route] = icon_fn

    def _set_active(self, route: str) -> None:
        for name, button in self._nav_buttons.items():
            button.setProperty("active", name == route)
            style = button.style()
            style.unpolish(button)
            style.polish(button)

    def _build_footer(self, dark: bool, auto_update_check: bool) -> QWidget:
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(16, 8, 16, 12)
        footer_layout.setSpacing(8)

        dark_row = QHBoxLayout()
        dark_row.addWidget(QLabel("Dark mode"))
        dark_row.addStretch()
        self.dark_mode_checkbox = ToggleSwitch(self._palette)
        self.dark_mode_checkbox.setChecked(dark)
        self.dark_mode_checkbox.toggled.connect(self.darkModeToggled)
        dark_row.addWidget(self.dark_mode_checkbox)
        footer_layout.addLayout(dark_row)

        update_row = QHBoxLayout()
        update_row.addWidget(QLabel("Check for updates"))
        update_row.addStretch()
        self.auto_update_checkbox = ToggleSwitch(self._palette)
        self.auto_update_checkbox.setChecked(auto_update_check)
        self.auto_update_checkbox.toggled.connect(self.autoUpdateToggled)
        update_row.addWidget(self.auto_update_checkbox)
        footer_layout.addLayout(update_row)

        footer_layout.addWidget(_divider())

        version_row = QHBoxLayout()
        version = QLabel(f"build {__version__}")
        version.setObjectName("faint")
        version_row.addWidget(version)
        version_row.addStretch()
        footer_layout.addLayout(version_row)

        highlight_rules_button = QPushButton("Highlight Rules")
        highlight_rules_button.setObjectName("secondary")
        highlight_rules_button.clicked.connect(self.highlightRulesRequested)
        footer_layout.addWidget(highlight_rules_button)

        about_button = QPushButton("About")
        about_button.setObjectName("secondary")
        about_button.clicked.connect(self.aboutRequested)
        footer_layout.addWidget(about_button)

        logout_button = QPushButton("Log Out")
        logout_button.setObjectName("danger")
        logout_button.clicked.connect(self.logoutRequested)
        footer_layout.addWidget(logout_button)

        return footer

    def refresh_palette(self, palette: theme.Palette) -> None:
        """Re-tints the palette-aware bits that live outside the global
        stylesheet (avatar/role chip inline styles, toggle knobs) — same
        reason `tile_style()`/`GeneratorView.refresh_palette` exist."""
        self._palette = palette
        self.dark_mode_checkbox.set_palette(palette)
        self.auto_update_checkbox.set_palette(palette)
        self._style_identity_chips()
        for route, button in self._nav_buttons.items():
            button.setIcon(self._nav_icon_fns[route](palette.text_muted))
