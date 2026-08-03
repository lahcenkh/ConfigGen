from configgen.ui.logo import logo_pixmap


def test_logo_pixmap_renders_at_the_requested_size(qtbot):
    pixmap = logo_pixmap(64)
    assert pixmap.isNull() is False
    assert pixmap.width() == 64
    assert pixmap.height() == 64


def test_logo_pixmap_actually_draws_something(qtbot):
    pixmap = logo_pixmap(88)
    image = pixmap.toImage()
    opaque_pixels = sum(
        1 for y in range(0, 88, 4) for x in range(0, 88, 4) if image.pixelColor(x, y).alpha() > 0
    )
    assert opaque_pixels > 0
