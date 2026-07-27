from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel

from tools import screenshot


def test_grab_writes_a_valid_png(qtbot, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(screenshot, "OUT_DIR", tmp_path)
    widget = QLabel("hello")
    qtbot.addWidget(widget)

    screenshot._grab(widget, "demo")

    png_path = tmp_path / "demo.png"
    assert png_path.is_file()
    image = QImage(str(png_path))
    assert not image.isNull()
