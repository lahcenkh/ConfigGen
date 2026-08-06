"""Batch generation from a CSV/XLSX file or a database query (§8 of the
build plan).

Every row is validated (and, if the schema has one, run through its
hook) before anything is rendered — a row that fails either step
is reported, never generated, and never blocks the rest of the batch.
Valid rows are rendered and saved together under one `batch_{stamp}/`
folder, with a shared `bulk_batch_id` linking their generation-log
entries (§13.7) back to this one import.
"""

from __future__ import annotations

import csv
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openpyxl

from configgen.core.db import Database
from configgen.core.exporter import resolve_output_dir, save_documents
from configgen.core.preflight import run_preflight
from configgen.core.renderer import RenderError, render_documents
from configgen.core.schema import Schema
from configgen.core.validators import FieldValidationError, validate_values
from configgen.hooks import HookError, Services, run_hook

logger = logging.getLogger(__name__)


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def read_xlsx_rows(path: str | Path) -> list[dict[str, object]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows_iter = sheet.iter_rows(values_only=True)
        header = [str(cell) if cell is not None else "" for cell in next(rows_iter)]
        rows = []
        for raw_row in rows_iter:
            if all(cell in (None, "") for cell in raw_row):
                continue  # openpyxl can yield trailing blank rows
            row = dict(zip(header, raw_row, strict=False))
            rows.append({key: ("" if value is None else value) for key, value in row.items()})
        return rows
    finally:
        workbook.close()


def read_rows(path: str | Path) -> list[dict]:
    """Column headers must match schema field keys; extra columns are
    ignored by validate_values, missing required ones fail validation."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return read_xlsx_rows(path)
    return read_csv_rows(path)


@dataclass
class RowError:
    row_number: int  # 1-based, header counted as row 1 (matches a spreadsheet's own numbering)
    errors: dict[str, str]


@dataclass
class BulkResult:
    batch_id: str
    output_dir: Path
    manifest_path: Path
    generated: list[dict]
    row_errors: list[RowError]

    @property
    def valid_count(self) -> int:
        return len(self.generated)

    @property
    def error_count(self) -> int:
        return len(self.row_errors)


def run_bulk(
    schema: Schema,
    rows: list[dict],
    *,
    templates_dir: Path | str,
    hooks_dir: Path | str | None,
    output_root: Path | str,
    source: str,
    username: str = "unknown",
    database: Database | None = None,
    services: Services | None = None,
    preflight_dir: Path | str | None = None,
    filters: dict | None = None,
    variant: str | None = None,
    timestamp: datetime | None = None,
) -> BulkResult:
    if schema.hook and (services is None or hooks_dir is None):
        raise ValueError(
            f"schema '{schema.id}' declares a hook; "
            "run_bulk needs both `services` and `hooks_dir` to run it"
        )

    timestamp = timestamp or datetime.now()
    batch_id = uuid.uuid4().hex
    batch_name = f"batch_{timestamp.strftime('%Y%m%d%H%M%S')}"
    logger.info(
        "bulk %s: schema=%s rows=%d source=%s username=%s",
        batch_id,
        schema.id,
        len(rows),
        source,
        username,
    )

    ready: list[tuple[int, dict, dict]] = []  # (row_number, raw_row, render_context)
    row_errors: list[RowError] = []

    for row_number, raw_row in enumerate(rows, start=2):
        try:
            values = validate_values(schema, raw_row, database=database)
        except FieldValidationError as exc:
            logger.info("bulk %s: row %d failed validation: %s", batch_id, row_number, exc.errors)
            row_errors.append(RowError(row_number=row_number, errors=exc.errors))
            continue

        if schema.hook:
            try:
                context = run_hook(hooks_dir, schema.hook, values, {"username": username}, services)
            except HookError as exc:
                logger.info(
                    "bulk %s: row %d hook '%s' rejected: %s",
                    batch_id,
                    row_number,
                    schema.hook,
                    exc.errors,
                )
                row_errors.append(RowError(row_number=row_number, errors=exc.errors))
                continue
        else:
            context = values

        ready.append((row_number, raw_row, context))

    generated: list[dict] = []
    for row_number, raw_row, context in ready:
        try:
            rendered = render_documents(
                schema,
                context,
                templates_dir=templates_dir,
                username=username,
                timestamp=timestamp,
                filters=filters,
            )
        except RenderError as exc:
            logger.info("bulk %s: row %d render failed: %s", batch_id, row_number, exc)
            row_errors.append(RowError(row_number=row_number, errors={"_render": str(exc)}))
            continue

        preflight_warnings: dict[str, list[str]] = {}
        if schema.preflight:
            for doc_key, text in rendered.items():
                doc_warnings = run_preflight(schema.preflight, text, preflight_dir)
                if doc_warnings:
                    preflight_warnings[doc_key] = doc_warnings

        result = save_documents(
            rendered,
            schema,
            raw_values=raw_row,
            output_root=output_root,
            username=username,
            variant=variant,
            timestamp=timestamp,
            subdir=batch_name,
        )
        row_entry = {
            "row_number": row_number,
            "inputs": raw_row,
            "documents": {key: path.name for key, path in result.document_paths.items()},
        }
        if preflight_warnings:
            row_entry["preflight_warnings"] = preflight_warnings
        generated.append(row_entry)

    output_dir = resolve_output_dir(output_root, username, schema, subdir=batch_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "schema_id": schema.id,
        "schema_version": schema.version,
        "source": source,
        "username": username,
        "generated_at": timestamp.isoformat(),
        "valid_count": len(generated),
        "error_count": len(row_errors),
        "rows": generated,
        "errors": [{"row_number": e.row_number, "errors": e.errors} for e in row_errors],
    }
    manifest_path = output_dir / "batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    logger.info(
        "bulk %s: finished — %d valid, %d errors, output=%s",
        batch_id,
        len(generated),
        len(row_errors),
        output_dir,
    )
    return BulkResult(
        batch_id=batch_id,
        output_dir=output_dir,
        manifest_path=manifest_path,
        generated=generated,
        row_errors=row_errors,
    )
