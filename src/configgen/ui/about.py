"""About dialog (§1) — app identity from appinfo.py, the single source of
truth every other "what version is this" surface (CLI --version, the
generated-config header) already reads from."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from configgen.appinfo import APP_NAME, AUTHOR, CONTACT, __version__


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")

        layout = QVBoxLayout(self)

        title = QLabel(APP_NAME)
        title.setObjectName("headline-lg")
        layout.addWidget(title)

        layout.addWidget(QLabel(f"Version {__version__}"))
        layout.addWidget(QLabel(f"By {AUTHOR}"))
        layout.addWidget(QLabel(CONTACT))

        tagline = QLabel(
            "A generic, plug-and-play tool for generating text configurations\n"
            "from a guided form and Jinja templates."
        )
        tagline.setObjectName("muted")
        layout.addWidget(tagline)

        license_label = QLabel("MIT License")
        license_label.setObjectName("muted")
        layout.addWidget(license_label)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
