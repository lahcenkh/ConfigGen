"""App-level settings persisted via QSettings — currently just the
auto-update check toggle (§16). Per-user preferences (dark mode) live in
theme.py, keyed by username; this one is machine/install-wide, so it
isn't.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

APP_ORG = "ConfigGen"
APP_NAME = "ConfigGen"


def _settings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def auto_update_check_enabled() -> bool:
    return bool(_settings().value("auto_update_check_enabled", True, type=bool))


def set_auto_update_check_enabled(enabled: bool) -> None:
    _settings().setValue("auto_update_check_enabled", enabled)
