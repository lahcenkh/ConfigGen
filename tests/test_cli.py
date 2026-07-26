import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from configgen import cli

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS_DIR = EXAMPLES_ROOT / "schemas"
TEMPLATES_DIR = EXAMPLES_ROOT / "templates"
DATA_DIR = EXAMPLES_ROOT / "data"
SCHEMA_PATH = SCHEMAS_DIR / "server_provisioning.yaml"
ROUTER_SCHEMA_PATH = SCHEMAS_DIR / "router_base_config.yaml"
DEVICE_SCHEMA_PATH = SCHEMAS_DIR / "device_onboarding.yaml"
PROVISIONING_SCHEMA_PATH = SCHEMAS_DIR / "device_provisioning.yaml"

VALID_DEVICE_VALUES = {
    "region": "us-east",
    "device_name": "edge-01",
    "asset_tag": "AT-10234",
    "notes": "initial onboarding",
}

VALID_PROVISIONING_VALUES = {
    "device_name": "edge-01",
    "subnet": "10.20.30.0/24",
}

VALID_VALUES = {
    "hostname": "web01-nyc",
    "management_ip": "10.20.30.5",
    "subnet": "10.20.30.0/24",
    "timezone": "America/New_York",
    "admin_username": "svcadmin",
    "ssh_port": "22",
    "enable_firewall": True,
    "notes": "initial build",
}

VALID_ROUTER_VALUES = {
    "hostname": "rtr-core-01",
    "mgmt_interface": "GigabitEthernet0/0",
    "mgmt_ip": "10.10.10.1/24",
    "vlan_id": 10,
    "enable_ospf": True,
    "ospf_process_id": 1,
    "ospf_area": 0,
    "ntp_server": "192.0.2.123",
    "snmp_community": "public-ro",
    "notes": "core router example",
}


def test_check_valid_schema(capsys):
    code = cli.main(["check", str(SCHEMA_PATH)])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out
    assert "server_provisioning" in out


def test_check_valid_router_schema(capsys):
    code = cli.main(["check", str(ROUTER_SCHEMA_PATH)])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out
    assert "router_base_config" in out


def test_check_valid_device_onboarding_schema(capsys):
    code = cli.main(["check", str(DEVICE_SCHEMA_PATH)])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out
    assert "device_onboarding" in out


def test_check_valid_device_provisioning_schema(capsys):
    code = cli.main(["check", str(PROVISIONING_SCHEMA_PATH)])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out
    assert "device_provisioning" in out


def test_check_examples_have_no_mismatch_warnings(capsys):
    for schema_path in (
        SCHEMA_PATH,
        ROUTER_SCHEMA_PATH,
        DEVICE_SCHEMA_PATH,
        PROVISIONING_SCHEMA_PATH,
    ):
        code = cli.main(["check", str(schema_path)])
        out = capsys.readouterr().out
        assert code == 0
        assert "WARNING" not in out


def test_check_warns_on_undeclared_template_variable(tmp_path: Path, capsys):
    (tmp_path / "schemas").mkdir()
    (tmp_path / "templates").mkdir()
    schema_path = tmp_path / "schemas" / "widget.yaml"
    schema_path.write_text(
        "name: Widget\nid: widget\ntemplate: widget.j2\n"
        "fields:\n  - key: known\n    label: Known\n    type: string\n",
        encoding="utf-8",
    )
    (tmp_path / "templates" / "widget.j2").write_text("{{ known }} {{ mystery }}", encoding="utf-8")

    code = cli.main(["check", str(schema_path)])
    out = capsys.readouterr().out
    assert code == 0  # advisory, not blocking
    assert "WARNING" in out
    assert "mystery" in out


