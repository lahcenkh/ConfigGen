from pathlib import Path

import pytest

from configgen.core.versioning import (
    VersioningError,
    diff_versions,
    list_versions,
    restore_version,
    save_version,
)

SCHEMA_V1 = """\
name: Widget
id: widget
version: 1
status: published
template: widget.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""


def _make_project(tmp_path: Path) -> tuple[Path, Path]:
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    schemas_dir.mkdir()
    templates_dir.mkdir()
    schema_path = schemas_dir / "widget.yaml"
    schema_path.write_text(SCHEMA_V1, encoding="utf-8")
    (templates_dir / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    return schema_path, templates_dir


def test_list_versions_empty_when_none_saved(tmp_path: Path):
    assert list_versions(tmp_path / "history", "widget") == []


def test_save_version_creates_entry_and_snapshot(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"

    entry = save_version(history_root, schema_path, templates_dir, author="bob", note="v1")

    assert entry.version == 1
    assert entry.author == "bob"
    assert entry.note == "v1"

    versions = list_versions(history_root, "widget")
    assert len(versions) == 1
    assert versions[0].version == 1

    snapshot = history_root / "widget" / "v1"
    assert (snapshot / "schema.yaml").read_text(encoding="utf-8") == SCHEMA_V1
    assert (snapshot / "templates" / "widget.j2").read_text(encoding="utf-8") == "hello {{ name }}"


def test_save_version_rejects_duplicate_version(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob")

    with pytest.raises(VersioningError):
        save_version(history_root, schema_path, templates_dir, author="bob")


def test_save_version_multi_document_copies_all_templates(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    schemas_dir.mkdir()
    templates_dir.mkdir()
    schema_path = schemas_dir / "pair.yaml"
    schema_path.write_text(
        "name: Pair\nid: pair\nversion: 1\nstatus: published\n"
        "documents:\n"
        "  - key: primary\n    label: Primary\n    template: primary.j2\n"
        "  - key: backup\n    label: Backup\n    template: backup.j2\n"
        "fields: []\n",
        encoding="utf-8",
    )
    (templates_dir / "primary.j2").write_text("primary body", encoding="utf-8")
    (templates_dir / "backup.j2").write_text("backup body", encoding="utf-8")
    history_root = tmp_path / "history"

    save_version(history_root, schema_path, templates_dir, author="bob")

    snapshot = history_root / "pair" / "v1" / "templates"
    assert (snapshot / "primary.j2").read_text(encoding="utf-8") == "primary body"
    assert (snapshot / "backup.j2").read_text(encoding="utf-8") == "backup body"


def test_versions_sorted_by_number(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob")
    schema_path.write_text(SCHEMA_V1.replace("version: 1", "version: 2"), encoding="utf-8")
    save_version(history_root, schema_path, templates_dir, author="alice")

    versions = list_versions(history_root, "widget")
    assert [v.version for v in versions] == [1, 2]


# -- diff_versions ---------------------------------------------------------


def test_diff_versions_reports_changed_files(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob")

    schema_path.write_text(SCHEMA_V1.replace("version: 1", "version: 2"), encoding="utf-8")
    (templates_dir / "widget.j2").write_text("hello there {{ name }}", encoding="utf-8")
    save_version(history_root, schema_path, templates_dir, author="alice")

    diffs = diff_versions(history_root, "widget", 1, 2)
    assert "schema.yaml" in diffs
    assert "-version: 1" in diffs["schema.yaml"]
    assert "+version: 2" in diffs["schema.yaml"]

    template_key = next(k for k in diffs if k.endswith("widget.j2"))
    assert "-hello {{ name }}" in diffs[template_key]
    assert "+hello there {{ name }}" in diffs[template_key]


def test_diff_versions_no_changes_returns_empty(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob")

    # A version diffed against itself has nothing to report.
    diffs = diff_versions(history_root, "widget", 1, 1)
    assert diffs == {}


def test_diff_versions_unknown_version_raises(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob")

    with pytest.raises(VersioningError):
        diff_versions(history_root, "widget", 1, 99)


# -- restore_version ---------------------------------------------------------


def test_restore_version_replaces_live_files_and_creates_new_entry(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob", note="v1")

    schema_path.write_text(SCHEMA_V1.replace("version: 1", "version: 2"), encoding="utf-8")
    (templates_dir / "widget.j2").write_text("hello there {{ name }}", encoding="utf-8")
    save_version(history_root, schema_path, templates_dir, author="alice", note="v2")

    entry = restore_version(history_root, schema_path, templates_dir, version=1, author="carol")

    assert entry.version == 3
    assert entry.author == "carol"
    assert entry.note == "Restored from version 1"

    assert (templates_dir / "widget.j2").read_text(encoding="utf-8") == "hello {{ name }}"
    assert "version: 3" in schema_path.read_text(encoding="utf-8")

    versions = list_versions(history_root, "widget")
    assert [v.version for v in versions] == [1, 2, 3]
    # v1 itself is untouched
    assert (history_root / "widget" / "v1" / "schema.yaml").read_text(encoding="utf-8") == SCHEMA_V1


def test_restore_version_custom_note(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob")
    schema_path.write_text(SCHEMA_V1.replace("version: 1", "version: 2"), encoding="utf-8")
    save_version(history_root, schema_path, templates_dir, author="alice")

    entry = restore_version(
        history_root, schema_path, templates_dir, version=1, author="carol", note="rollback"
    )
    assert entry.note == "rollback"


def test_restore_version_no_history_raises(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    with pytest.raises(VersioningError):
        restore_version(history_root, schema_path, templates_dir, version=1, author="carol")


def test_restore_unknown_version_raises(tmp_path: Path):
    schema_path, templates_dir = _make_project(tmp_path)
    history_root = tmp_path / "history"
    save_version(history_root, schema_path, templates_dir, author="bob")

    with pytest.raises(VersioningError):
        restore_version(history_root, schema_path, templates_dir, version=99, author="carol")
