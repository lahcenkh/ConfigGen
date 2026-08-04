"""Help dialog — browses the shipped docs/*.md files in-app (bundled by
ConfigGen.spec, resolved via paths.docs_dir()), so a user never has to leave
the app to find out how something works."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from configgen import paths

_TITLES = {
    "adding-a-config": "Adding a Config",
    "bulk-generation": "Bulk Generation",
    "hooks": "Hooks",
    "roles-and-groups": "Roles and Groups",
    "schema-reference": "Schema Reference",
    "troubleshooting": "Troubleshooting",
}


def doc_title(doc_path: Path) -> str:
    """A shipped doc's display name — a curated title for the docs we know
    about, else a reasonable fallback so a new doc still shows up."""
    return _TITLES.get(doc_path.stem, doc_path.stem.replace("-", " ").title())


def list_docs(docs_dir: Path) -> list[Path]:
    """Every shipped .md doc, alphabetized by its display title. Empty (not
    an error) if docs_dir doesn't exist — a dev checkout that hasn't been
    packaged yet, or a stripped-down build, just shows no docs."""
    if not docs_dir.is_dir():
        return []
    return sorted(docs_dir.glob("*.md"), key=doc_title)


class HelpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, docs_dir: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(900, 600)
        self._docs = list_docs(docs_dir if docs_dir is not None else paths.docs_dir())

        layout = QHBoxLayout(self)

        self.doc_list = QListWidget()
        self.doc_list.setObjectName("doc-list")
        self.doc_list.setMaximumWidth(220)
        for doc_path in self._docs:
            self.doc_list.addItem(doc_title(doc_path))
        self.doc_list.currentRowChanged.connect(self._show_doc)
        layout.addWidget(self.doc_list)

        right = QVBoxLayout()
        self.viewer = QTextBrowser()
        # Internal doc-to-doc links (docs cross-reference each other, e.g.
        # "[hooks.md](hooks.md)") should jump to that doc in this same
        # dialog, not try to open a browser on a relative path that means
        # nothing outside the docs/ folder.
        self.viewer.setOpenLinks(False)
        self.viewer.anchorClicked.connect(self._on_link_clicked)
        right.addWidget(self.viewer)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        right.addWidget(close_button)
        layout.addLayout(right)

        if self._docs:
            self.doc_list.setCurrentRow(0)
        else:
            self.viewer.setPlainText("No help documentation is available in this build.")

    def _show_doc(self, row: int) -> None:
        if row < 0 or row >= len(self._docs):
            return
        self.viewer.setMarkdown(self._docs[row].read_text(encoding="utf-8"))

    def _on_link_clicked(self, url) -> None:
        target_stem = Path(url.toString().split("#")[0]).stem
        for row, doc_path in enumerate(self._docs):
            if doc_path.stem == target_stem:
                self.doc_list.setCurrentRow(row)
                return
