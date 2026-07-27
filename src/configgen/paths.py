"""Resolves the app's on-disk folders, in dev (running from source) and frozen
(PyInstaller) modes, so the rest of the codebase never hardcodes a layout."""

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def resources_dir() -> Path:
    return app_root() / "resources"


def schemas_dir() -> Path:
    return resources_dir() / "schemas"


def templates_dir() -> Path:
    return resources_dir() / "templates"


def data_dir() -> Path:
    return resources_dir() / "data"


def output_dir() -> Path:
    return app_root() / "output"


def users_db_path() -> Path:
    return app_root() / "users.db"


def icon_path() -> Path:
    """packaging/icon.ico next to app_root() in both dev and frozen mode —
    ConfigGen.spec bundles it as a data file at that same relative path
    (§16). Callers must check `.is_file()`: a dev checkout that hasn't run
    tools/make_icon.py yet has no icon, and that's not an error."""
    return app_root() / "packaging" / "icon.ico"
