from pathlib import Path

from configgen import cli

SCHEMA_V1 = """\
name: Widget
id: widget
version: 1
status: published
template: widget.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "widget.yaml").write_text(SCHEMA_V1, encoding="utf-8")
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    return project


def test_history_list_empty(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    code = cli.main(["history", "widget", "--dir", str(project / "schemas")])
    out = capsys.readouterr().out
    assert code == 0
    assert "No history found" in out


def test_history_save_requires_author(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    code = cli.main(["history", "widget", "--dir", str(project / "schemas"), "--save"])
    err = capsys.readouterr().err
    assert code == 1
    assert "--author" in err


def test_history_save_and_list(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    schemas_dir = str(project / "schemas")

    code = cli.main(
        [
            "history",
            "widget",
            "--dir",
            schemas_dir,
            "--save",
            "--author",
            "bob",
            "--note",
            "initial version",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "saved version 1" in out

    code = cli.main(["history", "widget", "--dir", schemas_dir])
    out = capsys.readouterr().out
    assert code == 0
    assert "v1" in out
    assert "bob" in out
    assert "initial version" in out


def test_history_save_duplicate_version_rejected(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    schemas_dir = str(project / "schemas")
    cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "bob"])
    capsys.readouterr()

    code = cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "bob"])
    err = capsys.readouterr().err
    assert code == 1
    assert "already saved" in err


def test_history_diff_between_versions(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    schemas_dir = str(project / "schemas")
    schema_path = project / "schemas" / "widget.yaml"
    template_path = project / "templates" / "widget.j2"

    cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "bob"])
    capsys.readouterr()

    schema_path.write_text(SCHEMA_V1.replace("version: 1", "version: 2"), encoding="utf-8")
    template_path.write_text("hello there {{ name }}", encoding="utf-8")
    cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "alice"])
    capsys.readouterr()

    code = cli.main(["history", "widget", "--dir", schemas_dir, "--diff", "1", "2"])
    out = capsys.readouterr().out
    assert code == 0
    assert "schema.yaml" in out
    assert "-version: 1" in out
    assert "+version: 2" in out
    assert "-hello {{ name }}" in out
    assert "+hello there {{ name }}" in out


def test_history_diff_unknown_version_reports_clean_error(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    schemas_dir = str(project / "schemas")
    cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "bob"])
    capsys.readouterr()

    code = cli.main(["history", "widget", "--dir", schemas_dir, "--diff", "1", "99"])
    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err


def test_history_restore_creates_new_version_and_replaces_live_files(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    schemas_dir = str(project / "schemas")
    schema_path = project / "schemas" / "widget.yaml"
    template_path = project / "templates" / "widget.j2"

    cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "bob"])
    capsys.readouterr()

    schema_path.write_text(SCHEMA_V1.replace("version: 1", "version: 2"), encoding="utf-8")
    template_path.write_text("hello there {{ name }}", encoding="utf-8")
    cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "alice"])
    capsys.readouterr()

    code = cli.main(
        ["history", "widget", "--dir", schemas_dir, "--restore", "1", "--author", "carol"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "restored version 1 as new version 3" in out
    assert template_path.read_text(encoding="utf-8") == "hello {{ name }}"

    code = cli.main(["history", "widget", "--dir", schemas_dir])
    out = capsys.readouterr().out
    assert "v3" in out
    assert "carol" in out
    assert "Restored from version 1" in out


def test_history_restore_requires_author(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    schemas_dir = str(project / "schemas")
    cli.main(["history", "widget", "--dir", schemas_dir, "--save", "--author", "bob"])
    capsys.readouterr()

    code = cli.main(["history", "widget", "--dir", schemas_dir, "--restore", "1"])
    err = capsys.readouterr().err
    assert code == 1
    assert "--author" in err


def test_history_unknown_schema_id_reports_clean_error(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    code = cli.main(["history", "does_not_exist", "--dir", str(project / "schemas")])
    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
