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


def home_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        painter.drawLine(QPointF(size * 0.1, size * 0.5), QPointF(size / 2, size * 0.14))
        painter.drawLine(QPointF(size / 2, size * 0.14), QPointF(size * 0.9, size * 0.5))
        painter.drawRect(QRectF(size * 0.22, size * 0.48, size * 0.56, size * 0.4))

    return _draw(size, color, draw)


def template_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        painter.drawRoundedRect(QRectF(size * 0.2, size * 0.12, size * 0.6, size * 0.76), 2, 2)
        for frac in (0.36, 0.52, 0.68):
            painter.drawLine(QPointF(size * 0.32, size * frac), QPointF(size * 0.68, size * frac))

    return _draw(size, color, draw)


def log_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        painter.drawEllipse(QRectF(size * 0.1, size * 0.1, size * 0.8, size * 0.8))
        center = QPointF(size / 2, size / 2)
        painter.drawLine(center, QPointF(size / 2, size * 0.28))
        painter.drawLine(center, QPointF(size * 0.66, size * 0.56))

    return _draw(size, color, draw)


def import_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        painter.drawLine(QPointF(size / 2, size * 0.14), QPointF(size / 2, size * 0.6))
        painter.drawLine(QPointF(size * 0.3, size * 0.42), QPointF(size / 2, size * 0.62))
        painter.drawLine(QPointF(size * 0.7, size * 0.42), QPointF(size / 2, size * 0.62))
        painter.drawLine(QPointF(size * 0.16, size * 0.82), QPointF(size * 0.84, size * 0.82))

    return _draw(size, color, draw)


def bulk_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        for offset in (0.2, 0.42, 0.64):
            painter.drawLine(
                QPointF(size * 0.14, size * (offset + 0.08)),
                QPointF(size / 2, size * offset),
            )
            painter.drawLine(
                QPointF(size / 2, size * offset),
                QPointF(size * 0.86, size * (offset + 0.08)),
            )

    return _draw(size, color, draw)


def search_icon(color: str, size: int = 16) -> QIcon:
    def draw(painter: QPainter, size: int) -> None:
        painter.drawEllipse(QRectF(size * 0.12, size * 0.12, size * 0.56, size * 0.56))
        painter.drawLine(QPointF(size * 0.62, size * 0.62), QPointF(size * 0.9, size * 0.9))

    return _draw(size, color, draw)
