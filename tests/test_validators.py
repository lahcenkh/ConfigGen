import pytest

from configgen.core.schema import Field, Schema
from configgen.core.validators import (
    FieldValidationError,
    _coerce_string,
    coerce_field,
    validate_values,
)
from configgen.core.values import IPValue, NetworkValue


def _schema(*fields: Field) -> Schema:
    return Schema(name="Test", id="test", fields=list(fields), template="test.j2")


class _FakeDatabase:
    """Duck-types the one method validators.py calls on a Database."""

    def __init__(self, tables: dict[str, list[str]]):
        self._tables = tables

    def all(self, query_name):
        return self._tables[query_name]


def test_coerce_string_never_returns_none():
    # Regression test for the carried-over bug: a missing `return value` made
    # every string field render as None.
    field = Field(key="x", label="X", type="string")
    result = _coerce_string(field, "hello")
    assert result is not None
    assert result == "hello"


def test_coerce_string_pattern_mismatch_raises():
    field = Field(key="x", label="X", type="string", pattern=r"^\d+$")
    with pytest.raises(ValueError):
        coerce_field(field, "not-digits")


def test_coerce_int_range():
    field = Field(key="x", label="X", type="int", min=1, max=10)
    assert coerce_field(field, "5") == 5
    with pytest.raises(ValueError):
        coerce_field(field, "0")
    with pytest.raises(ValueError):
        coerce_field(field, "11")


def test_coerce_int_non_numeric_raises():
    field = Field(key="x", label="X", type="int")
    with pytest.raises(ValueError):
        coerce_field(field, "abc")


@pytest.mark.parametrize(
    "raw,expected", [("true", True), ("yes", True), ("0", False), ("no", False)]
)
def test_coerce_bool(raw, expected):
    field = Field(key="x", label="X", type="bool")
    assert coerce_field(field, raw) is expected


def test_coerce_bool_invalid_raises():
    field = Field(key="x", label="X", type="bool")
    with pytest.raises(ValueError):
        coerce_field(field, "maybe")


def test_coerce_choice_restricts_to_options():
    field = Field(key="x", label="X", type="choice", options=["a", "b"])
    assert coerce_field(field, "a") == "a"
    with pytest.raises(ValueError):
        coerce_field(field, "c")


def test_coerce_choice_from_db_passes_through_without_a_database():
    # §5.3: form-only paths still work even when there's no db configured.
    field = Field(key="region", label="Region", type="choice", from_db={"query": "regions"})
    assert coerce_field(field, "us-east") == "us-east"


def test_coerce_choice_from_db_validates_membership_when_database_given():
    field = Field(key="region", label="Region", type="choice", from_db={"query": "regions"})
    database = _FakeDatabase({"regions": ["us-east", "us-west"]})
    assert coerce_field(field, "us-east", database=database) == "us-east"
    with pytest.raises(ValueError):
        coerce_field(field, "mars-colony", database=database)


def test_coerce_lookup_from_db_accepts_any_text_even_with_database():
    # lookup's from_db is autocomplete only, never a restriction.
    field = Field(
        key="device_name", label="Device", type="lookup", from_db={"query": "device_names"}
    )
    database = _FakeDatabase({"device_names": ["edge-01"]})
    assert coerce_field(field, "brand-new-device", database=database) == "brand-new-device"


def test_validate_values_passes_database_through_to_from_db_fields():
    schema = _schema(
        Field(
            key="region",
            label="Region",
            type="choice",
            from_db={"query": "regions"},
            required=True,
        )
    )
    database = _FakeDatabase({"regions": ["us-east"]})
    result = validate_values(schema, {"region": "us-east"}, database=database)
    assert result["region"] == "us-east"
    with pytest.raises(FieldValidationError):
        validate_values(schema, {"region": "nowhere"}, database=database)


def test_coerce_ip_and_network_types():
    ip_field = Field(key="ip", label="IP", type="ip")
    net_field = Field(key="net", label="Net", type="network")
    assert isinstance(coerce_field(ip_field, "10.0.0.1"), IPValue)
    assert isinstance(coerce_field(net_field, "10.0.0.0/24"), NetworkValue)


def test_validate_values_required_field_missing():
    schema = _schema(Field(key="x", label="X", type="string", required=True))
    with pytest.raises(FieldValidationError) as excinfo:
        validate_values(schema, {})
    assert "x" in excinfo.value.errors


def test_validate_values_error_message_includes_example():
    schema = _schema(Field(key="x", label="X", type="string", pattern=r"^\d+$", example="42"))
    with pytest.raises(FieldValidationError) as excinfo:
        validate_values(schema, {"x": "abc"})
    assert "42" in excinfo.value.errors["x"]


def test_validate_values_optional_field_defaults_to_none():
    schema = _schema(Field(key="x", label="X", type="string", required=False))
    result = validate_values(schema, {})
    assert result["x"] is None


def test_validate_values_visible_if_hides_field():
    schema = _schema(
        Field(key="mode", label="Mode", type="choice", options=["a", "b"], default="a"),
        Field(key="only_b", label="Only B", type="string", visible_if={"mode": "b"}, required=True),
    )
    # mode=a means only_b is not visible, so it's omitted (not required, not an error)
    result = validate_values(schema, {"mode": "a"})
    assert "only_b" not in result


def test_validate_values_visible_if_shows_and_requires_field():
    schema = _schema(
        Field(key="mode", label="Mode", type="choice", options=["a", "b"], default="a"),
        Field(key="only_b", label="Only B", type="string", visible_if={"mode": "b"}, required=True),
    )
    with pytest.raises(FieldValidationError):
        validate_values(schema, {"mode": "b"})


def test_validate_values_required_if():
    schema = _schema(
        Field(key="mode", label="Mode", type="choice", options=["single", "dual"]),
        Field(key="vrrp_ip", label="VRRP IP", type="ip", required_if={"mode": "dual"}),
    )
    # not required when mode=single
    result = validate_values(schema, {"mode": "single"})
    assert result["vrrp_ip"] is None
    # required and missing when mode=dual
    with pytest.raises(FieldValidationError):
        validate_values(schema, {"mode": "dual"})
