import time
from pathlib import Path

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QFileDialog

from configgen.core.auth import AuthStore
from configgen.ui.main_window import MainWindow

SERVER_SCHEMA = """\
name: Widget Server
id: widget_server
version: 1
status: published
identity_field: hostname
template: widget.j2
fields:
  - key: hostname
    label: Hostname
    type: string
    required: true
  - key: note
    label: Note
    type: string
    required: false
"""

DRAFT_SCHEMA = """\
name: Draft Widget
id: draft_widget
version: 1
status: draft
template: widget.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    _write(project / "schemas" / "widget_server.yaml", SERVER_SCHEMA)
    _write(project / "schemas" / "draft_widget.yaml", DRAFT_SCHEMA)
    _write(project / "templates" / "widget.j2", "host {{ hostname }}\nnote {{ note }}")
    return project


def _isolated_window(tmp_path: Path, monkeypatch, role="admin", username="admin"):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    project = _make_project(tmp_path)
    store = AuthStore(tmp_path / "users.db")
    if username != "admin":
        store.create_user(username, "hunter22pw", role)
    user = store.get_user(username)
    window = MainWindow(user, store, project / "schemas", check_for_updates=False)
    return window, store, project


# -- navigation --------------------------------------------------------------


def test_window_starts_on_dashboard(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    assert window.stack.currentWidget() is window.dashboard


def test_selecting_a_template_opens_generator_view(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    assert window.stack.currentWidget() is window.generator_view
    assert window.generator_view.schema.id == "widget_server"


def test_ctrl_n_returns_to_dashboard(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    window._back_to_dashboard()
    assert window.stack.currentWidget() is window.dashboard


def test_logout_sets_the_flag_and_closes_the_window(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window.show()
    assert window.logout_requested is False

    window._logout()

    assert window.logout_requested is True
    assert window.isVisible() is False


def test_logout_button_triggers_main_window_logout(qtbot, tmp_path: Path, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    button = next(b for b in window.sidebar.findChildren(QPushButton) if b.text() == "Log Out")
    button.click()
    assert window.logout_requested is True


# -- role-based click-through (the phase's own acceptance criterion) ---------


def test_admin_sees_draft_and_published_tiles(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch, role="admin", username="admin")
    qtbot.addWidget(window)
    visible_ids = {s.id for s in window.dashboard.visible_schemas()}
    assert visible_ids == {"widget_server", "draft_widget"}


def test_config_engineer_sees_only_published_tiles(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch, role="config_engineer", username="carol")
    qtbot.addWidget(window)
    visible_ids = {s.id for s in window.dashboard.visible_schemas()}
    assert visible_ids == {"widget_server"}


# -- preview / generate -------------------------------------------------------


def test_preview_renders_without_saving_or_logging(qtbot, tmp_path: Path, monkeypatch):
    window, store, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view
    view.form.set_raw_values({"hostname": "web01", "note": "hi"})

    window._preview(view)

    assert "host web01" in view.last_rendered["primary"]
    assert not (tmp_path / "output").exists()
    assert store.list_generation_log(window.user) == []


def test_generate_saves_and_logs(qtbot, tmp_path: Path, monkeypatch):
    window, store, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view
    view.form.set_raw_values({"hostname": "web01", "note": "hi"})

    window._generate(view)

    saved = list((tmp_path / "output" / "admin" / "ungrouped").glob("*.txt"))
    assert len(saved) == 1
    assert "host web01" in saved[0].read_text(encoding="utf-8")

    entries = store.list_generation_log(window.user)
    assert len(entries) == 1
    assert entries[0]["schema_id"] == "widget_server"


def test_generate_with_invalid_form_does_not_save(qtbot, tmp_path: Path, monkeypatch):
    window, store, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view
    view.form.set_raw_values({"hostname": ""})  # required field left blank

    window._generate(view)

    assert not (tmp_path / "output").exists()
    assert store.list_generation_log(window.user) == []
    assert view.form.widgets["hostname"]._error_label.text()


# -- save as / diff ----------------------------------------------------------


def test_save_as_writes_the_previewed_text(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view
    view.form.set_raw_values({"hostname": "web01", "note": "hi"})
    window._preview(view)

    target = tmp_path / "exported.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    window._save_as(view)

    assert target.read_text(encoding="utf-8") == view.last_rendered["primary"]


def test_save_as_with_nothing_previewed_shows_message_and_writes_nothing(
    qtbot, tmp_path: Path, monkeypatch
):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view

    calls = []
    monkeypatch.setattr(
        "configgen.ui.main_window.QMessageBox.information",
        staticmethod(lambda *a, **k: calls.append(a)),
    )
    window._save_as(view)
    assert calls  # a message was shown, nothing else happened


def test_diff_shows_changes_between_two_generations(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view

    view.form.set_raw_values({"hostname": "web01", "note": "first"})
    window._generate(view)
    time.sleep(1.1)  # distinct second-resolution timestamp for the filename
    view.form.set_raw_values({"note": "second"})
    window._preview(view)

    captured = {}
    monkeypatch.setattr(
        window,
        "_show_diff_dialog",
        lambda text: captured.setdefault("text", text),
    )
    window._diff(view)

    assert "-note first" in captured["text"]
    assert "+note second" in captured["text"]


def test_diff_with_no_history_shows_message(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view
    view.form.set_raw_values({"hostname": "web01", "note": "only-once"})
    window._preview(view)  # preview only, nothing saved to diff against

    calls = []
    monkeypatch.setattr(
        "configgen.ui.main_window.QMessageBox.information",
        staticmethod(lambda *a, **k: calls.append(a)),
    )
    window._diff(view)
    assert calls


# -- dark mode -----------------------------------------------------------


def test_dark_mode_toggle_persists_and_restyles(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    assert window.dark is False

    window._on_dark_mode_toggled(True)
    assert window.dark is True
    assert "background-color: #0a0c0b" in window.styleSheet()

    # A fresh window for the same user picks up the persisted preference.
    window2 = MainWindow(window.user, window.store, window.schemas_dir, check_for_updates=False)
    qtbot.addWidget(window2)
    assert window2.dark is True


# -- Phase 13 dialogs (about / bulk / template editor / user admin / log) ----


def test_open_about_shows_the_about_dialog(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window._open_about()  # should not raise


def test_open_help_shows_the_help_dialog(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window._open_help()  # should not raise


def test_open_highlight_rules_shows_the_dialog(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window._open_highlight_rules()  # should not raise


def test_open_highlight_rules_refreshes_the_open_generator_view(qtbot, tmp_path: Path, monkeypatch):
    from configgen.ui.highlight_rules import DEFAULT_RULES, HighlightRule, save_custom_rules

    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._open_generator("widget_server")
    view = window.generator_view
    view.form.set_raw_values({"hostname": "web01", "note": "hi"})
    window._preview(view)
    assert len(view._highlighters[0]._custom_rules) == len(DEFAULT_RULES)  # seeded defaults

    def fake_exec(self):
        save_custom_rules([HighlightRule(word="web01", color="#ff00ff")])
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    window._open_highlight_rules()

    assert len(view._highlighters[0]._custom_rules) == 1


def test_open_bulk_dialog_offers_visible_schemas_and_refreshes_dashboard(
    qtbot, tmp_path: Path, monkeypatch
):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    old_dashboard = window.dashboard
    window._open_bulk_dialog()
    assert window.dashboard is not old_dashboard
    assert window.stack.currentWidget() is window.dashboard


def test_open_template_editor_and_refresh_picks_up_new_schema(qtbot, tmp_path: Path, monkeypatch):
    window, _, project = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    assert len(window.schemas) == 2

    def fake_exec(self):
        _write(
            project / "schemas" / "new_widget.yaml",
            "name: New Widget\nid: new_widget\nversion: 1\nstatus: published\n"
            "identity_field: name\ntemplate: widget.j2\nfields:\n"
            "  - key: name\n    label: Name\n    type: string\n    required: true\n",
        )
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("configgen.ui.template_editor.TemplateEditorWindow.exec", fake_exec)
    window._open_template_editor()

    assert len(window.schemas) == 3
    assert window.stack.currentWidget() is window.dashboard


def test_open_new_template_prompts_and_creates_schema(qtbot, tmp_path: Path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    assert len(window.schemas) == 2

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Brand New Schema", True))
    )
    monkeypatch.setattr(
        "configgen.ui.template_editor.TemplateEditorWindow.exec",
        lambda self: QDialog.DialogCode.Accepted,
    )
    window._open_new_template()

    assert len(window.schemas) == 3
    assert {s.id for s in window.schemas} >= {"brand_new_schema"}


def test_open_user_admin_refreshes_groups_and_dashboard(qtbot, tmp_path: Path, monkeypatch):
    window, store, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)

    def fake_exec(self):
        store.create_group("NetworkTeam")
        store.assign_user_to_group(window.user.username, "NetworkTeam")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("configgen.ui.user_admin.UserAdminWindow.exec", fake_exec)
    window._open_user_admin()
    assert window.user_groups == {"NetworkTeam"}


def test_open_generation_log_wires_regenerate_signal(qtbot, tmp_path: Path, monkeypatch):
    window, store, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)

    def fake_exec(self):
        self.regenerateRequested.emit("widget_server", {"hostname": "web09", "note": "x"})
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("configgen.ui.generation_log.GenerationLogDialog.exec", fake_exec)
    window._open_generation_log()

    assert window.generator_view is not None
    assert window.generator_view.schema.id == "widget_server"
    assert window.generator_view.form.raw_values()["hostname"] == "web09"


def test_regenerate_from_log_prefills_the_form(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window._regenerate_from_log("widget_server", {"hostname": "r1", "note": "n"})
    assert window.generator_view.form.raw_values() == {"hostname": "r1", "note": "n"}


def test_dashboard_reopen_button_prefills_the_form(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    window.dashboard.regenerateRequested.emit("widget_server", {"hostname": "r2", "note": "n2"})
    assert window.generator_view.form.raw_values() == {"hostname": "r2", "note": "n2"}


def test_ctrl_b_shortcut_opens_bulk_dialog(qtbot, tmp_path: Path, monkeypatch):
    """Confirms the Ctrl+B QShortcut's target by firing its `activated`
    signal directly, rather than relying on the offscreen QPA plugin to
    deliver a synthetic key event to it (it doesn't, reliably) — the
    plugin's key-event routing is Qt's own concern, not ours."""
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)

    matches = [s for s in window.findChildren(QShortcut) if s.key() == QKeySequence("Ctrl+B")]
    assert len(matches) == 1

    opened = []
    monkeypatch.setattr(
        "configgen.ui.main_window.BulkDialog.exec",
        lambda self: opened.append(True) or QDialog.DialogCode.Accepted,
    )
    matches[0].activated.emit()
    assert opened


def test_open_import_config_pack_refreshes_dashboard_with_new_schema(
    qtbot, tmp_path: Path, monkeypatch
):
    window, _, project = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    assert len(window.schemas) == 2

    def fake_exec(self):
        _write(
            project / "schemas" / "imported_widget.yaml",
            "name: Imported Widget\nid: imported_widget\nversion: 1\nstatus: published\n"
            "identity_field: name\ntemplate: widget.j2\nfields:\n"
            "  - key: name\n    label: Name\n    type: string\n    required: true\n",
        )
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("configgen.ui.config_pack_import.ImportConfigPackDialog.exec", fake_exec)
    window._open_import_config_pack()

    assert len(window.schemas) == 3
    assert window.stack.currentWidget() is window.dashboard


# -- update check (§16) ---------------------------------------------------------


def test_update_check_disabled_by_default_starts_no_worker(qtbot, tmp_path: Path, monkeypatch):
    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    assert window.update_worker is None


def test_update_check_enabled_starts_a_worker_and_shows_the_banner(
    qtbot, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    project = _make_project(tmp_path)
    store = AuthStore(tmp_path / "users.db")
    user = store.get_user("admin")
    monkeypatch.setattr(
        "configgen.ui.main_window.UpdateCheckWorker.run",
        lambda self: self.updateAvailable.emit("v9.9.9"),
    )

    window = MainWindow(user, store, project / "schemas", check_for_updates=True)
    qtbot.addWidget(window)
    window.update_worker.wait(2000)
    qtbot.waitUntil(lambda: window.update_banner.isHidden() is False, timeout=2000)

    assert "v9.9.9" in window.update_banner.label.text()


def test_update_check_toggle_persists_the_setting(qtbot, tmp_path: Path, monkeypatch):
    from configgen.ui.settings import auto_update_check_enabled

    window, _, _ = _isolated_window(tmp_path, monkeypatch)
    qtbot.addWidget(window)
    assert auto_update_check_enabled() is True

    window.sidebar.auto_update_checkbox.setChecked(False)

    assert auto_update_check_enabled() is False


def test_close_event_waits_for_running_update_worker(qtbot, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    project = _make_project(tmp_path)
    store = AuthStore(tmp_path / "users.db")
    user = store.get_user("admin")

    def slow_run(self):
        import time

        time.sleep(0.2)
        self.updateAvailable.emit("v9.9.9")

    monkeypatch.setattr("configgen.ui.main_window.UpdateCheckWorker.run", slow_run)

    window = MainWindow(user, store, project / "schemas", check_for_updates=True)
    qtbot.addWidget(window)
    window.close()  # must not raise / warn about a thread destroyed mid-run
    assert window.update_worker.isFinished()
