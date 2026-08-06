from pathlib import Path

from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file

from tools.make_version_info import render, version_tuple

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_version_tuple_pads_semantic_version_to_four_parts():
    assert version_tuple("0.1.0") == (0, 1, 0, 0)


def test_version_tuple_truncates_a_longer_version():
    assert version_tuple("1.2.3.4.5") == (1, 2, 3, 4)


def test_render_produces_a_loadable_vsversioninfo_structure(tmp_path: Path):
    text = render(
        app_name="Widget",
        version="2.3.1",
        author="Someone",
        description="A test app.",
    )
    version_file = tmp_path / "version_info.txt"
    version_file.write_text(text, encoding="utf-8")

    info = load_version_info_from_text_file(str(version_file))
    assert info.ffi.fileVersionMS == (2 << 16) | 3
    assert info.ffi.fileVersionLS == (1 << 16) | 0

    fields = {s.name: s.val for s in info.kids[0].kids[0].kids}
    assert fields["ProductName"] == "Widget"
    assert fields["FileVersion"] == "2.3.1"
    assert fields["FileDescription"] == "A test app."
    assert fields["CompanyName"] == "Someone"
    assert fields["LegalCopyright"] == "Copyright (c) Someone"
    assert fields["OriginalFilename"] == "Widget.exe"


def test_committed_version_info_file_is_loadable():
    version_info_path = REPO_ROOT / "packaging" / "version_info.txt"
    assert version_info_path.is_file()
    info = load_version_info_from_text_file(str(version_info_path))
    fields = {s.name: s.val for s in info.kids[0].kids[0].kids}
    assert fields["ProductName"] == "ConfigGen"


def test_committed_cli_version_info_file_is_loadable_and_distinct():
    version_info_path = REPO_ROOT / "packaging" / "version_info_cli.txt"
    assert version_info_path.is_file()
    info = load_version_info_from_text_file(str(version_info_path))
    fields = {s.name: s.val for s in info.kids[0].kids[0].kids}
    assert fields["ProductName"] == "ConfigGen-CLI"
    assert fields["OriginalFilename"] == "ConfigGen-CLI.exe"
    assert "command-line" in fields["FileDescription"]


def test_main_writes_both_gui_and_cli_version_info_files(tmp_path: Path, monkeypatch):
    import tools.make_version_info as make_version_info

    monkeypatch.setattr(make_version_info, "REPO_ROOT", tmp_path)
    (tmp_path / "packaging").mkdir()

    make_version_info.main()

    gui_info = load_version_info_from_text_file(str(tmp_path / "packaging" / "version_info.txt"))
    cli_info = load_version_info_from_text_file(
        str(tmp_path / "packaging" / "version_info_cli.txt")
    )
    gui_fields = {s.name: s.val for s in gui_info.kids[0].kids[0].kids}
    cli_fields = {s.name: s.val for s in cli_info.kids[0].kids[0].kids}
    assert gui_fields["ProductName"] == "ConfigGen"
    assert cli_fields["ProductName"] == "ConfigGen-CLI"
