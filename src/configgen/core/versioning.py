"""Schema + template version history (§10 of the build plan).

A "version" here is exactly the schema YAML's own `version:` field — this
mechanism doesn't keep an independent counter, so "which version produced
this issue" (§10.2, answered via the profile .json / header comment /
generation log already carrying `schema_version`) always points at a
concrete, retrievable snapshot: `<history_root>/<schema_id>/v<N>/`,
holding a copy of `schema.yaml` and every document template it referenced
at save time, plus one shared `manifest.json` recording who saved each
version and when.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from configgen.core.differ import unified_diff
from configgen.core.schema import load_schema_dict, schema_from_dict

_VERSION_LINE_RE = re.compile(r"(?m)^version:\s*\d+")


class VersioningError(Exception):
    pass


@dataclass
class VersionEntry:
    version: int
    author: str
    timestamp: str
    note: str | None = None


def _manifest_path(history_dir: Path) -> Path:
    return history_dir / "manifest.json"


def _load_manifest(history_dir: Path) -> list[VersionEntry]:
    manifest_path = _manifest_path(history_dir)
    if not manifest_path.is_file():
        return []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [VersionEntry(**v) for v in data.get("versions", [])]


def _save_manifest(history_dir: Path, entries: list[VersionEntry]) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    payload = {"versions": [asdict(e) for e in entries]}
    _manifest_path(history_dir).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _version_dir(history_root: Path, schema_id: str, version: int) -> Path:
    version_dir = history_root / schema_id / f"v{version}"
    if not version_dir.is_dir():
        raise VersioningError(f"no history found for '{schema_id}' version {version}")
    return version_dir


def list_versions(history_root: str | Path, schema_id: str) -> list[VersionEntry]:
    return _load_manifest(Path(history_root) / schema_id)


def save_version(
    history_root: str | Path,
    schema_path: str | Path,
    templates_dir: str | Path,
    *,
    author: str,
    note: str | None = None,
) -> VersionEntry:
    """Snapshots the current schema.yaml + its template file(s) as a new
    history version, numbered from the schema's own `version:` field.
    Raises if that version was already saved — bump `version:` first."""
    schema_path = Path(schema_path)
    data = load_schema_dict(schema_path)
    schema = schema_from_dict(data, source_path=schema_path)
    history_dir = Path(history_root) / schema.id
    entries = _load_manifest(history_dir)

    if any(e.version == schema.version for e in entries):
        raise VersioningError(
            f"version {schema.version} of '{schema.id}' is already saved; "
            "bump the schema's version field before saving again"
        )

    version_dir = history_dir / f"v{schema.version}"
    version_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(schema_path, version_dir / "schema.yaml")

    templates_snapshot_dir = version_dir / "templates"
    templates_snapshot_dir.mkdir(exist_ok=True)
    templates_dir = Path(templates_dir)
    for doc in schema.document_list():
        template_path = templates_dir / doc.template
        if template_path.is_file():
            shutil.copy2(template_path, templates_snapshot_dir / doc.template)

    entry = VersionEntry(
        version=schema.version,
        author=author,
        timestamp=datetime.now(timezone.utc).isoformat(),
        note=note,
    )
    entries.append(entry)
    entries.sort(key=lambda e: e.version)
    _save_manifest(history_dir, entries)
    return entry


def diff_versions(
    history_root: str | Path, schema_id: str, version_a: int, version_b: int
) -> dict[str, str]:
    """{relative_filename: unified_diff_text} for every file that differs
    between the two version snapshots (schema.yaml + each template)."""
    history_root = Path(history_root)
    dir_a = _version_dir(history_root, schema_id, version_a)
    dir_b = _version_dir(history_root, schema_id, version_b)

    files_a = {p.relative_to(dir_a) for p in dir_a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(dir_b) for p in dir_b.rglob("*") if p.is_file()}

    diffs = {}
    for rel in sorted(files_a | files_b, key=str):
        path_a, path_b = dir_a / rel, dir_b / rel
        text_a = path_a.read_text(encoding="utf-8") if path_a.is_file() else ""
        text_b = path_b.read_text(encoding="utf-8") if path_b.is_file() else ""
        if text_a != text_b:
            diffs[str(rel)] = unified_diff(
                text_a, text_b, label_a=f"v{version_a}/{rel}", label_b=f"v{version_b}/{rel}"
            )
    return diffs


def _bump_version_field(schema_path: Path, new_version: int) -> None:
    text = schema_path.read_text(encoding="utf-8")
    new_text, count = _VERSION_LINE_RE.subn(f"version: {new_version}", text, count=1)
    if count == 0:
        raise VersioningError(f"no top-level 'version:' field found in {schema_path}")
    schema_path.write_text(new_text, encoding="utf-8")


def restore_version(
    history_root: str | Path,
    schema_path: str | Path,
    templates_dir: str | Path,
    *,
    version: int,
    author: str,
    note: str | None = None,
) -> VersionEntry:
    """Replaces the live schema.yaml + templates with historical `version`'s
    content, then saves that restored state as a brand-new version (§10.4:
    "creating a new version entry") — restoring never overwrites or removes
    history, including the version it restores from."""
    schema_path = Path(schema_path)
    templates_dir = Path(templates_dir)
    schema_id = schema_from_dict(load_schema_dict(schema_path)).id
    history_dir = Path(history_root) / schema_id
    entries = _load_manifest(history_dir)
    if not entries:
        raise VersioningError(f"no history found for '{schema_id}'")

    source_dir = _version_dir(Path(history_root), schema_id, version)
    shutil.copy2(source_dir / "schema.yaml", schema_path)
    templates_snapshot_dir = source_dir / "templates"
    if templates_snapshot_dir.is_dir():
        for template_file in templates_snapshot_dir.iterdir():
            shutil.copy2(template_file, templates_dir / template_file.name)

    new_version = max(e.version for e in entries) + 1
    _bump_version_field(schema_path, new_version)

    return save_version(
        history_root,
        schema_path,
        templates_dir,
        author=author,
        note=note or f"Restored from version {version}",
    )
