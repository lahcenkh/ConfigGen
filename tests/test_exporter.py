import json
from datetime import datetime
from pathlib import Path

from configgen.core.exporter import (
    build_filename,
    build_profile_filename,
    profile_filename_for,
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
