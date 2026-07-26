from datetime import datetime
from pathlib import Path

from configgen.core.differ import diff_files, find_recent_outputs, unified_diff
from configgen.core.exporter import build_filename
from configgen.core.schema import Schema


def test_unified_diff_identical_texts_is_empty():
    assert unified_diff("same\n", "same\n") == ""


def test_unified_diff_shows_added_line():
    diff = unified_diff("a\n", "a\nb\n")
    assert "+b" in diff
    assert diff.startswith("--- a")


def test_unified_diff_shows_removed_line():
    diff = unified_diff("a\nb\n", "a\n")
    assert "-b" in diff


def test_unified_diff_uses_given_labels():
    diff = unified_diff("x\n", "y\n", label_a="old.txt", label_b="new.txt")
    assert "--- old.txt" in diff
    assert "+++ new.txt" in diff


def test_diff_files_reads_and_diffs(tmp_path: Path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("hello\n", encoding="utf-8")
    file_b.write_text("goodbye\n", encoding="utf-8")
    diff = diff_files(file_a, file_b)
    assert "-hello" in diff
    assert "+goodbye" in diff
    assert str(file_a) in diff
    assert str(file_b) in diff


# -- find_recent_outputs -------------------------------------------------


def _schema(**overrides) -> Schema:
    defaults = dict(name="Widget", id="widget", fields=[], template="widget.j2")
    defaults.update(overrides)
    return Schema(**defaults)


def _touch_output(
    tmp_path: Path, schema: Schema, identity: str, doc_key: str, ts: datetime
) -> Path:
    name = build_filename(schema, doc_key, {"hostname": identity}, timestamp=ts)
    path = tmp_path / name
    path.write_text(f"version at {ts.isoformat()}", encoding="utf-8")
    return path


def test_find_recent_outputs_missing_dir_returns_empty(tmp_path: Path):
    assert find_recent_outputs(tmp_path / "nope", "widget", "web01") == []


def test_find_recent_outputs_no_matches_returns_empty(tmp_path: Path):
    assert find_recent_outputs(tmp_path, "widget", "web01") == []


def test_find_recent_outputs_sorted_oldest_first(tmp_path: Path):
    schema = _schema(identity_field="hostname")
    older = _touch_output(tmp_path, schema, "web01", "primary", datetime(2026, 1, 1, 10, 0, 0))
    newer = _touch_output(tmp_path, schema, "web01", "primary", datetime(2026, 1, 2, 10, 0, 0))

    matches = find_recent_outputs(tmp_path, "widget", "web01")
    assert matches == [older, newer]


def test_find_recent_outputs_respects_limit(tmp_path: Path):
    schema = _schema(identity_field="hostname")
    for day in (1, 2, 3):
        _touch_output(tmp_path, schema, "web01", "primary", datetime(2026, 1, day, 10, 0, 0))

    matches = find_recent_outputs(tmp_path, "widget", "web01", limit=2)
    assert len(matches) == 2
    assert matches[0].name.split("_")[-1] < matches[1].name.split("_")[-1]


def test_find_recent_outputs_filters_by_doc_key(tmp_path: Path):
    schema = _schema(identity_field="hostname")
    primary = _touch_output(tmp_path, schema, "web01", "primary", datetime(2026, 1, 1, 10, 0, 0))
    _touch_output(tmp_path, schema, "web01", "backup", datetime(2026, 1, 1, 10, 0, 0))

    matches = find_recent_outputs(tmp_path, "widget", "web01", doc_key="primary")
    assert matches == [primary]


def test_find_recent_outputs_filters_by_identity(tmp_path: Path):
    schema = _schema(identity_field="hostname")
    web01 = _touch_output(tmp_path, schema, "web01", "primary", datetime(2026, 1, 1, 10, 0, 0))
    _touch_output(tmp_path, schema, "web02", "primary", datetime(2026, 1, 1, 10, 0, 0))

    matches = find_recent_outputs(tmp_path, "widget", "web01")
    assert matches == [web01]


def test_find_recent_outputs_searches_nested_batch_folders(tmp_path: Path):
    schema = _schema(identity_field="hostname")
    nested_dir = tmp_path / "batch_20260101100000"
    nested_dir.mkdir()
    match = _touch_output(nested_dir, schema, "web01", "primary", datetime(2026, 1, 1, 10, 0, 0))

    matches = find_recent_outputs(tmp_path, "widget", "web01")
    assert matches == [match]
