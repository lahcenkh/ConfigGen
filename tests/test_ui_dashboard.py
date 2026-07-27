from pathlib import Path

from PySide6.QtWidgets import QPushButton

from configgen.core.auth import ROLE_ADMIN, ROLE_CONFIG_ENGINEER, ROLE_TEMPLATE_ENGINEER, User
from configgen.core.schema import find_schema_files, load_schema
from configgen.ui.dashboard import Dashboard
from configgen.ui.theme import LIGHT

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS = [load_schema(p) for p in find_schema_files(EXAMPLES_ROOT / "schemas")]


def _user(role: str, username: str = "u") -> User:
    return User(id=1, username=username, role=role)


def _tile_schema_ids(dash: Dashboard) -> set[str]:
    ids = set()
    for i in range(dash.tiles_layout.count()):
        widget = dash.tiles_layout.itemAt(i).widget()
        if hasattr(widget, "schema"):
            ids.add(widget.schema.id)
    return ids


def test_admin_sees_all_schemas_as_tiles(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    assert len(dash.visible_schemas()) == len(SCHEMAS)
    assert _tile_schema_ids(dash) == {s.id for s in SCHEMAS}


def test_search_filters_tiles_by_name(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    dash.search_input.setText("router")
    assert _tile_schema_ids(dash) == {"router_base_config"}


def test_search_no_match_shows_placeholder_label(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    dash.search_input.setText("this-matches-nothing")
    assert dash.tiles_layout.count() == 1
    assert _tile_schema_ids(dash) == set()


def test_group_filter_has_only_all_groups_for_shipped_examples(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    group_names = [dash.group_filter.itemText(i) for i in range(dash.group_filter.count())]
    assert group_names == ["All groups"]  # none of the shipped examples declare a group


def test_template_tile_click_emits_template_selected(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    tile = dash.tiles_layout.itemAt(0).widget()
    with qtbot.waitSignal(dash.templateSelected, timeout=1000) as blocker:
        tile.clicked.emit(tile.schema.id)
    assert blocker.args == [tile.schema.id]


def test_bulk_generate_button_emits_signal(qtbot):
    dash = Dashboard(_user(ROLE_CONFIG_ENGINEER), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    bulk_button = next(b for b in dash.findChildren(QPushButton) if b.text() == "Bulk Generate")
    with qtbot.waitSignal(dash.bulkGenerateRequested, timeout=1000):
        bulk_button.click()


def test_config_engineer_sees_no_admin_or_editor_buttons(qtbot):
    dash = Dashboard(_user(ROLE_CONFIG_ENGINEER), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    labels = {b.text() for b in dash.findChildren(QPushButton)}
    assert "Template Editor" not in labels
    assert "User Admin" not in labels
    assert "Import Config Pack" not in labels
    assert "Bulk Generate" in labels


def test_template_engineer_sees_template_editor_but_not_user_admin(qtbot):
    dash = Dashboard(_user(ROLE_TEMPLATE_ENGINEER), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    labels = {b.text() for b in dash.findChildren(QPushButton)}
    assert "Template Editor" in labels
    assert "Generation Log" in labels
    assert "User Admin" not in labels
    assert "Import Config Pack" not in labels


def test_admin_sees_all_admin_buttons(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    labels = {b.text() for b in dash.findChildren(QPushButton)}
    assert {"Template Editor", "User Admin", "Import Config Pack", "Bulk Generate"} <= labels


def test_user_admin_button_emits_signal_for_admin(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT)
    qtbot.addWidget(dash)
    admin_button = next(b for b in dash.findChildren(QPushButton) if b.text() == "User Admin")
    with qtbot.waitSignal(dash.userAdminRequested, timeout=1000):
        admin_button.click()


def test_recent_log_panel_renders_entries(qtbot):
    entries = [
        {"created_at": "2026-01-01T00:00:00", "schema_id": "widget", "output_filename": "a.txt"}
    ]
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT, recent_log_entries=entries)
    qtbot.addWidget(dash)
    from PySide6.QtWidgets import QLabel

    labels_text = " ".join(lbl.text() for lbl in dash.findChildren(QLabel))
    assert "widget" in labels_text
    assert "a.txt" in labels_text


def test_no_recent_entries_means_no_recent_panel(qtbot):
    dash = Dashboard(_user(ROLE_ADMIN), SCHEMAS, set(), LIGHT, recent_log_entries=None)
    qtbot.addWidget(dash)
    from PySide6.QtWidgets import QFrame

    assert not any(f.objectName() == "card" for f in dash.findChildren(QFrame))
