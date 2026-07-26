from configgen.appinfo import APP_NAME, __version__


def test_app_identity_is_defined():
    assert APP_NAME == "ConfigGen"
    assert __version__
