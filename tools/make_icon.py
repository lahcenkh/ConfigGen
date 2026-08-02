"""Generates the app icon (§16 packaging) from the ConfigGen mark
(resources/branding/logo.svg, rendered via `configgen.ui.logo`) — the
same source the login screen and sidebar draw from, so the taskbar/exe
icon is never a different mark than what's shown in the app itself.
Run once from the repo root: `python tools/make_icon.py`.

Not part of the app's runtime import graph — this only ever runs
manually, ahead of a packaging build, to (re)produce
packaging/icon.{ico,png}.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from configgen.ui.logo import logo_pixmap  # noqa: E402

# Windows Explorer/the taskbar pick whichever of these is closest to the
# size they need and only fall back to resampling as a last resort — a
# single oversized frame (what QPixmap.save(path, "ICO") produces: just
# the one 256x256 PNG-compressed image) is a known case where Explorer
# and PyInstaller's own icon embedding step both silently give up and
# show a generic icon instead of resampling it.
_SIZES = (16, 32, 48, 64, 128, 256)


def _png_bytes(size: int) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    logo_pixmap(size).save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def write_ico(path: Path, sizes: tuple[int, ...] = _SIZES) -> None:
    """Builds a real multi-resolution .ico by hand: an ICONDIR header, one
    ICONDIRENTRY per size, then the PNG-encoded image data itself for each
    — Windows has supported PNG-compressed icon frames at any size since
    Vista, so there's no need for legacy uncompressed BMP/DIB frames."""
    images = [_png_bytes(size) for size in sizes]

    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = b""
    offset = 6 + 16 * len(sizes)
    for size, image in zip(sizes, images, strict=True):
        side = size if size < 256 else 0  # 0 means "256" in ICO format
        entries += struct.pack(
            "<BBBBHHII",
            side,  # width
            side,  # height
            0,  # color count (0 = no palette, true color)
            0,  # reserved
            1,  # color planes
            32,  # bits per pixel
            len(image),  # size of this image's data
            offset,  # offset of this image's data from file start
        )
        offset += len(image)

    with path.open("wb") as f:
        f.write(header)
        f.write(entries)
        for image in images:
            f.write(image)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    packaging_dir = REPO_ROOT / "packaging"
    packaging_dir.mkdir(parents=True, exist_ok=True)

    png_path = packaging_dir / "icon.png"
    ico_path = packaging_dir / "icon.ico"
    logo_pixmap(256).save(str(png_path), "PNG")
    write_ico(ico_path)

    print(f"wrote {png_path}")
    print(f"wrote {ico_path} ({len(_SIZES)} sizes: {', '.join(str(s) for s in _SIZES)})")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
