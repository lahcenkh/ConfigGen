"""Packaging artifacts (§16) aren't unit-testable in the usual sense — a
.spec file only means something inside a real PyInstaller build, and the
signing/Docker scripts only mean something on a real machine/daemon — but
each one can still be checked for "is this even well-formed," which is
what these tests do."""

import runpy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGING = REPO_ROOT / "packaging"


def test_run_configgen_entry_point_is_importable_and_absolute():
    source = (REPO_ROOT / "run_configgen.py").read_text(encoding="utf-8")
    compile(source, "run_configgen.py", "exec")
    assert "from configgen.app import main" in source
    assert "from .app" not in source  # a relative import would fail once frozen (§19)


def test_run_configgen_does_not_launch_on_import():
    # Guarded by `if __name__ == "__main__":` — importing it as a module
    # (run_name != "__main__") must not call main()/open a window.
    module = runpy.run_path(str(REPO_ROOT / "run_configgen.py"), run_name="not_main")
    assert "main" in module


def test_run_configgen_cli_entry_point_is_importable_and_absolute():
    source = (REPO_ROOT / "run_configgen_cli.py").read_text(encoding="utf-8")
    compile(source, "run_configgen_cli.py", "exec")
    assert "from configgen.cli import main" in source
    assert "from .cli" not in source  # a relative import would fail once frozen (§19)


def test_run_configgen_cli_does_not_launch_on_import():
    module = runpy.run_path(str(REPO_ROOT / "run_configgen_cli.py"), run_name="not_main")
    assert "main" in module


def test_configgen_spec_is_syntactically_valid():
    source = (PACKAGING / "ConfigGen.spec").read_text(encoding="utf-8")
    compile(source, "ConfigGen.spec", "exec")


def test_configgen_spec_references_the_absolute_import_entry_point():
    source = (PACKAGING / "ConfigGen.spec").read_text(encoding="utf-8")
    assert "run_configgen.py" in source
    assert "icon.ico" in source


def test_configgen_spec_builds_both_gui_and_cli_targets():
    source = (PACKAGING / "ConfigGen.spec").read_text(encoding="utf-8")
    assert "run_configgen_cli.py" in source
    assert 'name="ConfigGen-CLI"' in source
    assert "console=True" in source  # the CLI exe must attach to a terminal
    assert "console=False" in source  # the GUI exe must not
    # Each build target's own version resource, not one shared/misattributed.
    assert "version_info.txt" in source
    assert "version_info_cli.txt" in source


def test_dockerfile_is_cli_only_and_installs_base_deps():
    text = (PACKAGING / "Dockerfile").read_text(encoding="utf-8")
    assert "ENTRYPOINT" in text
    assert "configgen" in text
    assert "VOLUME" in text

    run_lines = [line for line in text.splitlines() if line.strip().startswith("RUN pip install")]
    assert run_lines, "Dockerfile has no `RUN pip install` instruction"
    # Must not pull the gui extra - that's the whole point of a CLI image.
    assert all(".[gui]" not in line for line in run_lines)


def test_sign_and_deploy_cert_scripts_exist_and_are_powershell():
    for name in ("sign.ps1", "deploy-cert.ps1"):
        path = PACKAGING / name
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert text.strip()
        assert "$ErrorActionPreference" in text


def test_icon_and_gitkeep_are_not_both_missing():
    assert (PACKAGING / "icon.ico").is_file()
    assert (PACKAGING / "icon.png").is_file()
