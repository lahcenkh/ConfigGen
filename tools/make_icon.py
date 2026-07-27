"""Generates the app icon (§16 packaging) — a plain "CG" monogram on the
theme's accent colour, drawn with Qt (already a dependency; no Pillow
needed). Run once from the repo root: `python tools/make_icon.py`.

Not part of the app's runtime import graph — this only ever runs
manually, ahead of a packaging build, to (re)produce
packaging/icon.{ico,png}.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

_ACCENT = "#3b6fe0"
_SIZE = 256


def render_icon(size: int = _SIZE) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QBrush(QColor(_ACCENT)))
    painter.setPen(Qt.PenStyle.NoPen)
    radius = size * 0.2
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", int(size * 0.36), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "CG")

    painter.end()
    return pixmap


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    packaging_dir = Path(__file__).resolve().parents[1] / "packaging"
    packaging_dir.mkdir(parents=True, exist_ok=True)

    pixmap = render_icon()
    png_path = packaging_dir / "icon.png"
    ico_path = packaging_dir / "icon.ico"
    pixmap.save(str(png_path), "PNG")
    pixmap.save(str(ico_path), "ICO")

    print(f"wrote {png_path}")
    print(f"wrote {ico_path}")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
