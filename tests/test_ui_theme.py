from configgen.ui import theme

# QSettings isolation (so this never touches the real machine's settings
# store) comes from the autouse `_isolated_qsettings` fixture in conftest.py.


def test_palette_for_dark_and_light():
    assert theme.palette_for(False) is theme.LIGHT
    assert theme.palette_for(True) is theme.DARK


def test_stylesheet_embeds_palette_colors():
    css = theme.stylesheet(theme.DARK)
    assert theme.DARK.background in css
    assert theme.DARK.accent in css


def test_stylesheet_includes_error_property_selector():
    css = theme.stylesheet(theme.LIGHT)
    assert 'hasError="true"' in css
    assert theme.LIGHT.danger in css


def test_stylesheet_styles_inactive_tabs_readable():
    # Carried-over fix (§19): inactive tabs must not go unreadable.
    css = theme.stylesheet(theme.LIGHT)
    assert "QTabBar::tab" in css
    assert "QTabBar::tab:selected" in css


def test_tile_style_uses_palette_accent_by_default():
    css = theme.tile_style(theme.LIGHT)
    assert theme.LIGHT.accent in css


def test_tile_style_uses_supplied_accent_hex():
    css = theme.tile_style(theme.LIGHT, accent_hex="#ff00ff")
    assert "#ff00ff" in css


def test_dark_mode_persists_per_username():
    assert theme.load_dark_mode("alice") is False  # default
    theme.save_dark_mode("alice", True)
    assert theme.load_dark_mode("alice") is True
    # a different user's preference is independent
    assert theme.load_dark_mode("bob") is False
