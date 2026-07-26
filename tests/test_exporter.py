import json
from datetime import datetime
from pathlib import Path

import pytest

from configgen.core.exporter import (
    build_filename,
    build_profile_filename,
    load_profile,
    profile_filename_for,
    resolve_profile_path,
    save_documents,
)
from configgen.core.schema import Schema

TS = datetime(2026, 1, 15, 14, 30, 0)


def _schema(**overrides) -> Schema:
    defaults = dict(name="Widget", id="widget", fields=[], template="widget.j2", group="Acme")
    defaults.update(overrides)
    return Schema(**defaults)


def test_build_filename_basic_shape():
    schema = _schema(identity_field="hostname")
    name = build_filename(schema, "primary", {"hostname": "web01"}, timestamp=TS)
    assert name == "Acme_widget_web01_primary_20260115143000.txt"


def test_build_filename_without_group_or_identity():
    schema = _schema(group=None)
    name = build_filename(schema, "primary", {}, timestamp=TS)
    assert name == "ungrouped_widget_output_primary_20260115143000.txt"


def test_build_filename_slugs_unsafe_identity_characters():
    schema = _schema(identity_field="hostname")
    name = build_filename(schema, "primary", {"hostname": "Web 01 / NYC!"}, timestamp=TS)
    assert name == "Acme_widget_Web-01-NYC_primary_20260115143000.txt"


def test_variant_only_included_when_supported():
    schema = _schema(supports_variants=True)
    name = build_filename(schema, "primary", {}, variant="dual", timestamp=TS)
    assert "_dual_" in name

    unsupported = _schema(supports_variants=False)
    name2 = build_filename(unsupported, "primary", {}, variant="dual", timestamp=TS)
    assert "dual" not in name2


def test_profile_filename_has_no_doc_key():
    schema = _schema(identity_field="hostname")
    profile_name = build_profile_filename(schema, {"hostname": "web01"}, timestamp=TS)
    assert profile_name == "Acme_widget_web01_20260115143000.json"


def test_profile_filename_for_strips_doc_token():
    schema = _schema(identity_field="hostname")
    doc_name = build_filename(schema, "primary", {"hostname": "web01"}, timestamp=TS)
    expected_profile = build_profile_filename(schema, {"hostname": "web01"}, timestamp=TS)
    assert profile_filename_for(doc_name, "primary") == expected_profile


def test_profile_filename_for_survives_doc_key_as_substring_of_schema_id():
    # Regression test: schema ids are conventionally snake_case, so a doc
    # key can appear as a *substring* of the id (here "primary" is embedded
    # in "primary_config"). A naive "filter every token equal to doc_key"
    # implementation strips both occurrences and produces the wrong name;
    # profile_filename_for must strip only the real (rightmost) doc-key
    # segment.
    schema = _schema(id="primary_config", identity_field="hostname")
    doc_name = build_filename(schema, "primary", {"hostname": "web01"}, timestamp=TS)
    expected_profile = build_profile_filename(schema, {"hostname": "web01"}, timestamp=TS)
    assert profile_filename_for(doc_name, "primary") == expected_profile
    assert expected_profile == "Acme_primary_config_web01_20260115143000.json"


def test_profile_filename_for_multi_doc_both_keys_resolve_to_same_profile():
    schema = _schema(identity_field="hostname")
    context = {"hostname": "web01"}
    primary_name = build_filename(schema, "primary", context, timestamp=TS)
    backup_name = build_filename(schema, "backup", context, timestamp=TS)
    expected_profile = build_profile_filename(schema, context, timestamp=TS)
    assert profile_filename_for(primary_name, "primary") == expected_profile
    assert profile_filename_for(backup_name, "backup") == expected_profile


def test_profile_filename_for_unknown_doc_key_raises():
    with pytest.raises(ValueError):
        profile_filename_for("Acme_widget_web01_primary_20260115143000.txt", "does-not-exist")


def test_resolve_profile_path(tmp_path: Path):
    doc_path = tmp_path / "Acme_widget_web01_primary_20260115143000.txt"
    doc_path.write_text("body", encoding="utf-8")
    resolved = resolve_profile_path(doc_path, "primary")
    assert resolved == tmp_path / "Acme_widget_web01_20260115143000.json"


def test_load_profile_reads_json(tmp_path: Path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"schema_id": "widget"}), encoding="utf-8")
    assert load_profile(profile_path) == {"schema_id": "widget"}


def test_save_documents_writes_files_and_profile(tmp_path: Path):
    schema = _schema(identity_field="hostname")
    result = save_documents(
        {"primary": "! rendered text"},
        schema,
        raw_values={"hostname": "web01"},
        output_root=tmp_path,
        username="alice",
        timestamp=TS,
    )
    assert result.output_dir == tmp_path / "alice" / "Acme"
    assert result.document_paths["primary"].read_text(encoding="utf-8") == "! rendered text"
    assert result.profile_path.is_file()

    profile = json.loads(result.profile_path.read_text(encoding="utf-8"))
    assert profile["schema_id"] == "widget"
    assert profile["username"] == "alice"
    assert profile["documents"]["primary"] == result.document_paths["primary"].name


def test_multi_document_round_trip(tmp_path: Path):
    schema = _schema(identity_field="hostname")
    raw_values = {"hostname": "web01"}
    result = save_documents(
        {"primary": "! primary body", "backup": "! backup body"},
        schema,
        raw_values=raw_values,
        output_root=tmp_path,
        username="alice",
        timestamp=TS,
    )

    assert set(result.document_paths) == {"primary", "backup"}
    assert result.document_paths["primary"].read_text(encoding="utf-8") == "! primary body"
    assert result.document_paths["backup"].read_text(encoding="utf-8") == "! backup body"

    # Reopen: starting from either saved document alone, resolve back to the
    # one shared profile and recover the original inputs.
    for doc_key, doc_path in result.document_paths.items():
        resolved = resolve_profile_path(doc_path, doc_key)
        assert resolved == result.profile_path
        profile = load_profile(resolved)
        assert profile["inputs"] == raw_values
        assert profile["documents"] == {
            "primary": result.document_paths["primary"].name,
            "backup": result.document_paths["backup"].name,
        }
