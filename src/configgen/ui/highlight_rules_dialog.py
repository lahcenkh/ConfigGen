"""Custom highlight-rules editor — lets a user add their own word/color
rules on top of the built-in Jinja and network-config highlighting
(`highlighters.py`), persisted via `highlight_rules.py`. Rules apply the
next time a config preview or template editor is opened — there's no
live-editing session to push into, since the windows that use these
highlighters are all modal.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from configgen.ui.highlight_rules import HighlightRule, load_custom_rules, save_custom_rules

_DEFAULT_COLOR = "#f59e0b"


class HighlightRulesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Custom Highlight Rules")
        self.resize(480, 420)
        self._rules: list[HighlightRule] = list(load_custom_rules())
        self._pending_color = _DEFAULT_COLOR

        layout = QVBoxLayout(self)

        help_label = QLabel(
            "Highlight your own words wherever they appear in a rendered config "
            "or template source — layered on top of the built-in highlighting."
        )
        help_label.setObjectName("muted")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Word", "Color", "Bold"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        add_row = QHBoxLayout()
        self.word_input = QLineEdit()
        self.word_input.setPlaceholderText("word to highlight")
        self.word_input.returnPressed.connect(self._add_rule)
        add_row.addWidget(self.word_input, stretch=1)

        self.color_button = QPushButton()
        self.color_button.setFixedWidth(48)
        self.color_button.clicked.connect(self._pick_color)
        add_row.addWidget(self.color_button)

        self.bold_checkbox = QCheckBox("Bold")
        add_row.addWidget(self.bold_checkbox)

        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add_rule)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        buttons = QHBoxLayout()
        remove_button = QPushButton("Remove Selected")
        remove_button.setObjectName("secondary")
        remove_button.clicked.connect(self._remove_selected)
        buttons.addWidget(remove_button)
        buttons.addStretch()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        buttons.addWidget(save_button)
        close_button = QPushButton("Close")
        close_button.setObjectName("secondary")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._update_color_button()
        self._refresh_table()

    def _update_color_button(self) -> None:
        self.color_button.setStyleSheet(
            f"background-color: {self._pending_color}; border: 1px solid #000000;"
        )

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._pending_color), self, "Choose a color")
        if color.isValid():
            self._pending_color = color.name()
            self._update_color_button()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._rules))
        for row, rule in enumerate(self._rules):
            self.table.setItem(row, 0, QTableWidgetItem(rule.word))
            color_item = QTableWidgetItem(rule.color)
            color_item.setForeground(QColor(rule.color))
            self.table.setItem(row, 1, color_item)
            self.table.setItem(row, 2, QTableWidgetItem("Yes" if rule.bold else "No"))

    def _add_rule(self) -> None:
        word = self.word_input.text().strip()
        if not word:
            QMessageBox.information(self, "Nothing to add", "Type a word to highlight first.")
            return
        self._rules.append(
            HighlightRule(word=word, color=self._pending_color, bold=self.bold_checkbox.isChecked())
        )
        self.word_input.clear()
        self.bold_checkbox.setChecked(False)
        self._refresh_table()

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            del self._rules[row]
        self._refresh_table()

    def _save(self) -> None:
        save_custom_rules(self._rules)
        self.accept()
