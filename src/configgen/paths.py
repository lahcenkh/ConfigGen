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
