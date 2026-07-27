from configgen.ui import settings


def test_auto_update_check_enabled_defaults_to_true():
    assert settings.auto_update_check_enabled() is True


def test_set_auto_update_check_enabled_persists():
    settings.set_auto_update_check_enabled(False)
    assert settings.auto_update_check_enabled() is False

    settings.set_auto_update_check_enabled(True)
    assert settings.auto_update_check_enabled() is True
