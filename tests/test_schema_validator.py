from pathlib import Path

import pytest

from configgen.core.schema_validator import SchemaValidationError, validate_schema

BASE = {
    "name": "Widget",
    "id": "widget",
    "template": "widget.j2",
    "fields": [{"key": "name", "label": "Name", "type": "string"}],
}


def _issues(data: dict, **kwargs) -> list[str]:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_schema(data, **kwargs)
    return [issue.path for issue in excinfo.value.issues]


def test_valid_schema_passes():
    validate_schema(BASE)  # no exception


def test_missing_required_top_level_key():
    data = {k: v for k, v in BASE.items() if k != "name"}
    assert any("name" in path for path in _issues(data))


def test_unrecognized_field_type():
    data = {**BASE, "fields": [{"key": "x", "label": "X", "type": "bogus"}]}
    assert _issues(data)


def test_duplicate_field_keys():
    data = {
        **BASE,
        "fields": [
            {"key": "x", "label": "X", "type": "string"},
            {"key": "x", "label": "X again", "type": "string"},
        ],
    }
    paths = _issues(data)
    assert any("duplicate" in str(p) or "fields[x]" in p for p in paths)


def test_invalid_regex_pattern():
    data = {
        **BASE,
        "fields": [{"key": "x", "label": "X", "type": "string", "pattern": "([unclosed"}],
    }
    assert _issues(data)


def test_default_violates_own_pattern():
    data = {
        **BASE,
        "fields": [
            {
                "key": "x",
                "label": "X",
                "type": "string",
                "pattern": r"^\d+$",
                "default": "not-a-number",
            }
        ],
    }
    assert _issues(data)


def test_default_matching_pattern_is_fine():
    data = {
        **BASE,
        "fields": [
            {"key": "x", "label": "X", "type": "string", "pattern": r"^\d+$", "default": "42"}
        ],
    }
    validate_schema(data)


def test_conditional_references_unknown_field():
    data = {
        **BASE,
        "fields": [
            {"key": "x", "label": "X", "type": "string", "visible_if": {"ghost": "yes"}},
        ],
    }
    assert _issues(data)


def test_port_field_rejects_default():
    data = {
        **BASE,
        "fields": [{"key": "p", "label": "Port", "type": "port", "default": "22"}],
    }
    assert _issues(data)


def test_lookup_field_rejects_default():
    data = {
        **BASE,
        "fields": [{"key": "d", "label": "Device", "type": "lookup", "default": "x"}],
    }
    assert _issues(data)


def test_template_missing_on_disk(tmp_path: Path):
    with pytest.raises(SchemaValidationError):
        validate_schema(BASE, templates_dir=tmp_path)


def test_template_present_on_disk(tmp_path: Path):
    (tmp_path / "widget.j2").write_text("hello", encoding="utf-8")
    validate_schema(BASE, templates_dir=tmp_path)


def test_prepare_hook_missing_on_disk(tmp_path: Path):
    data = {**BASE, "prepare": "widget"}
    with pytest.raises(SchemaValidationError):
        validate_schema(data, prepare_dir=tmp_path)


def test_prepare_hook_present_on_disk(tmp_path: Path):
    (tmp_path / "widget.py").write_text("", encoding="utf-8")
    data = {**BASE, "prepare": "widget"}
    validate_schema(data, prepare_dir=tmp_path)


def test_from_db_unknown_query():
    data = {
        **BASE,
        "fields": [
            {
                "key": "region",
                "label": "Region",
                "type": "choice",
                "from_db": {"query": "regions"},
            }
        ],
    }
    assert _issues(data, known_queries={"other_query"})


def test_from_db_known_query_passes():
    data = {
        **BASE,
        "fields": [
            {
                "key": "region",
                "label": "Region",
                "type": "choice",
                "from_db": {"query": "regions"},
            }
        ],
    }
    validate_schema(data, known_queries={"regions"})


def test_from_db_skipped_when_queries_not_supplied():
    data = {
        **BASE,
        "fields": [
            {
                "key": "region",
                "label": "Region",
                "type": "choice",
                "from_db": {"query": "regions"},
            }
        ],
    }
    validate_schema(data)  # known_queries=None means "can't check yet" -> no error


def test_both_template_and_documents_rejected():
    data = {
        **BASE,
        "documents": [{"key": "primary", "label": "Primary", "template": "widget.j2"}],
    }
    assert _issues(data)


def test_neither_template_nor_documents_rejected():
    data = {k: v for k, v in BASE.items() if k != "template"}
    assert _issues(data)


def test_invalid_status_rejected():
    data = {**BASE, "status": "not-a-status"}
    assert _issues(data)
