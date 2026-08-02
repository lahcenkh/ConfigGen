from configgen.ui.highlight_rules import HighlightRule, load_custom_rules, save_custom_rules
from configgen.ui.highlight_rules_dialog import HighlightRulesDialog


def test_starts_with_previously_saved_rules(qtbot, _isolated_qsettings):
    save_custom_rules([HighlightRule(word="vlan", color="#ff0000", bold=True)])
    dialog = HighlightRulesDialog()
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "vlan"


def test_starts_seeded_with_the_default_rules_when_nothing_saved_yet(qtbot, _isolated_qsettings):
    dialog = HighlightRulesDialog()
    qtbot.addWidget(dialog)
    words = {dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())}
    assert "interface" in words
    assert "no" in words


def test_add_rule_appends_a_row(qtbot, _isolated_qsettings):
    save_custom_rules([])  # a deliberately empty, already-saved state
    dialog = HighlightRulesDialog()
    qtbot.addWidget(dialog)
    dialog.word_input.setText("reboot")
    dialog._pending_color = "#123456"
    dialog._add_rule()
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "reboot"
    assert dialog.table.item(0, 1).text() == "#123456"


def test_add_rule_with_blank_word_does_nothing(qtbot, _isolated_qsettings, monkeypatch):
    save_custom_rules([])
    dialog = HighlightRulesDialog()
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "configgen.ui.highlight_rules_dialog.QMessageBox.information",
        staticmethod(lambda *a, **k: None),
    )
    dialog.word_input.setText("   ")
    dialog._add_rule()
    assert dialog.table.rowCount() == 0


def test_remove_selected_deletes_the_rule(qtbot, _isolated_qsettings):
    save_custom_rules([])
    dialog = HighlightRulesDialog()
    qtbot.addWidget(dialog)
    dialog.word_input.setText("reboot")
    dialog._add_rule()
    dialog.table.selectRow(0)
    dialog._remove_selected()
    assert dialog.table.rowCount() == 0


def test_save_persists_the_rules(qtbot, _isolated_qsettings):
    save_custom_rules([])
    dialog = HighlightRulesDialog()
    qtbot.addWidget(dialog)
    dialog.word_input.setText("reboot")
    dialog._pending_color = "#00ff00"
    dialog._add_rule()
    dialog._save()

    saved = load_custom_rules()
    assert saved == [HighlightRule(word="reboot", color="#00ff00", bold=False)]
