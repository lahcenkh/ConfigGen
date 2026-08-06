import logging
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from configgen import logging_setup


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """configure_logging() mutates process-global state (the root logger's
    handlers/level, sys.excepthook, logging_setup._handler) — restore all
    of it after each test so these tests can't bleed into the rest of the
    suite (e.g. some later test's log calls silently landing in a tmp_path
    directory this test already tore down)."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_module_handler = logging_setup._handler
    original_excepthook = sys.excepthook
    yield
    for handler in list(root.handlers):
        if handler not in original_handlers:
            root.removeHandler(handler)
            handler.close()
    for handler in original_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(original_level)
    logging_setup._handler = original_module_handler
    sys.excepthook = original_excepthook


def test_log_path_is_under_app_root(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(logging_setup, "app_root", lambda: tmp_path)
    assert logging_setup.log_dir() == tmp_path / "logs"
    assert logging_setup.log_path() == tmp_path / "logs" / "app.log"


def test_configure_logging_creates_file_and_writes_records(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(logging_setup, "app_root", lambda: tmp_path)
    path = logging_setup.configure_logging()
    assert path == tmp_path / "logs" / "app.log"
    assert path.is_file()

    logging.getLogger("configgen.test").info("hello from a test")
    logging_setup._handler.flush()

    text = path.read_text(encoding="utf-8")
    assert "hello from a test" in text
    assert "INFO" in text
    assert "configgen.test" in text


def test_configure_logging_is_idempotent(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(logging_setup, "app_root", lambda: tmp_path)
    logging_setup.configure_logging()
    first_handler = logging_setup._handler
    logging_setup.configure_logging()
    second_handler = logging_setup._handler

    root = logging.getLogger()
    assert first_handler not in root.handlers  # replaced, not stacked
    assert root.handlers.count(second_handler) == 1


def test_configure_logging_switches_to_a_new_app_root(monkeypatch, tmp_path: Path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    monkeypatch.setattr(logging_setup, "app_root", lambda: first_root)
    logging_setup.configure_logging()
    monkeypatch.setattr(logging_setup, "app_root", lambda: second_root)
    path = logging_setup.configure_logging()

    logging.getLogger("configgen.test").info("goes to the new file only")
    logging_setup._handler.flush()

    assert path == second_root / "logs" / "app.log"
    assert "goes to the new file only" in path.read_text(encoding="utf-8")
    first_log = first_root / "logs" / "app.log"
    if first_log.is_file():
        assert "goes to the new file only" not in first_log.read_text(encoding="utf-8")


def test_excepthook_logs_the_full_traceback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(logging_setup, "app_root", lambda: tmp_path)
    path = logging_setup.configure_logging()
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)

    try:
        raise ValueError("boom")
    except ValueError:
        logging_setup._excepthook(*sys.exc_info())
    logging_setup._handler.flush()

    text = path.read_text(encoding="utf-8")
    assert "Unhandled exception" in text
    assert "ValueError: boom" in text
    # A real traceback, not just the exception message.
    assert "test_excepthook_logs_the_full_traceback" in text


def test_excepthook_reraises_keyboard_interrupt_without_logging(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(logging_setup, "app_root", lambda: tmp_path)
    path = logging_setup.configure_logging()
    calls = []
    monkeypatch.setattr(sys, "__excepthook__", lambda *a: calls.append(a))

    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        logging_setup._excepthook(*sys.exc_info())
    logging_setup._handler.flush()

    assert calls  # delegated to the real default handler
    assert "Unhandled exception" not in path.read_text(encoding="utf-8")


def test_show_error_dialog_skips_quietly_with_no_qapplication(monkeypatch):
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    logging_setup._show_error_dialog(ValueError, ValueError("x"), "traceback text")


def test_show_error_dialog_shows_a_message_box_when_qapplication_exists(qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: calls.append(self.text()) or QMessageBox.StandardButton.Ok
    )
    logging_setup._show_error_dialog(ValueError, ValueError("boom"), "full traceback text")
    assert calls
    assert "ValueError" in calls[0]
    assert "boom" in calls[0]


def test_show_error_dialog_never_raises_even_if_qmessagebox_itself_fails(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    logging_setup._show_error_dialog(ValueError, ValueError("x"), "trace")  # must not raise
