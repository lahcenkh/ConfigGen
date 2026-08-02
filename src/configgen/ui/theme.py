"""Design tokens + stylesheets + dark mode (§15 of the build plan).

"Mono/Mint": a cool-neutral, near-zero-chroma dark-first visual language
with a single accent (mint) — depth comes from tonal layering
(surface_container_* ramp) and 1px borders, never shadows. Light mode
follows the same structural rules with an independently derived palette.

Semantic state colors (danger/success/warning) are kept as real hues —
the design brief's "no second hue" rule is about decorative/branding
accent usage, not about being able to show a login error or a validation
failure, which still need to read as unambiguously "wrong" regardless of
the neutral+mint palette around them.

Per-group accent colours and tile backgrounds are data a group/schema
record supplies (a hex string), never a hardcoded per-group branch here —
see `tile_style`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

APP_ORG = "ConfigGen"
APP_NAME = "ConfigGen"


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    surface_container_lowest: str
    surface_container_low: str
    surface_container: str
    surface_container_high: str
    surface_container_highest: str
    text: str
    text_muted: str
    text_tertiary: str
    text_faint: str
    border: str
    border_strong: str
    border_hover: str
    accent: str
    accent_hover: str
    accent_fill: str
    accent_fill_text: str
    accent_tint_bg: str
    accent_tint_border: str
    danger: str
    danger_container: str
    success: str
    warning: str
    mono_text: str
    syntax_keyword: str
    syntax_string: str


LIGHT = Palette(
    background="#e6eae8",
    surface="#ffffff",
    surface_container_lowest="#ffffff",
    surface_container_low="#ffffff",
    surface_container="#ffffff",
    surface_container_high="#eef1ef",
    surface_container_highest="#dfe4e1",
    text="#121512",
    text_muted="#5b6560",
    text_tertiary="#77827c",
    text_faint="#9aa39e",
    border="#d3d9d6",
    border_strong="#bcc4c0",
    border_hover="#9aa39e",
    accent="#1f8f5f",
    accent_hover="#177349",
    accent_fill="#1f8f5f",
    accent_fill_text="#ffffff",
    accent_tint_bg="#dbf0e6",
    accent_tint_border="#a6ddc0",
    danger="#dc2626",
    danger_container="#fee2e2",
    success="#059669",
    warning="#d97706",
    mono_text="#121512",
    syntax_keyword="#1f8f5f",
    syntax_string="#121512",
)

DARK = Palette(
    background="#0a0c0b",
    surface="#0d100f",
    surface_container_lowest="#101413",
    surface_container_low="#0d100f",
    surface_container="#101413",
    surface_container_high="#121716",
    surface_container_highest="#171d1b",
    text="#e6ebe8",
    text_muted="#8b968f",
    text_tertiary="#6f7a75",
    text_faint="#4e5a55",
    border="#171d1b",
    border_strong="#1c2320",
    border_hover="#2c3733",
    accent="#5fd6a4",
    accent_hover="#7ce0b5",
    accent_fill="#5fd6a4",
    accent_fill_text="#06120d",
    accent_tint_bg="#152420",
    accent_tint_border="#1f3630",
    danger="#ffb4ab",
    danger_container="#93000a",
    success="#10b981",
    warning="#f59e0b",
    mono_text="#e6ebe8",
    syntax_keyword="#5fd6a4",
    syntax_string="#e6ebe8",
)

FONT_FAMILY = '"IBM Plex Sans", "Segoe UI", Arial, sans-serif'
MONO_FONT_FAMILY = '"IBM Plex Mono", "Cascadia Mono", "Consolas", monospace'
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
SIDEBAR_WIDTH = 212
RADIUS_SM = "5px"  # chips
RADIUS_MD = "7px"  # controls, rows
RADIUS_LG = "9px"  # cards, panels


def palette_for(dark: bool) -> Palette:
    return DARK if dark else LIGHT


def stylesheet(palette: Palette) -> str:
    """The app-wide QSS for a given palette. Anything widget-specific (a
    tile's accent colour, a field's error border) layers on top via that
    widget's own setStyleSheet — never by editing this.

    Borders do the work shadows normally would: every surface is flat,
    depth comes only from the surface_container_* tonal ramp and 1px
    borders. Radii follow the three-tier scale (`RADIUS_SM`/`MD`/`LG`).
    """
    return f"""
    QWidget {{
        background-color: {palette.background};
        color: {palette.text};
        font-family: {FONT_FAMILY};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background-color: {palette.background};
    }}
    QLabel {{
        background-color: transparent;
    }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
        background-color: {palette.surface_container};
        color: {palette.text};
        border: 1px solid {palette.border_strong};
        border-radius: {RADIUS_MD};
        padding: 4px 6px;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        min-height: 22px;
        padding: 4px 10px;
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QPlainTextEdit:hover {{
        border: 1px solid {palette.border_hover};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {palette.accent};
    }}
    QLineEdit[hasError="true"], QComboBox[hasError="true"],
    QSpinBox[hasError="true"], QPlainTextEdit[hasError="true"] {{
        border: 1.5px solid {palette.danger};
    }}
    QPushButton {{
        background-color: {palette.accent_fill};
        color: {palette.accent_fill_text};
        border: none;
        border-radius: {RADIUS_MD};
        padding: 5px 14px;
        min-height: 22px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {palette.accent_hover};
    }}
    QPushButton:disabled {{
        background-color: {palette.surface_container_high};
        color: {palette.text_faint};
    }}
    QPushButton#secondary {{
        background-color: transparent;
        color: {palette.text};
        border: 1px solid {palette.border_strong};
        border-radius: {RADIUS_MD};
    }}
    QPushButton#secondary:hover {{
        border: 1px solid {palette.border_hover};
        background-color: {palette.surface_container_high};
    }}
    QPushButton#danger {{
        background-color: transparent;
        color: {palette.danger};
        border: 1px solid {palette.danger};
        border-radius: {RADIUS_MD};
    }}
    QPushButton#ghost-accent {{
        background-color: transparent;
        color: {palette.accent};
        border: 1px solid {palette.accent_tint_border};
        border-radius: {RADIUS_MD};
        padding: 2px 10px;
        min-height: 18px;
        font-weight: 600;
    }}
    QPushButton#ghost-accent:hover {{
        background-color: {palette.accent_fill};
        color: {palette.accent_fill_text};
        border: 1px solid {palette.accent_fill};
    }}
    QWidget#sidebar {{
        background-color: {palette.surface_container_low};
        border-right: 1px solid {palette.border};
    }}
    QPushButton#nav-item {{
        background-color: transparent;
        color: {palette.text_muted};
        border: none;
        border-left: 2px solid transparent;
        border-radius: {RADIUS_MD};
        text-align: left;
        padding: 8px 10px;
        min-height: 20px;
        font-weight: 400;
    }}
    QPushButton#nav-item:hover {{
        background-color: {palette.surface_container_high};
        color: {palette.text};
    }}
    QPushButton#nav-item[active="true"] {{
        background-color: {palette.accent_tint_bg};
        color: {palette.text};
        border-left: 2px solid {palette.accent};
        font-weight: 600;
    }}
    QLabel#error {{
        color: {palette.danger};
    }}
    QFrame#alert-danger {{
        background-color: {palette.danger_container};
        border: 1px solid {palette.danger};
        border-radius: {RADIUS_MD};
    }}
    QFrame#alert-danger QLabel#error {{
        color: {palette.text};
    }}
    QLabel#muted {{
        color: {palette.text_muted};
    }}
    QLabel#tertiary {{
        color: {palette.text_tertiary};
    }}
    QLabel#faint {{
        color: {palette.text_faint};
    }}
    QLabel#headline-lg {{
        font-size: 18px;
        font-weight: 600;
    }}
    QLabel#headline-md {{
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#label-sm {{
        font-size: 10px;
        font-weight: 600;
        color: {palette.text_muted};
    }}
    QFrame#divider {{
        background-color: {palette.border};
        max-height: 1px;
        border: none;
    }}
    QFrame#tile, QFrame#card {{
        background-color: {palette.surface_container};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_LG};
    }}
    QFrame#tile:hover {{
        background-color: {palette.surface_container_high};
        border: 1px solid {palette.border_hover};
    }}
    QFrame#panel {{
        background-color: {palette.surface};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_LG};
    }}
    QFrame#chip, QLabel#chip {{
        background-color: transparent;
        color: {palette.text_tertiary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 1px 6px;
        font-size: 10px;
    }}
    QFrame#activity-row {{
        background-color: transparent;
        border: none;
        border-radius: {RADIUS_MD};
    }}
    QFrame#activity-row:hover {{
        background-color: {palette.surface_container_high};
    }}
    QListWidget#schema-list {{
        background-color: {palette.surface_container_low};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_LG};
        padding: 6px;
        outline: none;
    }}
    QListWidget#schema-list::item {{
        color: {palette.text_muted};
        border-radius: {RADIUS_MD};
        padding: 8px 10px;
    }}
    QListWidget#schema-list::item:hover {{
        background-color: {palette.surface_container_high};
        color: {palette.text};
    }}
    QListWidget#schema-list::item:selected {{
        background-color: {palette.accent_tint_bg};
        color: {palette.accent};
        font-weight: 600;
    }}
    QTabWidget::pane {{
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
    }}
    QTabBar::tab {{
        background-color: {palette.surface_container_low};
        color: {palette.text_muted};
        border: 1px solid {palette.border};
        border-bottom: none;
        border-top-left-radius: {RADIUS_MD};
        border-top-right-radius: {RADIUS_MD};
        padding: 6px 12px;
    }}
    QTabBar::tab:selected {{
        background-color: {palette.surface_container_high};
        color: {palette.accent};
        border-bottom: 2px solid {palette.accent};
    }}
    QTableWidget, QTableView {{
        background-color: {palette.surface_container_lowest};
        alternate-background-color: {palette.surface_container_high};
        gridline-color: {palette.border};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_LG};
    }}
    QHeaderView::section {{
        background-color: {palette.surface_container_high};
        color: {palette.text_muted};
        border: none;
        border-bottom: 1px solid {palette.border_strong};
        padding: 4px 6px;
        font-weight: 700;
    }}
    QGroupBox {{
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
        margin-top: 10px;
        padding-top: 8px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: {palette.text_muted};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
    }}
    QScrollBar::handle:vertical {{
        background: {palette.border_hover};
        border-radius: {RADIUS_SM};
        min-height: 24px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
    }}
    QScrollBar::handle:horizontal {{
        background: {palette.border_hover};
        border-radius: {RADIUS_SM};
        min-width: 24px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0;
        width: 0;
    }}
    QMenu {{
        background-color: {palette.surface_container};
        color: {palette.text};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
    }}
    QMenu::item:selected {{
        background-color: {palette.surface_container_highest};
        border-radius: {RADIUS_SM};
    }}
    QToolTip {{
        background-color: {palette.surface_container_high};
        color: {palette.text};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 2px 4px;
    }}
    """


def tile_style(palette: Palette, accent_hex: str | None = None) -> str:
    """A tile's accent stripe colour is data the caller supplies (e.g. a
    group's own `accent_hex`), falling back to the palette's own accent."""
    accent = accent_hex or palette.accent
    return (
        f"QFrame#tile {{ background-color: {palette.surface_container}; "
        f"border: 1px solid {palette.border}; border-left: 4px solid {accent}; "
        f"border-radius: {RADIUS_LG}; }}"
    )


def _settings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def load_dark_mode(username: str) -> bool:
    """Dark mode is persisted per authenticated user (§15), not globally —
    two people sharing a machine keep their own preference."""
    return bool(_settings().value(f"dark_mode/{username}", False, type=bool))


def save_dark_mode(username: str, enabled: bool) -> None:
    _settings().setValue(f"dark_mode/{username}", enabled)
