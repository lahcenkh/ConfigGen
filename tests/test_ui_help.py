from pathlib import Path

from configgen.ui.help import HelpDialog, doc_title, list_docs


def _write_docs(tmp_path: Path) -> Path:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "hooks.md").write_text(
        "# Hooks\n\nSee [Adding a Config](adding-a-config.md) too.\n", encoding="utf-8"
    )
    (docs_dir / "adding-a-config.md").write_text("# Adding a Config\n\nHello.\n", encoding="utf-8")
    return docs_dir


def test_doc_title_uses_curated_names_for_known_docs():
    assert doc_title(Path("hooks.md")) == "Hooks"
    assert doc_title(Path("schema-reference.md")) == "Schema Reference"


def test_doc_title_falls_back_to_titleized_stem_for_unknown_docs():
    assert doc_title(Path("some-new-doc.md")) == "Some New Doc"


def test_list_docs_missing_dir_returns_empty(tmp_path: Path):
    assert list_docs(tmp_path / "does-not-exist") == []


def test_list_docs_sorted_by_display_title(tmp_path: Path):
    docs_dir = _write_docs(tmp_path)
    docs = list_docs(docs_dir)
    assert [d.stem for d in docs] == ["adding-a-config", "hooks"]


def test_dialog_loads_shipped_docs_and_shows_first_by_default(qtbot, tmp_path: Path):
    docs_dir = _write_docs(tmp_path)
    dialog = HelpDialog(docs_dir=docs_dir)
    qtbot.addWidget(dialog)
    assert dialog.doc_list.count() == 2
    assert dialog.doc_list.item(0).text() == "Adding a Config"
    assert "Hello" in dialog.viewer.toPlainText()


def test_dialog_selecting_a_doc_shows_its_content(qtbot, tmp_path: Path):
    docs_dir = _write_docs(tmp_path)
    dialog = HelpDialog(docs_dir=docs_dir)
    qtbot.addWidget(dialog)
    dialog.doc_list.setCurrentRow(1)
    assert "Hooks" in dialog.viewer.toPlainText()


def test_dialog_internal_doc_link_navigates_to_that_doc(qtbot, tmp_path: Path):
    docs_dir = _write_docs(tmp_path)
    dialog = HelpDialog(docs_dir=docs_dir)
    qtbot.addWidget(dialog)
    dialog.doc_list.setCurrentRow(1)  # hooks.md, which links to adding-a-config.md

    from PySide6.QtCore import QUrl

    dialog._on_link_clicked(QUrl("adding-a-config.md"))
    assert dialog.doc_list.currentRow() == 0


def test_dialog_with_no_docs_shows_a_placeholder_message(qtbot, tmp_path: Path):
    dialog = HelpDialog(docs_dir=tmp_path / "no-docs-here")
    qtbot.addWidget(dialog)
    assert dialog.doc_list.count() == 0
    assert "No help documentation" in dialog.viewer.toPlainText()
