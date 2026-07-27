"""Design tokens + stylesheets + dark mode (§15 of the build plan).

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
    text: str
    text_muted: str
    border: str
    accent: str
    danger: str
    success: str


LIGHT = Palette(
    background="#f5f6f8",
    surface="#ffffff",
    text="#1a1d21",
    text_muted="#5c6470",
    border="#d8dce2",
    accent="#3b6fe0",
    danger="#d94f4f",
    success="#2f9e5c",
)

DARK = Palette(
    background="#1a1d21",
    surface="#24282e",
    text="#e8eaed",
    text_muted="#9aa2ad",
    border="#343a42",
    accent="#5b8df0",
    danger="#e0685f",
    success="#4cbd7d",
)

SPACING = {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}
FONT_FAMILY = '"Segoe UI", Arial, sans-serif'


def palette_for(dark: bool) -> Palette:
    return DARK if dark else LIGHT


def stylesheet(palette: Palette) -> str:
    """The app-wide QSS for a given palette. Anything widget-specific (a
    tile's accent colour, a field's error border) layers on top via that
    widget's own setStyleSheet — never by editing this."""
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
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
        background-color: {palette.surface};
        border: 1px solid {palette.border};
        border-radius: 4px;
        padding: 4px 6px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {palette.accent};
    }}
    QLineEdit[hasError="true"], QComboBox[hasError="true"],
    QSpinBox[hasError="true"], QPlainTextEdit[hasError="true"] {{
        border: 1px solid {palette.danger};
    }}
    QPushButton {{
        background-color: {palette.accent};
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
    }}
    QPushButton:disabled {{
        background-color: {palette.border};
        color: {palette.text_muted};
    }}
    QPushButton#secondary {{
        background-color: {palette.surface};
        color: {palette.text};
        border: 1px solid {palette.border};
    }}
    QLabel#error {{
        color: {palette.danger};
    }}
    QLabel#muted {{
        color: {palette.text_muted};
    }}
    QFrame#tile {{
        background-color: {palette.surface};
        border: 1px solid {palette.border};
        border-radius: 8px;
    }}
    QFrame#card {{
        background-color: {palette.surface};
        border: 1px solid {palette.border};
        border-radius: 8px;
    }}
    QTabWidget::pane {{
        border: 1px solid {palette.border};
    }}
    QTabBar::tab {{
        background-color: {palette.background};
        color: {palette.text_muted};
        border: 1px solid {palette.border};
        border-bottom: none;
        padding: 6px 12px;
    }}
    QTabBar::tab:selected {{
        background-color: {palette.surface};
        color: {palette.text};
    }}
    """


def tile_style(palette: Palette, accent_hex: str | None = None) -> str:
    """A tile's accent stripe colour is data the caller supplies (e.g. a
    group's own `accent_hex`), falling back to the palette's own accent."""
    accent = accent_hex or palette.accent
    return (
        f"QFrame#tile {{ background-color: {palette.surface}; "
        f"border: 1px solid {palette.border}; border-left: 4px solid {accent}; "
        f"border-radius: 8px; }}"
    )


def _settings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def load_dark_mode(username: str) -> bool:
    """Dark mode is persisted per authenticated user (§15), not globally —
    two people sharing a machine keep their own preference."""
    return bool(_settings().value(f"dark_mode/{username}", False, type=bool))


def save_dark_mode(username: str, enabled: bool) -> None:
    _settings().setValue(f"dark_mode/{username}", enabled)
