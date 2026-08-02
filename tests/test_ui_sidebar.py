from PySide6.QtWidgets import QPushButton

from configgen.core.auth import ROLE_ADMIN, ROLE_CONFIG_ENGINEER, ROLE_TEMPLATE_ENGINEER, User
from configgen.ui.sidebar import Sidebar
from configgen.ui.theme import DARK, LIGHT


def _user(role: str, username: str = "u") -> User:
    return User(id=1, username=username, role=role)


def _nav_labels(sidebar: Sidebar) -> set[str]:
    return {b.text() for b in sidebar.findChildren(QPushButton)}


def test_config_engineer_sees_only_home_and_bulk_generate(qtbot):
    sidebar = Sidebar(_user(ROLE_CONFIG_ENGINEER), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    labels = _nav_labels(sidebar)
    assert "Home" in labels
    assert "Bulk Generate" in labels
    assert "Template Editor" not in labels
    assert "User Admin" not in labels
    assert "Import Config Pack" not in labels
    assert "Generation Log" not in labels


def test_template_engineer_sees_editor_and_log_but_not_admin(qtbot):
    sidebar = Sidebar(_user(ROLE_TEMPLATE_ENGINEER), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    labels = _nav_labels(sidebar)
    assert "Template Editor" in labels
    assert "Generation Log" in labels
    assert "User Admin" not in labels
    assert "Import Config Pack" not in labels


def test_admin_sees_every_nav_item(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    labels = _nav_labels(sidebar)
    assert {
        "Home",
        "Template Editor",
        "Generation Log",
        "User Admin",
        "Import Config Pack",
        "Bulk Generate",
        "About",
    } <= labels


def test_bulk_generate_button_emits_signal(qtbot):
    sidebar = Sidebar(_user(ROLE_CONFIG_ENGINEER), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    button = next(b for b in sidebar.findChildren(QPushButton) if b.text() == "Bulk Generate")
    with qtbot.waitSignal(sidebar.bulkGenerateRequested, timeout=1000):
        button.click()


def test_user_admin_button_emits_signal_for_admin(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    button = next(b for b in sidebar.findChildren(QPushButton) if b.text() == "User Admin")
    with qtbot.waitSignal(sidebar.userAdminRequested, timeout=1000):
        button.click()


def test_home_button_emits_signal(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    button = next(b for b in sidebar.findChildren(QPushButton) if b.text() == "Home")
    with qtbot.waitSignal(sidebar.homeRequested, timeout=1000):
        button.click()


def test_about_button_emits_signal(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    button = next(b for b in sidebar.findChildren(QPushButton) if b.text() == "About")
    with qtbot.waitSignal(sidebar.aboutRequested, timeout=1000):
        button.click()


def test_highlight_rules_button_emits_signal(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    button = next(b for b in sidebar.findChildren(QPushButton) if b.text() == "Highlight Rules")
    with qtbot.waitSignal(sidebar.highlightRulesRequested, timeout=1000):
        button.click()


def test_logout_button_emits_signal(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    button = next(b for b in sidebar.findChildren(QPushButton) if b.text() == "Log Out")
    with qtbot.waitSignal(sidebar.logoutRequested, timeout=1000):
        button.click()


def test_refresh_palette_updates_stale_nav_icons(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=True)
    qtbot.addWidget(sidebar)
    home_button = sidebar._nav_buttons["home"]
    light_icon = home_button.icon()

    sidebar.refresh_palette(DARK)

    assert home_button.icon().cacheKey() != light_icon.cacheKey()


def test_dark_mode_checkbox_reflects_initial_state_and_emits_on_toggle(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=True, auto_update_check=True)
    qtbot.addWidget(sidebar)
    assert sidebar.dark_mode_checkbox.isChecked() is True

    with qtbot.waitSignal(sidebar.darkModeToggled, timeout=1000) as blocker:
        sidebar.dark_mode_checkbox.setChecked(False)
    assert blocker.args == [False]


def test_auto_update_checkbox_reflects_initial_state_and_emits_on_toggle(qtbot):
    sidebar = Sidebar(_user(ROLE_ADMIN), LIGHT, dark=False, auto_update_check=False)
    qtbot.addWidget(sidebar)
    assert sidebar.auto_update_checkbox.isChecked() is False

    with qtbot.waitSignal(sidebar.autoUpdateToggled, timeout=1000) as blocker:
        sidebar.auto_update_checkbox.setChecked(True)
    assert blocker.args == [True]
