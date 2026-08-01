"""Design tokens + stylesheets + dark mode (§15 of the build plan).

"Flat Industrial Precision": a dark-first, softly-rounded, 1px-border
visual language built for network/IT engineers — depth comes from tonal
layering (surface_container_* ramp) and 1px borders, never shadows.
Light mode follows the same structural rules with an independently
derived palette (the corner radii and border-first depth still apply;
the hues differ).

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
    border: str
    border_strong: str
    accent: str
    accent_fill: str
    accent_fill_text: str
    danger: str
    danger_container: str
    success: str
    warning: str
    mono_text: str
    syntax_keyword: str
    syntax_string: str


LIGHT = Palette(
    background="#f5f6f7",
    surface="#ffffff",
    surface_container_lowest="#ffffff",
    surface_container_low="#f0f1f3",
    surface_container="#e8eaed",
    surface_container_high="#dfe2e6",
    surface_container_highest="#d3d7dc",
    text="#131313",
    text_muted="#4b5563",
    border="#d1d5db",
    border_strong="#8a919e",
    accent="#0060ab",
    accent_fill="#0078d4",
    accent_fill_text="#ffffff",
    danger="#dc2626",
    danger_container="#fee2e2",
    success="#059669",
    warning="#d97706",
    mono_text="#2563eb",
    syntax_keyword="#bc5b00",
    syntax_string="#0060ab",
)

DARK = Palette(
    background="#131313",
    surface="#131313",
    surface_container_lowest="#0e0e0e",
    surface_container_low="#1b1b1c",
    surface_container="#202020",
    surface_container_high="#2a2a2a",
    surface_container_highest="#353535",
    text="#e5e2e1",
    text_muted="#c0c7d4",
    border="#404752",
    border_strong="#8a919e",
    accent="#a3c9ff",
    accent_fill="#0078d4",
    accent_fill_text="#ffffff",
    danger="#ffb4ab",
    danger_container="#93000a",
    success="#10b981",
    warning="#f59e0b",
    mono_text="#60a5fa",
    syntax_keyword="#ffb689",
    syntax_string="#a3c9ff",
)

FONT_FAMILY = '"Inter", "Segoe UI", Arial, sans-serif'
MONO_FONT_FAMILY = '"JetBrains Mono", "Cascadia Mono", "Consolas", monospace'
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
SIDEBAR_WIDTH = 240
RADIUS_SM = "4px"
RADIUS_MD = "8px"


def palette_for(dark: bool) -> Palette:
    return DARK if dark else LIGHT


def stylesheet(palette: Palette) -> str:
    """The app-wide QSS for a given palette. Anything widget-specific (a
    tile's accent colour, a field's error border) layers on top via that
    widget's own setStyleSheet — never by editing this.

    Corners are softly rounded throughout (`RADIUS_SM` for controls,
    `RADIUS_MD` for cards/tiles/buttons) — depth still comes from 1px
    borders and tonal layering, never shadows, but the shape language is
    rounded, not sharp.
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
        background-color: {palette.surface_container_lowest};
        color: {palette.text};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 4px 6px;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        min-height: 22px;
        padding: 6px 10px;
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
        border-radius: {RADIUS_SM};
        padding: 6px 14px;
        font-weight: 700;
    }}
    QPushButton:disabled {{
        background-color: {palette.border};
        color: {palette.text_muted};
    }}
    QPushButton#secondary {{
        background-color: transparent;
        color: {palette.text};
        border: 1px solid {palette.border_strong};
        border-radius: {RADIUS_SM};
    }}
    QPushButton#danger {{
        background-color: transparent;
        color: {palette.danger};
        border: 1px solid {palette.danger};
        border-radius: {RADIUS_SM};
    }}
    QWidget#sidebar {{
        background-color: {palette.surface_container_low};
        border-right: 1px solid {palette.border};
    }}
    QPushButton#nav-item {{
        background-color: transparent;
        color: {palette.text_muted};
        border: none;
        border-radius: {RADIUS_SM};
        text-align: left;
        padding: 8px 16px;
        font-weight: 400;
    }}
    QPushButton#nav-item:hover {{
        background-color: {palette.surface_container_highest};
        color: {palette.text};
    }}
    QLabel#error {{
        color: {palette.danger};
    }}
    QFrame#alert-danger {{
        background-color: {palette.danger_container};
        border: 1px solid {palette.danger};
        border-radius: {RADIUS_SM};
    }}
    QFrame#alert-danger QLabel#error {{
        color: {palette.text};
    }}
    QLabel#muted {{
        color: {palette.text_muted};
    }}
    QLabel#headline-lg {{
        font-size: 20px;
        font-weight: 700;
    }}
    QLabel#headline-md {{
        font-size: 16px;
        font-weight: 600;
    }}
    QLabel#label-sm {{
        font-size: 10px;
        font-weight: 700;
        color: {palette.text_muted};
    }}
    QFrame#divider {{
        background-color: {palette.border};
        max-height: 1px;
        border: none;
    }}
    QFrame#tile {{
        background-color: {palette.surface_container_low};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
    }}
    QFrame#card {{
        background-color: {palette.surface_container_low};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
    }}
    QListWidget#schema-list {{
        background-color: {palette.surface_container_low};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
        padding: 6px;
        outline: none;
    }}
    QListWidget#schema-list::item {{
        color: {palette.text_muted};
        border-radius: {RADIUS_SM};
        padding: 8px 10px;
        margin: 1px 0px;
    }}
    QListWidget#schema-list::item:hover {{
        background-color: {palette.surface_container_high};
        color: {palette.text};
    }}
    QListWidget#schema-list::item:selected {{
        background-color: {palette.surface_container_highest};
        color: {palette.accent};
        font-weight: 600;
    }}
    QTabWidget::pane {{
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
    }}
    QTabBar::tab {{
        background-color: {palette.surface_container_low};
        color: {palette.text_muted};
        border: 1px solid {palette.border};
        border-bottom: none;
        border-top-left-radius: {RADIUS_SM};
        border-top-right-radius: {RADIUS_SM};
        padding: 6px 12px;
    }}
    QTabBar::tab:selected {{
        background-color: {palette.surface_container_high};
        color: {palette.accent};
        border-bottom: 2px solid {palette.accent};
    }}
    QTableWidget, QTableView {{
        background-color: {palette.surface_container_lowest};
        alternate-background-color: {palette.surface_container_low};
        gridline-color: {palette.border};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
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
        width: 8px;
    }}
    QScrollBar::handle:vertical {{
        background: {palette.border_strong};
        min-height: 24px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
    }}
    QScrollBar::handle:horizontal {{
        background: {palette.border_strong};
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
        border-radius: {RADIUS_SM};
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
        f"QFrame#tile {{ background-color: {palette.surface_container_low}; "
        f"border: 1px solid {palette.border}; border-left: 4px solid {accent}; "
        f"border-radius: {RADIUS_MD}; }}"
    )


def _settings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def load_dark_mode(username: str) -> bool:
    """Dark mode is persisted per authenticated user (§15), not globally —
    two people sharing a machine keep their own preference."""
    return bool(_settings().value(f"dark_mode/{username}", False, type=bool))


def save_dark_mode(username: str, enabled: bool) -> None:
    _settings().setValue(f"dark_mode/{username}", enabled)
