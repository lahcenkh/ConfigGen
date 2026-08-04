import json
from pathlib import Path

import pytest

from configgen import cli
from configgen.core.auth import AuthStore, InvalidCredentials

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS_DIR = EXAMPLES_ROOT / "schemas"


def _users_db(tmp_path: Path) -> Path:
    return tmp_path / "users.db"


def _bootstrap(tmp_path: Path) -> Path:
    """Touches the users.db into existence (bootstrap admin/admin) and
    returns its path."""
    db_path = _users_db(tmp_path)
    AuthStore(db_path)
    return db_path


def _make_project(tmp_path: Path, *, group: str | None, status: str) -> Path:
    """A tiny one-field schema+template project, for permission testing."""
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    group_line = f'group: "{group}"\n' if group else ""
    (project / "schemas" / "widget.yaml").write_text(
        "name: Widget\n"
        "id: widget\n"
        "version: 1\n"
        f"status: {status}\n"
        f"{group_line}"
        "template: widget.j2\n"
        "fields:\n"
        "  - key: name\n"
        "    label: Name\n"
        "    type: string\n"
        "    required: true\n",
        encoding="utf-8",
    )
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    return project


# -- user / group / apikey management ---------------------------------------


def test_user_create_requires_admin(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    code = cli.main(
        [
            "user",
            "create",
            "carol",
            "hunter22pw",
            "--role",
            "config_engineer",
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
    assert "created user 'carol'" in out


def test_user_create_denied_for_non_admin(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("bob", "hunter22pw", "template_engineer")

    code = cli.main(
        [
            "user",
            "create",
            "carol",
            "hunter22pw",
            "--role",
            "config_engineer",
            "--as-username",
            "bob",
            "--as-password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "ERROR" in err


def test_user_create_denied_without_credentials(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    code = cli.main(
        [
            "user",
            "create",
            "carol",
            "hunter22pw",
            "--role",
            "config_engineer",
            "--users-db",
            str(db_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "authentication required" in err


def test_user_list_shows_created_users(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    cli.main(
        [
            "user",
            "create",
            "carol",
            "hunter22pw",
            "--role",
            "config_engineer",
            "--as-username",
            "admin",
            "--as-password",
            "admin",
            "--users-db",
            str(db_path),
        ]
    )
    capsys.readouterr()
    code = cli.main(
        [
            "user",
            "list",
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
    assert "admin" in out
    assert "carol" in out


def test_user_passwd_self_service_allowed(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")

    code = cli.main(
        [
            "user",
            "passwd",
            "carol",
            "newpassword1",
            "--as-username",
            "carol",
            "--as-password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    assert code == 0
    assert store.authenticate("carol", "newpassword1").username == "carol"


def test_user_passwd_denied_for_other_users(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    store.create_user("dave", "hunter22pw", "config_engineer")

    code = cli.main(
        [
            "user",
            "passwd",
            "dave",
            "newpassword1",
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


def test_group_create_assign_and_list(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")

    admin_flags = ["--as-username", "admin", "--as-password", "admin", "--users-db", str(db_path)]
    assert cli.main(["group", "create", "Acme Corp", *admin_flags]) == 0
    capsys.readouterr()
    assert cli.main(["group", "assign", "carol", "Acme Corp", *admin_flags]) == 0
    capsys.readouterr()

    code = cli.main(["group", "list", *admin_flags])
    out = capsys.readouterr().out
    assert code == 0
    assert "Acme Corp" in out
    assert store.groups_for_user("carol") == {"Acme Corp"}


def test_apikey_create_and_use_for_generate(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")

    code = cli.main(
        [
            "apikey",
            "create",
            "carol",
            "--label",
            "CI",
            "--as-username",
            "admin",
            "--as-password",
            "admin",
            "--users-db",
            str(db_path),
        ]
    )
    raw_key = capsys.readouterr().out.strip()
    assert code == 0
    assert raw_key

    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")
    output_dir = tmp_path / "out"

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(_make_project(tmp_path, group=None, status="published") / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(output_dir),
            "--api-key",
            raw_key,
            "--users-db",
            str(db_path),
        ]
    )
    assert code == 0
    saved = list((output_dir / "carol" / "ungrouped").glob("*.txt"))
    assert len(saved) == 1


def test_apikey_revoke_then_verify_fails(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    admin_flags = ["--as-username", "admin", "--as-password", "admin", "--users-db", str(db_path)]

    cli.main(["apikey", "create", "carol", *admin_flags])
    raw_key = capsys.readouterr().out.strip()
    [key_row] = store.list_api_keys("carol")

    code = cli.main(["apikey", "revoke", str(key_row["id"]), *admin_flags])
    capsys.readouterr()
    assert code == 0

    with pytest.raises(InvalidCredentials):
        store.verify_api_key(raw_key)


def test_apikey_list_shows_status(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    admin_flags = ["--as-username", "admin", "--as-password", "admin", "--users-db", str(db_path)]
    cli.main(["apikey", "create", "carol", *admin_flags])
    capsys.readouterr()

    code = cli.main(["apikey", "list", "carol", *admin_flags])
    out = capsys.readouterr().out
    assert code == 0
    assert "active" in out


# -- role/group enforcement on generate/list --------------------------------


def test_generate_denied_for_wrong_group(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    store.create_group("Beta Industries")
    # carol is NOT assigned to Beta Industries

    project = _make_project(tmp_path, group="Beta Industries", status="published")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
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


def test_generate_allowed_after_group_assignment(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    store.create_group("Beta Industries")
    store.assign_user_to_group("carol", "Beta Industries")

    project = _make_project(tmp_path, group="Beta Industries", status="published")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
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


def test_generate_denied_for_draft_schema_as_config_engineer(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")

    project = _make_project(tmp_path, group=None, status="draft")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
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


def test_generate_draft_schema_allowed_for_template_engineer(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("bob", "hunter22pw", "template_engineer")

    project = _make_project(tmp_path, group=None, status="draft")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
            "--username",
            "bob",
            "--password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    assert code == 0


def test_generate_without_credentials_is_unrestricted_legacy_behavior(tmp_path: Path, capsys):
    # No users.db even created here — matches every pre-Phase-6 test and
    # solo-mode's "the role system is invisible unless you create users".
    project = _make_project(tmp_path, group="Some Group", status="draft")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
            "--users-db",
            str(tmp_path / "unused-users.db"),
        ]
    )
    assert code == 0


def test_generate_wrong_password_reports_clean_auth_error(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")

    project = _make_project(tmp_path, group=None, status="published")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
            "--username",
            "carol",
            "--password",
            "wrong-password",
            "--users-db",
            str(db_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
    assert store  # keep reference


def test_list_scoped_to_config_engineer_group_and_status(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    store.create_group("Acme Corp")
    store.assign_user_to_group("carol", "Acme Corp")

    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    schemas_dir.mkdir()
    templates_dir.mkdir()
    (templates_dir / "t.j2").write_text("x", encoding="utf-8")

    def _write(id_, group, status):
        group_line = f'group: "{group}"\n' if group else ""
        content = (
            f"name: {id_}\nid: {id_}\nversion: 1\nstatus: {status}\n"
            f"{group_line}template: t.j2\nfields: []\n"
        )
        (schemas_dir / f"{id_}.yaml").write_text(content, encoding="utf-8")

    _write("published_acme", "Acme Corp", "published")
    _write("draft_acme", "Acme Corp", "draft")
    _write("published_other", "Beta Industries", "published")
    _write("published_ungrouped", None, "published")

    code = cli.main(
        [
            "list",
            "--dir",
            str(schemas_dir),
            "--username",
            "carol",
            "--password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "published_acme" in out
    assert "draft_acme" not in out
    assert "published_other" not in out
    assert "published_ungrouped" in out


def test_list_unscoped_when_no_credentials_given(tmp_path: Path, capsys):
    code = cli.main(["list", "--dir", str(SCHEMAS_DIR)])
    out = capsys.readouterr().out
    assert code == 0
    assert "server_provisioning" in out


def test_list_without_auth_flags_never_touches_users_db(tmp_path: Path, capsys, monkeypatch):
    # Regression test: `list`/`generate` used to build an AuthStore
    # unconditionally, which bootstraps admin/admin on first open — meaning
    # a plain `configgen list` with zero auth flags silently created a real
    # users.db as a side effect. It must not, even at the default path.
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    code = cli.main(["list", "--dir", str(SCHEMAS_DIR)])
    capsys.readouterr()
    assert code == 0
    assert not (tmp_path / "resources" / "data" / "users.db").exists()


def test_generate_without_auth_flags_never_touches_users_db(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr("configgen.paths.app_root", lambda: tmp_path)
    project = _make_project(tmp_path, group=None, status="published")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")

    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    capsys.readouterr()
    assert code == 0
    assert not (tmp_path / "resources" / "data" / "users.db").exists()


# -- generation log ----------------------------------------------------------


def test_log_list_filters_by_role(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")
    store.create_user("dave", "hunter22pw", "config_engineer")
    carol = store.get_user("carol")
    dave = store.get_user("dave")
    store.record_generation(
        carol, schema_id="widget", schema_version=1, form_inputs={}, output_filename="a.txt"
    )
    store.record_generation(
        dave, schema_id="widget", schema_version=1, form_inputs={}, output_filename="b.txt"
    )

    code = cli.main(
        [
            "log",
            "list",
            "--as-username",
            "carol",
            "--as-password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "a.txt" in out
    assert "b.txt" not in out


def test_generate_records_log_entry_visible_via_log_list(tmp_path: Path, capsys):
    db_path = _bootstrap(tmp_path)
    store = AuthStore(db_path)
    store.create_user("carol", "hunter22pw", "config_engineer")

    project = _make_project(tmp_path, group=None, status="published")
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "world"}), encoding="utf-8")
    cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
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
    capsys.readouterr()

    code = cli.main(
        [
            "log",
            "list",
            "--as-username",
            "carol",
            "--as-password",
            "hunter22pw",
            "--users-db",
            str(db_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "widget" in out
    assert "carol" in out


def test_log_command_without_subcommand_prints_help(capsys):
    code = cli.main(["log"])
    out = capsys.readouterr().out
    assert code == 0
    assert "usage" in out.lower()
