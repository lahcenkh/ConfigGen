"""Small monochrome line-art icons drawn with QPainter (§15 GUI redesign)
— person/lock/eye for the login form. Qt's own QStyle.standardIcon() has
no equivalents for these, and bundling an icon font/SVG set is more than
a few 16px glyphs are worth, so they're just drawn directly, colored to
match whatever palette token the caller passes in.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def _draw(size: int, color: str, draw_fn) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.2, size * 0.09))
    painter.setPen(pen)
    draw_fn(painter, size)
    painter.end()
    return QIcon(pixmap)


def person_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        head_r = size * 0.16
        painter.drawEllipse(QPointF(size / 2, size * 0.32), head_r, head_r)
        body_rect = QRectF(size * 0.18, size * 0.5, size * 0.64, size * 0.5)
        painter.drawArc(body_rect, 0, 180 * 16)

    return _draw(size, color, draw)


def lock_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        shackle_rect = QRectF(size * 0.28, size * 0.14, size * 0.44, size * 0.38)
        painter.drawArc(shackle_rect, 0, 180 * 16)
        body_rect = QRectF(size * 0.2, size * 0.44, size * 0.6, size * 0.42)
        painter.drawRoundedRect(body_rect, 2, 2)

    return _draw(size, color, draw)


def eye_icon(color: str, size: int = 16, *, visible: bool = True) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        rect = QRectF(size * 0.08, size * 0.32, size * 0.84, size * 0.36)
        painter.drawEllipse(rect)
        pupil_r = size * 0.08
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(size / 2, size / 2), pupil_r, pupil_r)
        if not visible:
            painter.drawLine(QPointF(size * 0.12, size * 0.85), QPointF(size * 0.88, size * 0.15))

    return _draw(size, color, draw)
