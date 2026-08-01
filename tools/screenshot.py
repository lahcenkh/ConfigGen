"""Screenshot harness (§16 packaging, README screenshots) — renders real
app widgets under the offscreen QPA platform and grabs them to PNG.
`QWidget.grab()` rasterizes into an off-screen buffer regardless of
platform, so this produces genuine, current screenshots of the actual
UI, not mockups; run it whenever the UI changes enough to make the
committed ones stale.

Run from the repo root: `python tools/screenshot.py`
(QT_QPA_PLATFORM=offscreen is set here, before PySide6 is imported.)
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from configgen.core.auth import AuthStore  # noqa: E402
from configgen.core.schema import find_schema_files, load_schema  # noqa: E402
from configgen.ui import theme  # noqa: E402
from configgen.ui.dashboard import Dashboard  # noqa: E402
from configgen.ui.login_window import LoginWindow  # noqa: E402
from configgen.ui.main_window import MainWindow  # noqa: E402
from configgen.ui.template_editor import TemplateEditorWindow  # noqa: E402
from configgen.ui.user_admin import UserAdminWindow  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "screenshots"


def _grab(widget, name: str) -> None:
    # A fixed-size widget (e.g. LoginWindow) clamps resize() back to its own
    # size anyway — forcing 1150x780 on it would just be a no-op, so grab it
    # at its real size instead of pretending otherwise.
    if widget.maximumSize() != widget.minimumSize():
        widget.resize(1150, 780)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    path = OUT_DIR / f"{name}.png"
    pixmap.save(str(path), "PNG")
    print(f"wrote {path}")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    tmpdir = Path(tempfile.mkdtemp())
    try:
        store = AuthStore(tmpdir / "users.db")
        admin = store.authenticate("admin", "admin")
        # Screenshots follow the reference design's dark "Flat Industrial
        # Precision" look — every grabbed widget below is explicitly
        # styled or built dark, not left at Qt's stock light default.
        theme.save_dark_mode("admin", True)

        login = LoginWindow(store)
        login.setStyleSheet(theme.stylesheet(theme.DARK))
        login._show_login_error("Invalid credentials. 3 attempts remaining before lockout.")
        _grab(login, "login")

        schemas_dir = REPO_ROOT / "examples" / "schemas"
        schemas = [load_schema(p) for p in find_schema_files(schemas_dir)]
        dashboard = Dashboard(admin, schemas, set(), theme.DARK)
        dashboard.setStyleSheet(theme.stylesheet(theme.DARK))
        _grab(dashboard, "dashboard")

        window = MainWindow(admin, store, schemas_dir, check_for_updates=False)
        window._open_generator(schemas[0].id)
        _grab(window, "generator")

        editor = TemplateEditorWindow(admin, store, schemas_dir, theme.DARK)
        editor.setStyleSheet(theme.stylesheet(theme.DARK))
        if editor.schema_list.count():
            editor.schema_list.setCurrentRow(0)
        _grab(editor, "template_editor")

        user_admin = UserAdminWindow(store, admin)
        user_admin.setStyleSheet(theme.stylesheet(theme.DARK))
        _grab(user_admin, "user_admin")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    del app

    return 0


if __name__ == "__main__":
    sys.exit(main())
