from pathlib import Path

from PySide6.QtGui import QImage

from tools.make_icon import render_icon

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_render_icon_produces_a_square_nonempty_pixmap(qtbot):
    pixmap = render_icon(128)
    assert pixmap.width() == 128
    assert pixmap.height() == 128
    assert not pixmap.isNull()


def test_committed_icon_files_are_valid_images():
    ico_path = REPO_ROOT / "packaging" / "icon.ico"
    png_path = REPO_ROOT / "packaging" / "icon.png"
    assert ico_path.is_file()
    assert png_path.is_file()

    ico_image = QImage(str(ico_path))
    png_image = QImage(str(png_path))
    assert not ico_image.isNull()
    assert not png_image.isNull()
