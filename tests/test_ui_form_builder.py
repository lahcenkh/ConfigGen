from pathlib import Path

from configgen.core.schema import Field, Schema, load_schema
from configgen.ui.form_builder import FormBuilder

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS_DIR = EXAMPLES_ROOT / "schemas"

VALID_SERVER_VALUES = {
    "hostname": "web01-nyc",
    "management_ip": "10.20.30.5",
    "subnet": "10.20.30.0/24",
    "timezone": "America/New_York",
    "admin_username": "svcadmin",
    "ssh_port": "22",
    "enable_firewall": True,
    "notes": "test",
}


def test_form_builds_one_widget_per_field(qtbot):
    schema = load_schema(SCHEMAS_DIR / "server_provisioning.yaml")
    form = FormBuilder(schema)
    qtbot.addWidget(form)
    assert set(form.widgets) == {f.key for f in schema.fields}


def test_form_validate_succeeds_with_good_values(qtbot):
    schema = load_schema(SCHEMAS_DIR / "server_provisioning.yaml")
    form = FormBuilder(schema)
    qtbot.addWidget(form)
    form.set_raw_values(VALID_SERVER_VALUES)
    assert form.validate() is not None


def test_form_validate_fails_and_paints_error_on_bad_value(qtbot):
    schema = load_schema(SCHEMAS_DIR / "server_provisioning.yaml")
    form = FormBuilder(schema)
    qtbot.addWidget(form)
    form.set_raw_values({**VALID_SERVER_VALUES, "hostname": "BAD HOST!"})
    assert form.validate() is None
    assert form.widgets["hostname"]._error_label.text()


def test_form_prefills_field_defaults(qtbot):
    schema = load_schema(SCHEMAS_DIR / "server_provisioning.yaml")
    form = FormBuilder(schema)
    qtbot.addWidget(form)
    assert form.widgets["timezone"].value() == "UTC"  # schema default


def test_form_raw_values_round_trip(qtbot):
    schema = load_schema(SCHEMAS_DIR / "server_provisioning.yaml")
    form = FormBuilder(schema)
    qtbot.addWidget(form)
    form.set_raw_values(VALID_SERVER_VALUES)
    raw = form.raw_values()
    assert raw["hostname"] == "web01-nyc"
    assert raw["enable_firewall"] is True


def test_required_if_toggles_both_ways(qtbot):
    # Regression test for the FieldWidget.set_required() mutation bug: once
    # fixed, toggling the driving field back and forth must correctly
    # toggle the dependent field's effective-required state every time, not
    # just the first time.
    schema = load_schema(SCHEMAS_DIR / "router_base_config.yaml")
    form = FormBuilder(schema)
    qtbot.addWidget(form)

    form.set_raw_values({"enable_ospf": False})
    assert form.widgets["ospf_process_id"].field.required is False

    form.set_raw_values({"enable_ospf": True})
    assert form.widgets["ospf_process_id"]._label.text().endswith("*")

    form.set_raw_values({"enable_ospf": False})
    assert not form.widgets["ospf_process_id"]._label.text().endswith("*")
    assert form.widgets["ospf_process_id"].field.required is False


def test_visible_if_hides_and_shows_field(qtbot):
    # None of the shipped examples use visible_if (only required_if), so
    # build a minimal schema directly to exercise it.
    schema = Schema(
        name="Test",
        id="test",
        template="test.j2",
        fields=[
            Field(key="mode", label="Mode", type="choice", options=["single", "dual"]),
            Field(key="vrrp_ip", label="VRRP IP", type="ip", visible_if={"mode": "dual"}),
        ],
    )
    form = FormBuilder(schema)
    qtbot.addWidget(form)

    form.set_raw_values({"mode": "single"})
    assert form.widgets["vrrp_ip"].isHidden()

    form.set_raw_values({"mode": "dual"})
    assert not form.widgets["vrrp_ip"].isHidden()

    form.set_raw_values({"mode": "single"})
    assert form.widgets["vrrp_ip"].isHidden()


class _FakeOnboardingDatabase:
    """device_onboarding.yaml has two from_db fields; both must resolve."""

    _TABLES = {"regions": ["us-east", "us-west"], "device_names": ["edge-01", "edge-02"]}

    def all(self, query_name):
        return self._TABLES[query_name]


def test_from_db_choice_field_gets_options_from_database(qtbot):
    schema = load_schema(SCHEMAS_DIR / "device_onboarding.yaml")
    form = FormBuilder(schema, database=_FakeOnboardingDatabase())
    qtbot.addWidget(form)
    combo = form.widgets["region"].input
    assert [combo.itemText(i) for i in range(combo.count())] == ["us-east", "us-west"]


def test_from_db_lookup_field_gets_completions_from_database(qtbot):
    schema = load_schema(SCHEMAS_DIR / "device_onboarding.yaml")
    form = FormBuilder(schema, database=_FakeOnboardingDatabase())
    qtbot.addWidget(form)
    assert form.widgets["device_name"].input.completer() is not None


def test_from_db_failure_does_not_crash_form_construction(qtbot):
    class _BrokenDatabase:
        def all(self, query_name):
            from configgen.core.db import DatabaseError

            raise DatabaseError("query failed")

    schema = load_schema(SCHEMAS_DIR / "device_onboarding.yaml")
    form = FormBuilder(schema, database=_BrokenDatabase())
    qtbot.addWidget(form)
    assert "region" in form.widgets  # form still built despite the DB error
