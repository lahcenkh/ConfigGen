import json
from pathlib import Path

from configgen import cli

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS_DIR = EXAMPLES_ROOT / "schemas"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    _write(
        project / "schemas" / "widget.yaml",
        "name: Widget\nid: widget\nversion: 1\nstatus: published\n"
        "template: widget.j2\n"
        "fields:\n  - key: name\n    label: Name\n    type: string\n    required: true\n",
    )
    _write(project / "templates" / "widget.j2", "{{ name | shout }}")
    return project


# -- examples: real end-to-end sanity ---------------------------------------


def test_plugins_list_examples(capsys):
    code = cli.main(["plugins", "--dir", str(SCHEMAS_DIR)])
    out = capsys.readouterr().out
    assert code == 0
    assert "hook" in out
    assert "device_provisioning" in out
    assert "filter" in out
    assert "to_wildcard" in out


def test_plugins_check_examples_all_resolve(capsys):
    code = cli.main(["plugins", "--dir", str(SCHEMAS_DIR), "--check"])
    out = capsys.readouterr().out
    assert code == 0
    assert "All schema references resolve" in out


# -- plugins list / orphans --------------------------------------------------


def test_plugins_list_reports_orphaned_hook(tmp_path: Path, capsys):
    project = _make_project(tmp_path)  # widget.yaml has no hook:
    _write(project / "hooks" / "unused_hook.py", "def build(v, c, s):\n    return {}\n")

    code = cli.main(["plugins", "--dir", str(project / "schemas")])
    out = capsys.readouterr().out
    assert code == 0
    assert "unused_hook" in out
    assert "WARNING: orphaned hook 'unused_hook'" in out


def test_plugins_list_no_orphan_when_filter_used_in_template(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    _write(
        project / "filters.py",
        "def shout(t):\n    return t.upper()\n\nFILTERS = {'shout': shout}\n",
    )
    code = cli.main(["plugins", "--dir", str(project / "schemas")])
    out = capsys.readouterr().out
    assert code == 0
    assert "shout" in out
    assert "WARNING" not in out


# -- plugins --check ----------------------------------------------------------


def test_plugins_check_reports_dangling_hook_reference(tmp_path: Path, capsys):
    project = tmp_path / "project"
    _write(
        project / "schemas" / "broken.yaml",
        "name: Broken\nid: broken\nversion: 1\nstatus: published\n"
        "hook: ghost_hook\ntemplate: broken.j2\nfields: []\n",
    )
    _write(project / "templates" / "broken.j2", "hello")

    code = cli.main(["plugins", "--dir", str(project / "schemas"), "--check"])
    err = capsys.readouterr().err
    assert code == 1
    assert "broken" in err
    assert "ghost_hook" in err
    assert "Traceback" not in err


def test_plugins_check_reports_dangling_preflight_reference(tmp_path: Path, capsys):
    project = tmp_path / "project"
    _write(
        project / "schemas" / "broken.yaml",
        "name: Broken\nid: broken\nversion: 1\nstatus: published\n"
        "preflight: not-a-real-platform\ntemplate: broken.j2\nfields: []\n",
    )
    _write(project / "templates" / "broken.j2", "hello")

    code = cli.main(["plugins", "--dir", str(project / "schemas"), "--check"])
    err = capsys.readouterr().err
    assert code == 1
    assert "not-a-real-platform" in err


def test_plugins_check_passes_with_builtin_preflight_platform(tmp_path: Path, capsys):
    project = tmp_path / "project"
    _write(
        project / "schemas" / "widget.yaml",
        "name: Widget\nid: widget\nversion: 1\nstatus: published\n"
        "preflight: ios\ntemplate: widget.j2\nfields: []\n",
    )
    _write(project / "templates" / "widget.j2", "hello")

    code = cli.main(["plugins", "--dir", str(project / "schemas"), "--check"])
    out = capsys.readouterr().out
    assert code == 0
    assert "All schema references resolve" in out


# -- filters actually wired into generate/bulk -------------------------------


def test_generate_applies_project_custom_filter(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    _write(
        project / "filters.py",
        "def shout(t):\n    return t.upper()\n\nFILTERS = {'shout': shout}\n",
    )
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"name": "hi"}), encoding="utf-8")

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
            "demo",
        ]
    )
    assert code == 0
    saved = next((tmp_path / "out" / "demo" / "ungrouped").glob("*.txt"))
    assert saved.read_text(encoding="utf-8").strip().endswith("HI")


def test_bulk_applies_project_custom_filter(tmp_path: Path, capsys):
    project = _make_project(tmp_path)
    _write(
        project / "filters.py",
        "def shout(t):\n    return t.upper()\n\nFILTERS = {'shout': shout}\n",
    )
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("name\nhi\n", encoding="utf-8")

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
            "demo",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "1 valid, 0 errors" in out
    saved_dir = (tmp_path / "out" / "demo" / "ungrouped").glob("batch_*/*.txt")
    saved = next(saved_dir)
    assert saved.read_text(encoding="utf-8").strip().endswith("HI")
