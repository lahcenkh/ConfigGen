from pathlib import Path

import pytest
import yaml

from configgen.core.schema import (
    find_schema_files,
    load_schema,
    project_dirs_for,
    schema_from_dict,
)

SINGLE_TEMPLATE = {
    "name": "Widget",
    "id": "widget",
    "fields": [{"key": "name", "label": "Name", "type": "string"}],
    "template": "widget.j2",
}

MULTI_DOCUMENT = {
    "name": "Widget Pair",
    "id": "widget_pair",
    "fields": [{"key": "name", "label": "Name", "type": "string"}],
    "documents": [
        {"key": "primary", "label": "Primary", "template": "primary.j2"},
        {"key": "backup", "label": "Backup", "template": "backup.j2"},
    ],
}


def test_schema_from_dict_single_template():
    schema = schema_from_dict(SINGLE_TEMPLATE)
    assert schema.id == "widget"
    assert schema.fields[0].key == "name"
    docs = schema.document_list()
    assert len(docs) == 1
    assert docs[0].template == "widget.j2"


def test_schema_from_dict_multi_document():
    schema = schema_from_dict(MULTI_DOCUMENT)
    docs = schema.document_list()
    assert [d.key for d in docs] == ["primary", "backup"]


def test_schema_defaults():
    schema = schema_from_dict(SINGLE_TEMPLATE)
    assert schema.version == 1
    assert schema.status == "draft"
    assert schema.tags == []
    assert schema.supports_variants is False
    assert schema.comment_prefix == "!"


def test_load_schema_reads_yaml(tmp_path: Path):
    schema_path = tmp_path / "widget.yaml"
    schema_path.write_text(yaml.dump(SINGLE_TEMPLATE), encoding="utf-8")
    schema = load_schema(schema_path)
    assert schema.id == "widget"
    assert schema.source_path == schema_path


def test_project_dirs_for_sibling_layout(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    schema_path = schemas_dir / "widget.yaml"
    schema_path.write_text("id: widget", encoding="utf-8")
    templates_dir, hooks_dir = project_dirs_for(schema_path)
    assert templates_dir == tmp_path / "templates"
    assert hooks_dir == tmp_path / "hooks"


def test_find_schema_files_lists_yaml_and_yml(tmp_path: Path):
    (tmp_path / "a.yaml").write_text("id: a", encoding="utf-8")
    (tmp_path / "b.yml").write_text("id: b", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    files = find_schema_files(tmp_path)
    assert {p.name for p in files} == {"a.yaml", "b.yml"}


def test_find_schema_files_missing_dir_returns_empty(tmp_path: Path):
    assert find_schema_files(tmp_path / "does-not-exist") == []


def test_field_key_error_when_missing_required_top_level():
    with pytest.raises(KeyError):
        schema_from_dict({"fields": []})
