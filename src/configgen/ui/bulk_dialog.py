"""Bulk generation dialog (§8.5) — file picker, progress, error summary
with CSV export.

`run_bulk` (§8) validates every row, renders the valid ones, and writes
one shared `batch_manifest.json` before returning; there's no per-row
progress callback to hook into, so the progress bar here is a "this
locked up because it's genuinely working" indicator (busy/indeterminate
mode), not a percentage — the same one-shot-call shape `MainWindow._generate`
already uses for a single row.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from configgen.core.auth import AuthStore, User, visible_schemas
from configgen.core.bulk import BulkResult, read_rows, run_bulk
from configgen.core.db import DatabaseError, database_for_schema
from configgen.core.registry import load_project_filters
from configgen.core.schema import (
    Schema,
    project_dirs_for,
    project_preflight_dir_for,
    project_root_for,
)
from configgen.paths import output_dir
from configgen.prepare import services_for_schema


class BulkDialog(QDialog):
    def __init__(
        self,
        user: User,
        store: AuthStore,
        schemas: list[Schema],
        schema_paths: dict[str, Path],
        user_groups: set[str],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.user = user
        self.store = store
        self.schema_paths = schema_paths
        self.schemas = visible_schemas(user, schemas, user_groups)
        self.input_path: Path | None = None
        self.result: BulkResult | None = None

        self.setWindowTitle("Bulk Generate")
        self.resize(700, 500)
        layout = QVBoxLayout(self)

        schema_row = QHBoxLayout()
        schema_row.addWidget(QLabel("Schema"))
        self.schema_combo = QComboBox()
        for schema in self.schemas:
            self.schema_combo.addItem(schema.name, schema.id)
        schema_row.addWidget(self.schema_combo, stretch=1)
        layout.addLayout(schema_row)

        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setReadOnly(True)
        file_row.addWidget(self.file_input, stretch=1)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse)
        file_row.addWidget(browse_button)
        layout.addLayout(file_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.error_table = QTableWidget(0, 2)
        self.error_table.setHorizontalHeaderLabels(["Row", "Errors"])
        self.error_table.setAlternatingRowColors(True)
        layout.addWidget(self.error_table, stretch=1)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self._run)
        self.export_button = QPushButton("Export Errors to CSV")
        self.export_button.setObjectName("secondary")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_errors)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

    def _browse(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select input file", "", "CSV/XLSX files (*.csv *.xlsx *.xlsm)"
        )
        if path_str:
            self.input_path = Path(path_str)
            self.file_input.setText(path_str)

    def _selected_schema(self) -> Schema | None:
        schema_id = self.schema_combo.currentData()
        for schema in self.schemas:
            if schema.id == schema_id:
                return schema
        return None

    def _run(self) -> None:
        schema = self._selected_schema()
        if schema is None:
            QMessageBox.warning(self, "No schema", "Select a schema first.")
            return
        if self.input_path is None:
            QMessageBox.warning(self, "No file", "Choose a CSV or XLSX file first.")
            return

        schema_path = self.schema_paths[schema.id]
        try:
            rows = read_rows(self.input_path)
        except OSError as exc:
            QMessageBox.warning(self, "Could not read file", str(exc))
            return
        if not rows:
            QMessageBox.warning(self, "Empty file", f"No rows found in {self.input_path}.")
            return

        try:
            database = database_for_schema(schema, schema_path)
        except DatabaseError as exc:
            QMessageBox.warning(self, "Database error", str(exc))
            return

        templates_dir, prepare_dir = project_dirs_for(schema_path)
        self.progress.setVisible(True)
        self.run_button.setEnabled(False)
        try:
            self.result = run_bulk(
                schema,
                rows,
                templates_dir=templates_dir,
                prepare_dir=prepare_dir,
                output_root=output_dir(),
                source=str(self.input_path),
                username=self.user.username,
                database=database,
                services=services_for_schema(schema_path),
                preflight_dir=project_preflight_dir_for(schema_path),
                filters=load_project_filters(project_root_for(schema_path)),
            )
        finally:
            self.progress.setVisible(False)
            self.run_button.setEnabled(True)

        for row in self.result.generated:
            for filename in row["documents"].values():
                self.store.record_generation(
                    self.user,
                    schema_id=schema.id,
                    schema_version=schema.version,
                    form_inputs=row["inputs"],
                    output_filename=filename,
                    group_name=schema.group,
                    bulk_batch_id=self.result.batch_id,
                )

        self.summary_label.setText(
            f"{self.result.valid_count} valid, {self.result.error_count} errors — "
            f"output: {self.result.output_dir}"
        )
        self.error_table.setRowCount(len(self.result.row_errors))
        for row, row_error in enumerate(self.result.row_errors):
            messages = "; ".join(f"{k}: {v}" for k, v in row_error.errors.items())
            self.error_table.setItem(row, 0, QTableWidgetItem(str(row_error.row_number)))
            self.error_table.setItem(row, 1, QTableWidgetItem(messages))
        self.export_button.setEnabled(bool(self.result.row_errors))

    def _export_errors(self) -> None:
        if self.result is None or not self.result.row_errors:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export error report", "bulk_errors.csv", "CSV files (*.csv)"
        )
        if not path_str:
            return
        with open(path_str, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["row_number", "errors"])
            for row_error in self.result.row_errors:
                messages = "; ".join(f"{k}: {v}" for k, v in row_error.errors.items())
                writer.writerow([row_error.row_number, messages])
