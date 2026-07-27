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

OUT_DIR = REPO_ROOT / "docs" / "screenshots"


def _grab(widget, name: str) -> None:
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

        login = LoginWindow(store)
        _grab(login, "login")

        schemas_dir = REPO_ROOT / "examples" / "schemas"
        schemas = [load_schema(p) for p in find_schema_files(schemas_dir)]
        palette = theme.palette_for(False)
        dashboard = Dashboard(admin, schemas, set(), palette)
        _grab(dashboard, "dashboard")

        window = MainWindow(admin, store, schemas_dir, check_for_updates=False)
        window._open_generator(schemas[0].id)
        _grab(window, "generator")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    del app

    return 0


if __name__ == "__main__":
    sys.exit(main())
