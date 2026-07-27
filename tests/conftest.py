"""Forces Qt's offscreen platform plugin before anything imports PySide6, so
GUI tests run headless without needing a real display — locally or in CI
(§17: "GUI (headless, offscreen)")."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402

from configgen.ui import theme  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, monkeypatch):
    """theme.py persists dark mode via QSettings(APP_ORG, APP_NAME), which
    is backed by the real Windows registry (or platform equivalent) by
    default — without this, running the test suite writes to and reads
    from the *actual developer/CI machine's* settings store, so a stale
    value from one run bleeds into and pollutes the next."""
    settings_path = tmp_path / "configgen_test_settings.ini"
    monkeypatch.setattr(
        theme, "_settings", lambda: QSettings(str(settings_path), QSettings.Format.IniFormat)
    )
