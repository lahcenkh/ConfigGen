"""Non-blocking update notification (§16) — a background check plus a
dismissible banner, never a modal dialog: a stale version is worth
mentioning, never worth interrupting someone's work over.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from configgen.appinfo import __version__
from configgen.core.update_check import DEFAULT_REPO, UpdateCheckError, check_for_update
from configgen.ui import theme


class UpdateCheckWorker(QThread):
    """Runs the (blocking, network) version check off the UI thread.
    Silent on failure — a machine with no internet access, or GitHub
    being unreachable, is not an error worth surfacing for a background
    nicety (§16: "non-blocking notification")."""

    updateAvailable = Signal(str)

    def __init__(self, repo: str = DEFAULT_REPO, parent: QWidget | None = None):
        super().__init__(parent)
        self.repo = repo

    def run(self) -> None:
        try:
            latest_tag = check_for_update(self.repo)
        except UpdateCheckError:
            return
        if latest_tag:
            self.updateAvailable.emit(latest_tag)


class UpdateBanner(QWidget):
    """Hidden until `show_update()` is called; dismiss just hides it
    again for the rest of the session."""

    def __init__(self, palette: theme.Palette, parent: QWidget | None = None):
        super().__init__(parent)
        self.palette = palette
        self.setObjectName("card")
        self.setVisible(False)

        layout = QHBoxLayout(self)
        self.label = QLabel()
        self.label.setWordWrap(True)
        layout.addWidget(self.label, stretch=1)

        dismiss_button = QPushButton("Dismiss")
        dismiss_button.setObjectName("secondary")
        dismiss_button.clicked.connect(self.hide)
        layout.addWidget(dismiss_button)

    def show_update(self, latest_tag: str) -> None:
        self.label.setText(
            f"ConfigGen {latest_tag} is available (you're on {__version__}). "
            f'Visit <a href="https://github.com/{DEFAULT_REPO}/releases">'
            f"{DEFAULT_REPO}'s releases page</a> to update."
        )
        self.label.setOpenExternalLinks(True)
        self.setVisible(True)
