from pathlib import Path

from configgen import paths


def test_bundle_root_matches_app_root_in_dev_mode():
    # Not frozen: no PyInstaller bundle exists at all, just the checked-out
    # source tree — both should point at the same place.
    assert paths.bundle_root() == paths.app_root()


def test_bundle_root_uses_meipass_when_frozen(monkeypatch, tmp_path: Path):
    fake_meipass = tmp_path / "_internal"
    fake_exe_dir = tmp_path / "dist" / "ConfigGen"
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(fake_meipass), raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(fake_exe_dir / "ConfigGen.exe"))

    # PyInstaller >=6 puts bundled data (resources/, packaging/icon.ico)
    # under _internal/, one level below the exe itself — bundle_root()
    # must resolve there, not next to the exe like app_root() does.
    assert paths.bundle_root() == fake_meipass
    assert paths.app_root() == fake_exe_dir
    assert paths.resources_dir() == fake_meipass / "resources"
    assert paths.icon_path() == fake_meipass / "packaging" / "icon.ico"

    # Writable runtime state stays next to the exe, not inside the bundle.
    assert paths.users_db_path() == fake_exe_dir / "users.db"
    assert paths.output_dir() == fake_exe_dir / "output"
