import json
from pathlib import Path

import pytest

from configgen import cli

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS_DIR = EXAMPLES_ROOT / "schemas"
SCHEMA_PATH = SCHEMAS_DIR / "server_provisioning.yaml"
ROUTER_SCHEMA_PATH = SCHEMAS_DIR / "router_base_config.yaml"

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
