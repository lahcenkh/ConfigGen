import zipfile
from pathlib import Path

from configgen import cli
from configgen.core.auth import AuthStore

WIDGET_SCHEMA = """\
name: Widget
id: widget
version: 1
status: published
identity_field: name
template: widget.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""


def _bootstrap(tmp_path: Path) -> Path:
    db_path = tmp_path / "users.db"
    AuthStore(db_path)
    return db_path


def _make_project(tmp_path: Path, name: str = "project") -> Path:
    project = tmp_path / name
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "widget.yaml").write_text(WIDGET_SCHEMA, encoding="utf-8")
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    return project


# -- export ---------------------------------------------------------


def test_export_requires_admin_or_template_engineer(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    project = _make_project(tmp_path)

    code = cli.main(
        [
            "export",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--output",
            str(tmp_path / "out.zip"),
            "--as-username",
            "carol",
            "--as-password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "ERROR" in err
    assert not (tmp_path / "out.zip").exists()


def test_export_allowed_for_template_engineer(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("tina", "hunter22pw", "template_engineer")
    project = _make_project(tmp_path)
    output = tmp_path / "widget.configpack.zip"

    code = cli.main(
        [
            "export",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--output",
            str(output),
            "--author",
            "tina",
            "--as-username",
            "tina",
            "--as-password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "exported 'widget'" in out
    assert output.is_file()
    with zipfile.ZipFile(output) as zf:
        assert "schema.yaml" in zf.namelist()


def test_export_unknown_schema_id_fails_cleanly(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    project = _make_project(tmp_path)

    code = cli.main(
        [
            "export",
            "nonexistent",
            "--dir",
            str(project / "schemas"),
            "--as-username",
            "admin",
            "--as-password",
            "admin",
            "--users-db",
            str(db_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "ERROR" in err


# -- import ---------------------------------------------------------


def _export_pack(tmp_path: Path, db_path: Path) -> Path:
    project = _make_project(tmp_path, "source")
    output = tmp_path / "widget.configpack.zip"
    cli.main(
        [
            "export",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--output",
            str(output),
            "--as-username",
            "admin",
            "--as-password",
            "admin",
            "--users-db",
            str(db_path),
        ]
    )
    return output


def test_import_requires_admin(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("tina", "hunter22pw", "template_engineer")
    pack = _export_pack(tmp_path, db_path)
    target = tmp_path / "target"

    code = cli.main(
        [
            "import",
            str(pack),
            "--resources",
            str(target),
            "--as-username",
            "tina",
            "--as-password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "ERROR" in err
    assert not (target / "schemas" / "widget.yaml").exists()


def test_import_writes_files_and_reports_success(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    pack = _export_pack(tmp_path, db_path)
    target = tmp_path / "target"

    code = cli.main(
        [
            "import",
            str(pack),
            "--resources",
            str(target),
            "--as-username",
            "admin",
            "--as-password",
            "admin",
            "--users-db",
            str(db_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "imported 'widget'" in out
    assert (target / "schemas" / "widget.yaml").is_file()
    assert (target / "templates" / "widget.j2").is_file()


def test_import_conflict_without_flag_fails(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    pack = _export_pack(tmp_path, db_path)
    target = tmp_path / "target"
    admin_flags = [
        "--as-username",
        "admin",
        "--as-password",
        "admin",
        "--users-db",
        str(db_path),
    ]
    cli.main(["import", str(pack), "--resources", str(target), *admin_flags])
    capsys.readouterr()

    code = cli.main(["import", str(pack), "--resources", str(target), *admin_flags])
    err = capsys.readouterr().err
    assert code == 1
    assert "already exists" in err


def test_import_conflict_with_overwrite_succeeds(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    pack = _export_pack(tmp_path, db_path)
    target = tmp_path / "target"
    admin_flags = [
        "--as-username",
        "admin",
        "--as-password",
        "admin",
        "--users-db",
        str(db_path),
    ]
    cli.main(["import", str(pack), "--resources", str(target), *admin_flags])
    capsys.readouterr()

    code = cli.main(["import", str(pack), "--resources", str(target), "--overwrite", *admin_flags])
    out = capsys.readouterr().out
    assert code == 0
    assert "overwrote 'widget'" in out


def test_import_conflict_with_rename_writes_new_id(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    pack = _export_pack(tmp_path, db_path)
    target = tmp_path / "target"
    admin_flags = [
        "--as-username",
        "admin",
        "--as-password",
        "admin",
        "--users-db",
        str(db_path),
    ]
    cli.main(["import", str(pack), "--resources", str(target), *admin_flags])
    capsys.readouterr()

    code = cli.main(
        ["import", str(pack), "--resources", str(target), "--rename", "widget_v2", *admin_flags]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "imported 'widget_v2'" in out
    assert (target / "schemas" / "widget_v2.yaml").is_file()
    assert (target / "schemas" / "widget.yaml").is_file()  # original untouched
