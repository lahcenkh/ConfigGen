"""Filename building and per-document saving.

Naming convention (carried over from the private build, §7/§19):
`{group}_{id}_{identity}_{DOCKEY}_{variant}_{stamp}.txt`, plus one shared
`.json` profile per generation event. The doc-key token always occupies the
same position so reopening a multi-document set can find its shared profile
by stripping that one token back out — see `profile_filename_for`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from configgen.core.schema import Schema

_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


def _slug(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.strip()).strip("-")
    return slug or "x"


def slugify(text: str) -> str:
    """Public alias of the same slugging rule filenames are built with —
    for anything (like differ.py's --last lookup) that needs to recognize
    a filename this module already produced."""
    return _slug(text)


def _stamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y%m%d%H%M%S")


def _base_parts(schema: Schema, context: dict) -> list[str]:
    group = _slug(schema.group) if schema.group else "ungrouped"
    identity = "output"
    if schema.identity_field and context.get(schema.identity_field) is not None:
        identity = _slug(str(context[schema.identity_field]))
    return [group, schema.id, identity]


def build_filename(
    schema: Schema,
    doc_key: str,
    context: dict,
    *,
    variant: str | None = None,
    timestamp: datetime | None = None,
) -> str:
    timestamp = timestamp or datetime.now()
    parts = [*_base_parts(schema, context), doc_key]
    if schema.supports_variants and variant:
        parts.append(_slug(variant))
    parts.append(_stamp(timestamp))
    return "_".join(parts) + ".txt"


def build_profile_filename(
    schema: Schema,
    context: dict,
    *,
    variant: str | None = None,
    timestamp: datetime | None = None,
) -> str:
    timestamp = timestamp or datetime.now()
    parts = _base_parts(schema, context)
    if schema.supports_variants and variant:
        parts.append(_slug(variant))
    parts.append(_stamp(timestamp))
    return "_".join(parts) + ".json"


def profile_filename_for(doc_filename: str, doc_key: str) -> str:
    """Given one document's saved filename, returns the shared profile's
    filename by stripping that document's key token back out.

    Strips the *rightmost* `_{doc_key}_` — not every token equal to
    doc_key — because schema ids are conventionally snake_case (e.g.
    `primary_config`) and can otherwise contain the doc key as a substring.
    build_filename always places the real doc-key segment last (right
    before an optional variant and the timestamp), so the rightmost match
    is always the right one.
    """
    stem = doc_filename.rsplit(".", 1)[0]
    marker = f"_{doc_key}_"
    idx = stem.rfind(marker)
    if idx == -1:
        raise ValueError(f"doc_key '{doc_key}' not found in filename '{doc_filename}'")
    stem = stem[:idx] + stem[idx + len(marker) - 1 :]  # keep one separating underscore
    return stem + ".json"


def resolve_profile_path(doc_path: str | Path, doc_key: str) -> Path:
    """The "reopen" operation (§7/§19): given the path to one saved
    document, finds its sibling shared profile .json on disk."""
    doc_path = Path(doc_path)
    return doc_path.parent / profile_filename_for(doc_path.name, doc_key)


def load_profile(profile_path: str | Path) -> dict:
    return json.loads(Path(profile_path).read_text(encoding="utf-8"))


def resolve_output_dir(
    output_root: Path | str, username: str, schema: Schema, *, subdir: str | None = None
) -> Path:
    """`{output_root}/{username}/{group}/[subdir]` — the one place this
    layout is decided, so a bulk batch folder (§8) and a single save
    (below) can never disagree about where things land."""
    group_slug = _slug(schema.group) if schema.group else "ungrouped"
    target = Path(output_root) / username / group_slug
    return target / subdir if subdir else target


@dataclass
class SaveResult:
    output_dir: Path
    document_paths: dict[str, Path]
    profile_path: Path


def save_documents(
    rendered: dict[str, str],
    schema: Schema,
    *,
    raw_values: dict,
    output_root: Path | str,
    username: str = "unknown",
    variant: str | None = None,
    timestamp: datetime | None = None,
    subdir: str | None = None,
) -> SaveResult:
    """Writes one .txt per rendered document plus a shared .json profile,
    under `{output_root}/{username}/{group}/[subdir]/`."""
    timestamp = timestamp or datetime.now()
    target_dir = resolve_output_dir(output_root, username, schema, subdir=subdir)
    target_dir.mkdir(parents=True, exist_ok=True)

    document_paths: dict[str, Path] = {}
    for doc_key, text in rendered.items():
        filename = build_filename(schema, doc_key, raw_values, variant=variant, timestamp=timestamp)
        path = target_dir / filename
        path.write_text(text, encoding="utf-8")
        document_paths[doc_key] = path

    profile_filename = build_profile_filename(
        schema, raw_values, variant=variant, timestamp=timestamp
    )
    profile_path = target_dir / profile_filename
    profile = {
        "schema_id": schema.id,
        "schema_version": schema.version,
        "group": schema.group,
        "username": username,
        "variant": variant,
        "generated_at": timestamp.isoformat(),
        "inputs": raw_values,
        "documents": {key: path.name for key, path in document_paths.items()},
    }
    profile_path.write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")

    return SaveResult(
        output_dir=target_dir, document_paths=document_paths, profile_path=profile_path
    )
