"""The ConfigGen mark — one SVG asset (resources/branding/logo.svg),
rendered to whatever pixel size a call site needs via QSvgRenderer. Kept
as a single source of truth so the login screen, the sidebar, and
tools/make_icon.py's .ico all draw the exact same mark, just at
different sizes, instead of three drifting copies.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from configgen.paths import logo_path


def logo_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(str(logo_path()))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    return pixmap
