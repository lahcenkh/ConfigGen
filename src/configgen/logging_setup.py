"""App-wide logging (troubleshooting): every render, every hook run, every
error lands in <app_root>/logs/app.log, because a --windowed packaged build
(ConfigGen.spec's console=False) has nowhere else for it to go — Qt routes
an uncaught exception raised inside a slot through `sys.excepthook`, and
with no console attached, the traceback that would normally print there
just vanishes instead. That's the class of bug this exists to catch: a
button click that appears to silently do nothing.

`configure_logging()` sets up the rotating file handler and replaces
`sys.excepthook` so an uncaught exception is always: (1) written to
app.log with a full traceback, and (2) shown to the user in a message box,
instead of disappearing."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path

from configgen.paths import app_root

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5

_handler: logging.Handler | None = None


def log_dir() -> Path:
    return app_root() / "logs"


def log_path() -> Path:
    return log_dir() / "app.log"


def configure_logging(level: int = logging.INFO) -> Path:
    """Idempotent — safe to call more than once (a fresh MainWindow after
    Log Out, or repeated calls across tests where app_root() has been
    monkeypatched to somewhere new): drops whatever handler a previous
    call installed before adding the current one, so it never ends up
    logging to a stale path or duplicating every line."""
    global _handler

    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()

    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    _handler = handler

    sys.excepthook = _excepthook
    return path


def _excepthook(exc_type: type[BaseException], exc_value: BaseException, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.getLogger("configgen.uncaught").critical("Unhandled exception:\n%s", text)
    _show_error_dialog(exc_type, exc_value, text)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _show_error_dialog(exc_type: type[BaseException], exc_value: BaseException, text: str) -> None:
    """Best-effort — a --windowed build has no console for the traceback
    _excepthook already logged to land on, so this is the only remaining
    way the user finds out *something* happened at all. Must never let a
    problem here escalate into a second, worse crash."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            return
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Unexpected error")
        box.setText(f"{exc_type.__name__}: {exc_value}")
        box.setInformativeText(f"Details were written to {log_path()}")
        box.setDetailedText(text)
        box.exec()
    except Exception:  # noqa: BLE001 - the crash handler must never itself crash
        pass