def test_check_invalid_schema(tmp_path: Path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: bad\nfields: []\n", encoding="utf-8")  # missing name, no template
    code = cli.main(["check", str(bad)])
    err = capsys.readouterr().err
    assert code == 1
    assert "FAILED" in err


def test_list_examples(capsys):
    code = cli.main(["list", "--dir", str(SCHEMAS_DIR)])
    out = capsys.readouterr().out
    assert code == 0
    assert "server_provisioning" in out
    assert "router_base_config" in out
    assert "published" in out


def test_list_empty_directory(tmp_path: Path, capsys):
    code = cli.main(["list", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "No schemas found" in out


def test_generate_writes_output(tmp_path: Path, capsys):
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(VALID_VALUES), encoding="utf-8")
    output_dir = tmp_path / "out"

    code = cli.main(
        [
            "generate",
            "server_provisioning",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
            "--output",
            str(output_dir),
            "--username",
            "tester",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0

    saved_dir = output_dir / "tester" / "ungrouped"
    txt_files = list(saved_dir.glob("*.txt"))
    json_files = list(saved_dir.glob("*.json"))
    assert len(txt_files) == 1
    assert len(json_files) == 1

    text = txt_files[0].read_text(encoding="utf-8")
    assert "hostnamectl set-hostname web01-nyc" in text
    assert "address 10.20.30.5" in text
    assert "netmask 255.255.255.0" in text
    assert "gateway 10.20.30.1" in text
    assert "ufw allow 22/tcp" in text
    assert "Notes: initial build" in text
    assert text.startswith("#")
    assert "tester" in text
    assert "primary:" in out
    assert "profile:" in out


def test_generate_router_example_writes_output(tmp_path: Path, capsys):
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(VALID_ROUTER_VALUES), encoding="utf-8")
    output_dir = tmp_path / "out"

    code = cli.main(
        [
            "generate",
            "router_base_config",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
            "--output",
            str(output_dir),
            "--username",
            "tester",
        ]
    )
    assert code == 0

    saved_dir = output_dir / "tester" / "ungrouped"
    txt_files = list(saved_dir.glob("*.txt"))
    assert len(txt_files) == 1

    text = txt_files[0].read_text(encoding="utf-8")
    assert "hostname rtr-core-01" in text
    assert "interface GigabitEthernet0/0" in text
    assert "ip address 10.10.10.1 255.255.255.0" in text
    assert "router ospf 1" in text
    assert "area 0" in text
    assert "ntp server 192.0.2.123" in text
    assert "snmp-server community public-ro RO" in text
    assert text.startswith("!")


def test_generate_device_onboarding_writes_output(tmp_path: Path, capsys):
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(VALID_DEVICE_VALUES), encoding="utf-8")
    output_dir = tmp_path / "out"

    code = cli.main(
        [
            "generate",
            "device_onboarding",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
            "--output",
            str(output_dir),
            "--username",
            "tester",
        ]
    )
    assert code == 0

    saved_dir = output_dir / "tester" / "ungrouped"
    txt_files = list(saved_dir.glob("*.txt"))
    assert len(txt_files) == 1
    text = txt_files[0].read_text(encoding="utf-8")
    assert "Device:    edge-01" in text
    assert "Region:    us-east" in text
    assert "Asset Tag: AT-10234" in text
    assert text.startswith("#")


def test_generate_device_onboarding_rejects_region_not_in_database(tmp_path: Path, capsys):
    bad_values = {**VALID_DEVICE_VALUES, "region": "mars-colony"}
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(bad_values), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "device_onboarding",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "region" in err
    assert "mars-colony" in err


def test_generate_reports_clean_error_when_database_missing(tmp_path: Path, capsys):
    # Copy the schema+template but not the data/ directory, so the sibling
    # data/queries.yaml this schema needs simply isn't there (§5.3).
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "device_onboarding.yaml").write_text(
        DEVICE_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (project / "templates" / "device_onboarding.j2").write_text(
        (TEMPLATES_DIR / "device_onboarding.j2").read_text(encoding="utf-8"), encoding="utf-8"
    )
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(VALID_DEVICE_VALUES), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "device_onboarding",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "queries.yaml" in err
    assert "Traceback" not in err


def test_generate_device_provisioning_writes_output(tmp_path: Path, capsys):
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(VALID_PROVISIONING_VALUES), encoding="utf-8")
    output_dir = tmp_path / "out"

    code = cli.main(
        [
            "generate",
            "device_provisioning",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
            "--output",
            str(output_dir),
            "--username",
            "tester",
        ]
    )
    assert code == 0

    saved_dir = output_dir / "tester" / "ungrouped"
    txt_files = list(saved_dir.glob("*.txt"))
    assert len(txt_files) == 1
    text = txt_files[0].read_text(encoding="utf-8")
    assert "Name:          edge-01" in text
    assert "Vendor:        Acme Networks" in text
    assert "Management IP: 10.20.30.1" in text
    assert text.startswith("#")


def test_generate_device_provisioning_rejects_unknown_device(tmp_path: Path, capsys):
    bad_values = {**VALID_PROVISIONING_VALUES, "device_name": "ghost-device"}
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(bad_values), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "device_provisioning",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "device_name" in err
    assert "ghost-device" in err


def test_generate_prepare_hook_reports_clean_error_when_database_missing(tmp_path: Path, capsys):
    # A prepare hook that calls services.db.query(...) should fail cleanly,
    # not with an AttributeError, when there's no queries.yaml at all.
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "prepare").mkdir()
    (project / "schemas" / "device_provisioning.yaml").write_text(
        PROVISIONING_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (project / "templates" / "device_provisioning.j2").write_text(
        (TEMPLATES_DIR / "device_provisioning.j2").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (project / "prepare" / "device_provisioning.py").write_text(
        (EXAMPLES_ROOT / "prepare" / "device_provisioning.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(VALID_PROVISIONING_VALUES), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "device_provisioning",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "no database configured" in err
    assert "Traceback" not in err


def test_db_check_all_queries_ok(capsys):
    code = cli.main(["db", "check", "--queries", str(DATA_DIR / "queries.yaml")])
    out = capsys.readouterr().out
    assert code == 0
    assert "regions: OK" in out
    assert "device: OK" in out


def test_db_check_missing_queries_file(tmp_path: Path, capsys):
    code = cli.main(["db", "check", "--queries", str(tmp_path / "no-such-queries.yaml")])
    err = capsys.readouterr().err
    assert code == 1
    assert "queries.yaml" in err


def test_db_check_reports_broken_query(tmp_path: Path, capsys):
    (tmp_path / "sample.db").touch()
    conn = sqlite3.connect(tmp_path / "sample.db")
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    conn.close()

    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(
        yaml.dump(
            {
                "database": "sample.db",
                "queries": {"broken": {"sql": "SELECT * FROM no_such_table", "returns": "rows"}},
            }
        ),
        encoding="utf-8",
    )
    code = cli.main(["db", "check", "--queries", str(queries_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "broken: FAIL" in out


def test_db_command_without_subcommand_prints_help(capsys):
    code = cli.main(["db"])
    out = capsys.readouterr().out
    assert code == 0
    assert "usage" in out.lower()


def test_generate_reports_validation_errors(tmp_path: Path, capsys):
    bad_values = {**VALID_VALUES, "management_ip": "not-an-ip"}
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps(bad_values), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "server_provisioning",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "management_ip" in err


def test_generate_unknown_schema_id(tmp_path: Path, capsys):
    values_path = tmp_path / "values.json"
    values_path.write_text("{}", encoding="utf-8")
    code = cli.main(
        [
            "generate",
            "does_not_exist",
            "--dir",
            str(SCHEMAS_DIR),
            "--values",
            str(values_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "does_not_exist" in err


def test_no_command_prints_help(capsys):
    code = cli.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "usage" in out.lower()


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "ConfigGen" in out


def test_extract_lists_variables(capsys):
    template_path = TEMPLATES_DIR / "server_provisioning.j2"
    code = cli.main(["extract", str(template_path)])
    out = capsys.readouterr().out
    assert code == 0
    lines = out.split()
    assert "hostname" in lines
    assert "management_ip" in lines
    assert "subnet" in lines


def test_extract_scaffold_produces_yaml(capsys):
    template_path = TEMPLATES_DIR / "server_provisioning.j2"
    code = cli.main(["extract", str(template_path), "--scaffold"])
    out = capsys.readouterr().out
    assert code == 0
    scaffold = yaml.safe_load(out)
    assert scaffold["id"] == "server_provisioning"
    field_keys = {f["key"] for f in scaffold["fields"]}
    assert "management_ip" in field_keys


def test_extract_check_reports_clean_match(capsys):
    template_path = TEMPLATES_DIR / "server_provisioning.j2"
    code = cli.main(["extract", str(template_path), "--check", str(SCHEMA_PATH)])
    out = capsys.readouterr().out
    assert code == 0
    assert "MISSING" not in out
    assert "OK" in out


def test_extract_check_reports_missing_variable(tmp_path: Path, capsys):
    schema_path = tmp_path / "widget.yaml"
    schema_path.write_text(
        "name: Widget\nid: widget\ntemplate: widget.j2\n"
        "fields:\n  - key: known\n    label: Known\n    type: string\n",
        encoding="utf-8",
    )
    template_path = tmp_path / "widget.j2"
    template_path.write_text("{{ known }} {{ mystery }}", encoding="utf-8")

    code = cli.main(["extract", str(template_path), "--check", str(schema_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "mystery: MISSING" in out
    assert "known: OK" in out
