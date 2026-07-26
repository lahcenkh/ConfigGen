"""Unified diffs between rendered configs (§9 of the build plan).

Three modes, all built on the same `unified_diff`: two arbitrary files
(§9.1 "two files"), the two most recent saved outputs for a given
schema+identity (§9.1 "current vs. last saved"), and — since that's just
comparing two rendered texts — version comparison needs nothing extra
either, once the caller has rendered both versions' text.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from configgen.core.exporter import slugify

_STAMP_RE = re.compile(r"_(\d{14})\.txt$")


def unified_diff(text_a: str, text_b: str, *, label_a: str = "a", label_b: str = "b") -> str:
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    return "".join(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b))


def diff_files(path_a: str | Path, path_b: str | Path) -> str:
    path_a, path_b = Path(path_a), Path(path_b)
    text_a = path_a.read_text(encoding="utf-8")
    text_b = path_b.read_text(encoding="utf-8")
    return unified_diff(text_a, text_b, label_a=str(path_a), label_b=str(path_b))


def find_recent_outputs(
    output_dir: str | Path,
    schema_id: str,
    identity: str,
    *,
    doc_key: str = "primary",
    limit: int = 2,
) -> list[Path]:
    """Every saved document for this schema+identity+doc_key under
    `output_dir`, oldest first, capped to the `limit` most recent — the
    building block "current vs. last saved" is diffing the last two of."""
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return []
    pattern = f"*_{schema_id}_{slugify(identity)}_{doc_key}_*.txt"
    matches = []
    for path in output_dir.rglob(pattern):
        match = _STAMP_RE.search(path.name)
        if match:
            matches.append((match.group(1), path))
    matches.sort(key=lambda pair: pair[0])
    return [path for _, path in matches[-limit:]]
