"""Resolves the app's on-disk folders, in dev (running from source) and frozen
(PyInstaller) modes, so the rest of the codebase never hardcodes a layout."""

import sys
from pathlib import Path


def app_root() -> Path:
    """Where the exe itself lives — the right base for anything the running
    app *writes*, not just reads: output/, and resources/ (Template Editor
    creates/edits/deletes schema and template files there and writes version
    history alongside them; users.db and from_db lookup data live in
    resources/data/). All of that needs to sit next to the exe, survive
    reinstalls, and — for a --onefile build — not vanish along with a temp
    extraction dir the way bundle_root() would.
    Not the right base for the handful of genuinely static, read-only
    assets PyInstaller embeds in the bundle itself — see `bundle_root()`."""
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
    """schemas/templates/data/hooks/.history — read AND written by the
    running app, so this is app_root()-based (exe-adjacent, writable), not
    bundle_root()-based. A packaged build gets its starter content copied
    here by build.ps1 as a plain file copy, separately from PyInstaller's
    own (read-only) `datas` bundling."""
    return app_root() / "resources"


def bundled_assets_dir() -> Path:
    """Static, read-only assets PyInstaller actually embeds in the bundle
    (ConfigGen.spec's `datas`) — nothing ever writes here, so unlike
    `resources_dir()`, resolving it against `bundle_root()` is correct even
    where that's a --onefile temp extraction directory."""
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
    """resources/data/users.db — alongside queries.yaml and whatever .db
    file a schema's `from_db` lookups use, rather than loose at the app
    root. `AuthStore` creates this directory itself if it's missing
    (a from_db-free install has no other reason for resources/data/ to
    exist yet)."""
    return data_dir() / "users.db"


def icon_path() -> Path:
    """packaging/icon.ico, resolved from bundle_root() — ConfigGen.spec
    bundles it as a data file at that same relative path (§16). Callers
    must check `.is_file()`: a dev checkout that hasn't run
    tools/make_icon.py yet has no icon, and that's not an error."""
    return bundle_root() / "packaging" / "icon.ico"


def logo_path() -> Path:
    """The ConfigGen mark, as source SVG — resources/branding/logo.svg,
    bundled by ConfigGen.spec's `datas`. This is the single source both
    the in-app logo (login screen, sidebar) and tools/make_icon.py's .ico
    render from."""
    return bundled_assets_dir() / "branding" / "logo.svg"


def docs_dir() -> Path:
    """The shipped docs/*.md files — static and read-only like the icon and
    logo, so this resolves against bundle_root() (ConfigGen.spec's `datas`)
    rather than app_root(). Powers the in-app Help dialog, so a user never
    has to leave the app to find these."""
    return bundle_root() / "docs"
