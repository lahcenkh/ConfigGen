"""Generation log viewer (§13.7) — filterable audit trail with
click-to-regenerate.

Role-based visibility (own/group/all) is already enforced server-side by
`AuthStore.list_generation_log`; the filters here (user/group/schema/date
range) only narrow what's already visible, never widen it.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from configgen.core.auth import AuthStore, User

_ALL = "(all)"


class GenerationLogDialog(QDialog):
    regenerateRequested = Signal(str, dict)

    def __init__(self, store: AuthStore, user: User, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.user = user
        self.setWindowTitle("Generation Log")
        self.resize(900, 560)

        self._entries = self.store.list_generation_log(user)

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_filters())

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Timestamp", "User", "Group", "Schema", "Version", "Output filename"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self._show_selected)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        regenerate_button = QPushButton("View Inputs / Regenerate")
        regenerate_button.clicked.connect(self._show_selected)
        buttons.addWidget(regenerate_button)
        layout.addLayout(buttons)

        self._apply_filters()

    # -- filters -------------------------------------------------------

    def _build_filters(self) -> QHBoxLayout:
        row = QHBoxLayout()

        usernames = sorted({e["username"] for e in self._entries})
        groups = sorted({e["group_name"] for e in self._entries if e["group_name"]})
        schemas = sorted({e["schema_id"] for e in self._entries})

        row.addWidget(QLabel("User"))
        self.user_filter = QComboBox()
        self.user_filter.addItems([_ALL, *usernames])
        self.user_filter.currentIndexChanged.connect(self._apply_filters)
        row.addWidget(self.user_filter)

        row.addWidget(QLabel("Group"))
        self.group_filter = QComboBox()
        self.group_filter.addItems([_ALL, *groups])
        self.group_filter.currentIndexChanged.connect(self._apply_filters)
        row.addWidget(self.group_filter)

        row.addWidget(QLabel("Schema"))
        self.schema_filter = QComboBox()
        self.schema_filter.addItems([_ALL, *schemas])
        self.schema_filter.currentIndexChanged.connect(self._apply_filters)
        row.addWidget(self.schema_filter)

        row.addWidget(QLabel("From"))
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDate(date(2000, 1, 1))
        self.date_from.dateChanged.connect(self._apply_filters)
        row.addWidget(self.date_from)

        row.addWidget(QLabel("To"))
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDate(date.today())
        self.date_to.dateChanged.connect(self._apply_filters)
        row.addWidget(self.date_to)

        return row

    def _matches_filters(self, entry: dict) -> bool:
        user = self.user_filter.currentText()
        group = self.group_filter.currentText()
        schema_id = self.schema_filter.currentText()
        if user != _ALL and entry["username"] != user:
            return False
        if group != _ALL and entry["group_name"] != group:
            return False
        if schema_id != _ALL and entry["schema_id"] != schema_id:
            return False
        entry_date = datetime.fromisoformat(entry["created_at"]).date()
        if not (self.date_from.date().toPython() <= entry_date <= self.date_to.date().toPython()):
            return False
        return True

    def _apply_filters(self, *_args) -> None:
        self._filtered = [e for e in self._entries if self._matches_filters(e)]
        self.table.setRowCount(len(self._filtered))
        for row, entry in enumerate(self._filtered):
            self.table.setItem(row, 0, QTableWidgetItem(entry["created_at"]))
            self.table.setItem(row, 1, QTableWidgetItem(entry["username"]))
            self.table.setItem(row, 2, QTableWidgetItem(entry["group_name"] or ""))
            self.table.setItem(row, 3, QTableWidgetItem(entry["schema_id"]))
            self.table.setItem(row, 4, QTableWidgetItem(str(entry["schema_version"])))
            self.table.setItem(row, 5, QTableWidgetItem(entry["output_filename"]))

    # -- selection -------------------------------------------------------

    def _show_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._filtered):
            return
        entry = self._filtered[row]
        form_inputs = json.loads(entry["form_inputs"])

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Inputs — {entry['output_filename']}")
        dialog.resize(520, 420)
        layout = QVBoxLayout(dialog)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(json.dumps(form_inputs, indent=2, default=str))
        layout.addWidget(text)

        buttons = QHBoxLayout()
        regenerate_button = QPushButton("Regenerate with these inputs")
        regenerate_button.clicked.connect(
            lambda: self._regenerate(entry["schema_id"], form_inputs, dialog)
        )
        close_button = QPushButton("Close")
        close_button.setObjectName("secondary")
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(regenerate_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        dialog.exec()

    def _regenerate(self, schema_id: str, form_inputs: dict, dialog: QDialog) -> None:
        self.regenerateRequested.emit(schema_id, form_inputs)
        dialog.accept()
        self.accept()
