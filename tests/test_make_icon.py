from pathlib import Path

from PySide6.QtGui import QImage

from configgen.ui.logo import logo_pixmap
from tools.make_icon import write_ico

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_logo_pixmap_produces_a_square_nonempty_pixmap(qtbot):
    # tools/make_icon.py just renders configgen.ui.logo.logo_pixmap() to
    # packaging/icon.{ico,png} — this is the actual source of the artwork.
    pixmap = logo_pixmap(128)
    assert pixmap.width() == 128
    assert pixmap.height() == 128
    assert not pixmap.isNull()


def test_write_ico_embeds_every_declared_size(qtbot, tmp_path: Path):
    # A single oversized frame is a known case where Explorer/PyInstaller's
    # own icon embedding silently falls back to a generic icon instead of
    # resampling it — this is the actual bug that motivated write_ico()
    # existing at all, so pin down that every size really lands in the file.
    ico_path = tmp_path / "test.ico"
    write_ico(ico_path, sizes=(16, 32, 48))

    data = ico_path.read_bytes()
    assert data[2:4] == b"\x01\x00"  # ICO type marker
    count = int.from_bytes(data[4:6], "little")
    assert count == 3

    sizes_in_file = []
    for i in range(count):
        offset = 6 + i * 16
        width = data[offset] or 256
        sizes_in_file.append(width)
    assert sizes_in_file == [16, 32, 48]


def test_committed_icon_files_are_valid_images():
    ico_path = REPO_ROOT / "packaging" / "icon.ico"
    png_path = REPO_ROOT / "packaging" / "icon.png"
    assert ico_path.is_file()
    assert png_path.is_file()

    ico_image = QImage(str(ico_path))
    png_image = QImage(str(png_path))
    assert not ico_image.isNull()
    assert not png_image.isNull()
