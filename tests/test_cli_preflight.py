import json
from pathlib import Path

from configgen import cli

BROKEN_SCHEMA = """\
name: Broken Router
id: broken_router
version: 1
status: published
preflight: ios
template: broken_router.j2
fields:
  - key: iface_name
    label: Interface name
    type: string
    required: true
  - key: vlan_num
    label: VLAN number
    type: string
    required: true
"""

BROKEN_TEMPLATE = "interface {{ iface_name }}\n no shutdown\nvlan {{ vlan_num }}\n"

CLEAN_TEMPLATE = "interface {{ iface_name }}\n no shutdown\nvlan {{ vlan_num }}\nend\n"


def _make_project(tmp_path: Path, template_text: str) -> Path:
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "broken_router.yaml").write_text(BROKEN_SCHEMA, encoding="utf-8")
    (project / "templates" / "broken_router.j2").write_text(template_text, encoding="utf-8")
    return project


def test_generate_reports_preflight_warnings_but_still_succeeds(tmp_path: Path, capsys):
    project = _make_project(tmp_path, BROKEN_TEMPLATE)
    values_path = tmp_path / "values.json"
    values_path.write_text(
        json.dumps({"iface_name": "bad!name", "vlan_num": "9999"}), encoding="utf-8"
    )

    code = cli.main(
        [
            "generate",
            "broken_router",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
            "--username",
            "demo",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0  # advisory only, never blocks
    assert "PREFLIGHT WARNING" in out
    assert "no closing 'end'" in out
    assert "bad!name" in out
    assert "VLAN 9999" in out
    # the file was still saved despite the warnings
    saved = list((tmp_path / "out" / "demo" / "ungrouped").glob("*.txt"))
    assert len(saved) == 1


def test_generate_clean_config_has_no_preflight_warnings(tmp_path: Path, capsys):
    project = _make_project(tmp_path, CLEAN_TEMPLATE)
    values_path = tmp_path / "values.json"
    values_path.write_text(
        json.dumps({"iface_name": "GigabitEthernet0/0", "vlan_num": "10"}), encoding="utf-8"
    )

    code = cli.main(
        [
            "generate",
            "broken_router",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "PREFLIGHT WARNING" not in out


def test_generate_uses_project_custom_preflight_check(tmp_path: Path, capsys):
    project = _make_project(tmp_path, CLEAN_TEMPLATE)
    (project / "preflight").mkdir()
    (project / "preflight" / "ios.py").write_text(
        "def check(text):\n    return ['custom rule fired']\n", encoding="utf-8"
    )
    values_path = tmp_path / "values.json"
    values_path.write_text(
        json.dumps({"iface_name": "GigabitEthernet0/0", "vlan_num": "10"}), encoding="utf-8"
    )

    code = cli.main(
        [
            "generate",
            "broken_router",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "custom rule fired" in out


def test_bulk_reports_preflight_warnings_per_row(tmp_path: Path, capsys):
    project = _make_project(tmp_path, BROKEN_TEMPLATE)
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text(
        "iface_name,vlan_num\nbad!name,9999\nGigabitEthernet0/0,10\n", encoding="utf-8"
    )

    code = cli.main(
        [
            "bulk",
            "broken_router",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(csv_path),
            "--output",
            str(tmp_path / "out"),
            "--username",
            "demo",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "2 valid, 0 errors" in out
    assert "row 2" in out
    assert "bad!name" in out
    assert "VLAN 9999" in out

    manifest_glob = (tmp_path / "out" / "demo" / "ungrouped").glob("batch_*/batch_manifest.json")
    manifest = json.loads(next(manifest_glob).read_text(encoding="utf-8"))
    row2 = next(r for r in manifest["rows"] if r["row_number"] == 2)
    # both bad values on row 2
    assert len(row2["preflight_warnings"]["primary"]) == 3
    row3 = next(r for r in manifest["rows"] if r["row_number"] == 3)
    # BROKEN_TEMPLATE never emits "end" regardless of input, so row 3 still
    # gets exactly that one warning even with otherwise-valid values.
    assert row3["preflight_warnings"]["primary"] == [
        "found 'interface' block(s) but no closing 'end' statement"
    ]
