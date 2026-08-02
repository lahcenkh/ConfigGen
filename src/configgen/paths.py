"""Resolves the app's on-disk folders, in dev (running from source) and frozen
(PyInstaller) modes, so the rest of the codebase never hardcodes a layout."""

import sys
from pathlib import Path


def app_root() -> Path:
    """Where the exe itself lives — the right base for *writable* runtime
    state (users.db, output/) that should sit next to the exe, survive
    reinstalls, and never be mixed in with the app's own bundled code.
    Not the right base for bundled read-only assets — see `bundle_root()`."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    """Where PyInstaller actually puts everything listed in `datas`
    (ConfigGen.spec). PyInstaller >=6 bundles them into a `_internal/`
    folder next to the exe, not the exe's own directory — `sys._MEIPASS`
    is PyInstaller's own documented way to find that, and it's also
    correct for a --onefile build (a temp extraction dir), unlike
    `app_root()`. Falls back to `app_root()` in dev mode, where there's
    no bundle at all, just the checked-out source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return app_root()


def resources_dir() -> Path:
    return bundle_root() / "resources"


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
    """packaging/icon.ico, resolved from bundle_root() — ConfigGen.spec
    bundles it as a data file at that same relative path (§16). Callers
    must check `.is_file()`: a dev checkout that hasn't run
    tools/make_icon.py yet has no icon, and that's not an error."""
    return bundle_root() / "packaging" / "icon.ico"


def logo_path() -> Path:
    """The ConfigGen mark, as source SVG — resources/branding/logo.svg,
    bundled by ConfigGen.spec the same way resources/data/ already is.
    This is the single source both the in-app logo (login screen,
    sidebar) and tools/make_icon.py's .ico render from."""
    return resources_dir() / "branding" / "logo.svg"
