import json
import time
from pathlib import Path

from configgen import cli

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
SCHEMAS_DIR = EXAMPLES_ROOT / "schemas"


def _make_widget_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "widget.yaml").write_text(
        "name: Widget\nid: widget\nversion: 1\nstatus: published\n"
        "identity_field: hostname\ntemplate: widget.j2\n"
        "fields:\n"
        "  - key: hostname\n    label: Hostname\n    type: string\n    required: true\n"
        "  - key: note\n    label: Note\n    type: string\n    required: false\n",
        encoding="utf-8",
    )
    (project / "templates" / "widget.j2").write_text(
        "host {{ hostname }}\nnote {{ note }}", encoding="utf-8"
    )
    return project


def _generate(project: Path, output_dir: Path, hostname: str, note: str, username: str = "demo"):
    values_path = project / f"values_{note}.json"
    values_path.write_text(json.dumps({"hostname": hostname, "note": note}), encoding="utf-8")
    code = cli.main(
        [
            "generate",
            "widget",
            "--dir",
            str(project / "schemas"),
            "--values",
            str(values_path),
            "--output",
            str(output_dir),
            "--username",
            username,
        ]
    )
    assert code == 0


# -- two-file mode ---------------------------------------------------------


def test_diff_two_identical_files_produces_empty_diff(tmp_path: Path, capsys):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("same\n", encoding="utf-8")
    file_b.write_text("same\n", encoding="utf-8")

    code = cli.main(["diff", str(file_a), str(file_b)])
    out = capsys.readouterr().out
    assert code == 0
    assert out == ""


def test_diff_two_different_files_shows_changes(tmp_path: Path, capsys):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("hello\n", encoding="utf-8")
    file_b.write_text("goodbye\n", encoding="utf-8")

    code = cli.main(["diff", str(file_a), str(file_b)])
    out = capsys.readouterr().out
    assert code == 0
    assert "-hello" in out
    assert "+goodbye" in out


def test_diff_missing_file_reports_clean_error(tmp_path: Path, capsys):
    file_a = tmp_path / "a.txt"
    file_a.write_text("hello\n", encoding="utf-8")

    code = cli.main(["diff", str(file_a), str(tmp_path / "does-not-exist.txt")])
    err = capsys.readouterr().err
    assert code == 1
    assert "not found" in err


# -- --last mode -------------------------------------------------------------


def test_diff_last_shows_changes_between_two_generations(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    output_dir = tmp_path / "out"
    _generate(project, output_dir, "web01", "first")
    time.sleep(1.1)  # ensure a distinct second-level timestamp
    _generate(project, output_dir, "web01", "second")
    capsys.readouterr()

    code = cli.main(
        [
            "diff",
            "--last",
            "widget",
            "web01",
            "--dir",
            str(project / "schemas"),
            "--output",
            str(output_dir),
            "--username",
            "demo",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "-note first" in out
    assert "+note second" in out


def test_diff_last_insufficient_history_reports_clean_error(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    output_dir = tmp_path / "out"
    _generate(project, output_dir, "web01", "only-one")
    capsys.readouterr()

    code = cli.main(
        [
            "diff",
            "--last",
            "widget",
            "web01",
            "--dir",
            str(project / "schemas"),
            "--output",
            str(output_dir),
            "--username",
            "demo",
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "need at least 2" in err


def test_diff_last_unknown_schema_reports_clean_error(tmp_path: Path, capsys):
    code = cli.main(
        [
            "diff",
            "--last",
            "does_not_exist",
            "web01",
            "--dir",
            str(SCHEMAS_DIR),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err


def test_diff_last_different_identity_has_no_shared_history(tmp_path: Path, capsys):
    project = _make_widget_project(tmp_path)
    output_dir = tmp_path / "out"
    _generate(project, output_dir, "web01", "a")
    time.sleep(1.1)
    _generate(project, output_dir, "web02", "b")  # different host - no history for web01
    capsys.readouterr()

    code = cli.main(
        [
            "diff",
            "--last",
            "widget",
            "web02",
            "--dir",
            str(project / "schemas"),
            "--output",
            str(output_dir),
            "--username",
            "demo",
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "need at least 2" in err
