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
import logging
import shutil
from pathlib import Path

import openpyxl
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
from configgen.hooks import services_for_schema
from configgen.paths import output_dir

logger = logging.getLogger(__name__)


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
        download_template_button = QPushButton("Download Input Template")
        download_template_button.setObjectName("secondary")
        download_template_button.clicked.connect(self._download_template)
        schema_row.addWidget(download_template_button)
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
        self.copy_configs_button = QPushButton("Copy Configs To…")
        self.copy_configs_button.setObjectName("secondary")
        self.copy_configs_button.setEnabled(False)
        self.copy_configs_button.clicked.connect(self._copy_configs_to_folder)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.copy_configs_button)
        layout.addLayout(buttons)

    def _download_template(self) -> None:
        """A blank input file with just the header row `read_rows()`
        actually expects (§8: "column headers must match schema field
        keys") — so a user can fill it in offline and re-upload it via
        Browse… instead of guessing column names from the schema."""
        schema = self._selected_schema()
        if schema is None:
            QMessageBox.warning(self, "No schema", "Select a schema first.")
            return

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save input template",
            f"{schema.id}_template.csv",
            "CSV files (*.csv);;Excel files (*.xlsx)",
        )
        if not path_str:
            return

        headers = [field.key for field in schema.fields]
        path = Path(path_str)
        if path.suffix.lower() == ".xlsx":
            workbook = openpyxl.Workbook()
            workbook.active.append(headers)
            workbook.save(path_str)
        else:
            with open(path_str, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(headers)

        self.summary_label.setText(f"Input template saved to {path_str}.")

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

        templates_dir, hooks_dir = project_dirs_for(schema_path)
        self.progress.setVisible(True)
        self.run_button.setEnabled(False)
        logger.info("bulk: schema=%s rows=%d source=%s", schema.id, len(rows), self.input_path)
        try:
            self.result = run_bulk(
                schema,
                rows,
                templates_dir=templates_dir,
                hooks_dir=hooks_dir,
                output_root=output_dir(),
                source=str(self.input_path),
                username=self.user.username,
                database=database,
                services=services_for_schema(schema_path),
                preflight_dir=project_preflight_dir_for(schema_path),
                filters=load_project_filters(project_root_for(schema_path)),
            )
        except Exception as exc:  # noqa: BLE001 - a batch must never fail silently
            logger.exception("bulk: schema=%s crashed", schema.id)
            QMessageBox.critical(
                self,
                "Bulk generation failed",
                f"{exc}\n\nSee logs/app.log for the full traceback.",
            )
            return
        finally:
            self.progress.setVisible(False)
            self.run_button.setEnabled(True)

        logger.info(
            "bulk: schema=%s finished — %d valid, %d errors",
            schema.id,
            self.result.valid_count,
            self.result.error_count,
        )
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
        self.copy_configs_button.setEnabled(self.result.valid_count > 0)

    def _copy_configs_to_folder(self) -> None:
        """Copies just the rendered .txt configs from this batch to a
        second location of the user's choosing — the per-row .json
        profiles and batch_manifest.json (bookkeeping, needed for Reopen
        and the audit trail) stay behind in the regular output/ tree."""
        if self.result is None or self.result.valid_count == 0:
            return
        dest_str = QFileDialog.getExistingDirectory(self, "Copy batch configs to")
        if not dest_str:
            return
        dest = Path(dest_str)
        txt_files = sorted(self.result.output_dir.glob("*.txt"))
        for txt_file in txt_files:
            shutil.copy2(txt_file, dest / txt_file.name)
        self.summary_label.setText(f"{len(txt_files)} config file(s) copied to {dest_str}.")

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
