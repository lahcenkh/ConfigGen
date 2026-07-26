import csv
import sqlite3
from pathlib import Path

import openpyxl
import pytest
import yaml

from configgen import cli
from configgen.core.auth import AuthStore

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS_DIR = EXAMPLES_ROOT / "schemas"
BULK_CSV = EXAMPLES_ROOT / "sample_bulk.csv"


def _make_widget_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "widget.yaml").write_text(
        "name: Widget\nid: widget\nversion: 1\nstatus: published\n"
        "identity_field: name\ntemplate: widget.j2\n"
        "fields:\n  - key: name\n    label: Name\n    type: string\n    required: true\n",
        encoding="utf-8",
    )
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    return project


def test_bulk_csv_example_partial_success(tmp_path: Path, capsys):
    output_dir = tmp_path / "out"
    code = cli.main(
        [
            "bulk",
            "server_provisioning",
            "--dir",
            str(SCHEMAS_DIR),
            "--input",
            str(BULK_CSV),
            "--output",
            str(output_dir),
            "--username",
            "demo",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "3 valid, 1 errors" in out
    assert "row 5" in out

    batch_dirs = list((output_dir / "demo" / "ungrouped").glob("batch_*"))
    assert len(batch_dirs) == 1
    txt_files = list(batch_dirs[0].glob("*.txt"))
    assert len(txt_files) == 3
    assert (batch_dirs[0] / "batch_manifest.json").is_file()


def test_bulk_xlsx_input(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    xlsx_path = tmp_path / "rows.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["name"])
    sheet.append(["web01"])
    sheet.append(["web02"])
    workbook.save(xlsx_path)

    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(xlsx_path),
            "--output",
            str(tmp_path / "out"),
            "--username",
            "demo",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "2 valid, 0 errors" in out


def test_bulk_errors_out_writes_csv(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    csv_path = tmp_path / "rows.csv"
    # A quoted empty string is a real row with a blank value (required field
    # missing) - a genuinely blank *line* is skipped entirely by csv.reader,
    # so it wouldn't exercise the error path at all.
    csv_path.write_text('name\nweb01\n""\n', encoding="utf-8")
    errors_out = tmp_path / "errors.csv"

    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(csv_path),
            "--output",
            str(tmp_path / "out"),
            "--errors-out",
            str(errors_out),
        ]
    )
    assert code == 0
    assert errors_out.is_file()
    rows = list(csv.reader(errors_out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["row_number", "errors"]
    assert len(rows) == 2


def test_bulk_query_mode(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    (project / "data").mkdir()
    db_path = project / "data" / "sample.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE devices (name TEXT)")
    conn.executemany("INSERT INTO devices VALUES (?)", [("web01",), ("web02",)])
    conn.commit()
    conn.close()
    (project / "data" / "queries.yaml").write_text(
        yaml.dump(
            {
                "database": "sample.db",
                "queries": {"all_devices": {"sql": "SELECT name FROM devices", "returns": "rows"}},
            }
        ),
        encoding="utf-8",
    )

    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--query",
            "all_devices",
            "--output",
            str(tmp_path / "out"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "2 valid, 0 errors" in out


def test_bulk_query_with_wrong_returns_type_reports_clean_error(tmp_path: Path, capsys):
    code = cli.main(
        [
            "bulk",
            "device_onboarding",
            "--dir",
            str(SCHEMAS_DIR),
            "--query",
            "device_names",  # returns: scalar_list, not rows
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "returns: rows" in err
    assert "Traceback" not in err


def test_bulk_missing_input_file_reports_clean_error(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(tmp_path / "does-not-exist.csv"),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err


def test_bulk_empty_csv_reports_clean_error(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("name\n", encoding="utf-8")

    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(csv_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "no rows found" in err


def test_bulk_input_and_query_are_mutually_exclusive(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "bulk",
                "widget",
                "--dir",
                str(project / "schemas"),
                "--input",
                "a.csv",
                "--query",
                "some_query",
                "--output",
                str(tmp_path / "out"),
            ]
        )
    assert excinfo.value.code == 2  # argparse usage error


# -- auth: role enforcement + generation log --------------------------------


def test_bulk_denied_for_wrong_group(tmp_path: Path, capsys):
    db_path = tmp_path / "users.db"
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    store.create_group("Beta Industries")

    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "widget.yaml").write_text(
        "name: Widget\nid: widget\nversion: 1\nstatus: published\n"
        'group: "Beta Industries"\ntemplate: widget.j2\n'
        "fields:\n  - key: name\n    label: Name\n    type: string\n    required: true\n",
        encoding="utf-8",
    )
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("name\nweb01\n", encoding="utf-8")

    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(csv_path),
            "--output",
            str(tmp_path / "out"),
            "--username",
            "carol",
            "--password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "cannot access" in err


def test_bulk_records_generation_log_with_shared_batch_id(tmp_path: Path, capsys):
    db_path = tmp_path / "users.db"
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")

    project = _make_widget_project(tmp_path)
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("name\nweb01\nweb02\n", encoding="utf-8")

    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(csv_path),
            "--output",
            str(tmp_path / "out"),
            "--username",
            "carol",
            "--password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    assert code == 0

    carol = store.get_user("carol")
    entries = store.list_generation_log(carol)
    assert len(entries) == 2
    batch_ids = {e["bulk_batch_id"] for e in entries}
    assert len(batch_ids) == 1
    assert None not in batch_ids


def test_bulk_without_auth_flags_never_touches_users_db(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    project = _make_widget_project(tmp_path)
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("name\nweb01\n", encoding="utf-8")

    code = cli.main(
        [
            "bulk",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--input",
            str(csv_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    capsys.readouterr()
    assert code == 0
    assert not (tmp_path / "users.db").exists()
