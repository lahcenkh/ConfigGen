from PySide6.QtWidgets import QPushButton

from configgen.core.update_check import UpdateCheckError
from configgen.ui import theme, update_notice
from configgen.ui.update_notice import UpdateBanner, UpdateCheckWorker


def test_banner_hidden_by_default(qtbot):
    banner = UpdateBanner(theme.palette_for(False))
    qtbot.addWidget(banner)
    assert banner.isHidden() is True


def test_banner_show_update_sets_text_and_unhides(qtbot):
    banner = UpdateBanner(theme.palette_for(False))
    qtbot.addWidget(banner)

    banner.show_update("v9.9.9")

    assert banner.isHidden() is False
    assert "v9.9.9" in banner.label.text()


def test_dismiss_button_hides_banner(qtbot):
    banner = UpdateBanner(theme.palette_for(False))
    qtbot.addWidget(banner)
    banner.show_update("v9.9.9")
    assert banner.isHidden() is False

    dismiss_button = banner.findChild(QPushButton)
    dismiss_button.click()

    assert banner.isHidden() is True


def test_worker_emits_signal_when_update_available(qtbot, monkeypatch):
    monkeypatch.setattr(update_notice, "check_for_update", lambda repo, timeout=3.0: "v9.9.9")
    worker = UpdateCheckWorker()

    received = []
    worker.updateAvailable.connect(received.append)
    worker.run()  # call directly, not .start() — no real thread needed for this

    assert received == ["v9.9.9"]


def test_worker_emits_nothing_when_no_update(qtbot, monkeypatch):
    monkeypatch.setattr(update_notice, "check_for_update", lambda repo, timeout=3.0: None)
    worker = UpdateCheckWorker()

    received = []
    worker.updateAvailable.connect(received.append)
    worker.run()

    assert received == []


def test_worker_silently_swallows_update_check_error(qtbot, monkeypatch):
    def _raise(repo, timeout=3.0):
        raise UpdateCheckError("no network")

    monkeypatch.setattr(update_notice, "check_for_update", _raise)
    worker = UpdateCheckWorker()

    received = []
    worker.updateAvailable.connect(received.append)
    worker.run()  # should not raise

    assert received == []
