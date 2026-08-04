from pathlib import Path

from configgen.core.extractor import (
    VariableStatus,
    classify_variables,
    extract_variables,
    extract_variables_from_file,
    guess_field_type,
    scaffold_schema,
)


def test_extracts_simple_variable():
    assert extract_variables("hello {{ name }}") == ["name"]


def test_extracts_for_loop_iterable_not_loop_target():
    variables = extract_variables("{% for item in items %}{{ item }}{% endfor %}")
    assert variables == ["items"]


def test_extracts_if_condition_variable():
    assert extract_variables("{% if enabled %}yes{% endif %}") == ["enabled"]


def test_dotted_access_extracts_only_top_level_name():
    assert extract_variables("{{ cfg.hostname }}") == ["cfg"]


def test_multiple_variables_deduplicated_and_sorted():
    variables = extract_variables("{{ b }} {{ a }} {{ b }}")
    assert variables == ["a", "b"]


def test_set_local_variable_is_not_external():
    variables = extract_variables("{% set total = 1 + 1 %}{{ total }}")
    assert variables == []


def test_set_anywhere_in_template_excludes_the_name_everywhere():
    # The extractor is advisory, not a full scope analyzer: a name assigned
    # anywhere in the template — even after this use — is treated as locally
    # provided throughout, not as an external input.
    variables = extract_variables("{{ external }}{% set external = 5 %}")
    assert variables == []


def test_jinja_builtin_globals_excluded():
    assert extract_variables("{{ range(3) }}") == []


def test_loop_variable_excluded_inside_for():
    variables = extract_variables("{% for x in items %}{{ loop.index }}{% endfor %}")
    assert variables == ["items"]


def test_macro_parameters_are_not_external():
    variables = extract_variables("{% macro greet(name) %}hi {{ name }}{% endmacro %}")
    assert variables == []


def test_extract_variables_from_file(tmp_path: Path):
    template = tmp_path / "t.j2"
    template.write_text("{{ hostname }} {{ mgmt_ip.ip }}", encoding="utf-8")
    assert extract_variables_from_file(template) == ["hostname", "mgmt_ip"]


def test_classify_variables_field_hook_missing():
    statuses = classify_variables(["a", "b", "c"], field_keys={"a"}, has_hook=False)
    assert statuses == [
        VariableStatus(name="a", source="field"),
        VariableStatus(name="b", source="missing"),
        VariableStatus(name="c", source="missing"),
    ]


def test_classify_variables_missing_becomes_hook_when_hook_declared():
    statuses = classify_variables(["a", "b"], field_keys={"a"}, has_hook=True)
    assert statuses == [
        VariableStatus(name="a", source="field"),
        VariableStatus(name="b", source="hook"),
    ]


def test_guess_field_type_ip():
    assert guess_field_type("management_ip") == "ip"


def test_guess_field_type_int_from_id():
    assert guess_field_type("device_id") == "int"


def test_guess_field_type_int_from_number():
    assert guess_field_type("port_number") == "int"


def test_guess_field_type_defaults_to_string():
    assert guess_field_type("description") == "string"


def test_scaffold_schema_shape(tmp_path: Path):
    template = tmp_path / "widget_base.j2"
    template.write_text("{{ hostname }} {{ device_id }} {{ management_ip }}", encoding="utf-8")

    schema = scaffold_schema(template)

    assert schema["id"] == "widget_base"
    assert schema["name"] == "Widget Base"
    assert schema["status"] == "draft"
    assert schema["template"] == "widget_base.j2"
    fields_by_key = {f["key"]: f for f in schema["fields"]}
    assert fields_by_key["hostname"]["type"] == "string"
    assert fields_by_key["device_id"]["type"] == "int"
    assert fields_by_key["management_ip"]["type"] == "ip"
    assert fields_by_key["hostname"]["label"] == "Hostname"
