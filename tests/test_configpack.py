import zipfile
from pathlib import Path

import pytest

from configgen.core.configpack import (
    ConfigPackConflict,
    ConfigPackError,
    export_config_pack,
    import_config_pack,
)

WIDGET_SCHEMA = """\
name: Widget
id: widget
version: 3
status: published
description: A test widget
tags:
  - net
  - test
identity_field: name
prepare: adjust
preflight: acme_custom
template: widget.j2
fields:
  - key: name
    label: Name
    type: string
    required: true
"""

PREPARE_HOOK = """\
def prepare(values, context, services):
    return values
"""


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "prepare").mkdir()
    (project / "preflight").mkdir()
    (project / "schemas" / "widget.yaml").write_text(WIDGET_SCHEMA, encoding="utf-8")
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    (project / "prepare" / "adjust.py").write_text(PREPARE_HOOK, encoding="utf-8")
    (project / "preflight" / "acme_custom.py").write_text(
        "def check(text):\n    return []\n", encoding="utf-8"
    )
    return project


# -- export ---------------------------------------------------------


def test_export_bundles_schema_template_and_prepare_hook(tmp_path: Path):
    project = _project(tmp_path)
    output = export_config_pack(
        project / "schemas" / "widget.yaml",
        tmp_path / "widget.configpack.zip",
        author="alice",
        description="override description",
    )

    assert output.is_file()
    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
        assert names == {
            "schema.yaml",
            "templates/widget.j2",
            "prepare/adjust.py",
            "preflight/acme_custom.py",
            "manifest.json",
        }
        manifest = zf.read("manifest.json").decode("utf-8")
        assert '"author": "alice"' in manifest
        assert '"description": "override description"' in manifest
        assert '"id": "widget"' in manifest
        assert '"version": 3' in manifest


def test_export_skips_builtin_preflight_check(tmp_path: Path):
    # "acme_custom" is bundled as a custom preflight check above; a schema
    # referencing an actual BUILTIN_CHECKS name should not try to bundle
    # a nonexistent file.
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "schemas" / "widget.yaml").write_text(
        WIDGET_SCHEMA.replace("preflight: acme_custom", "preflight: junos").replace(
            "prepare: adjust\n", ""
        ),
        encoding="utf-8",
    )
    (project / "templates" / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")

    output = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "out.zip")
    with zipfile.ZipFile(output) as zf:
        assert "preflight/junos.py" not in zf.namelist()


def test_export_bundles_custom_preflight_check(tmp_path: Path):
    project = _project(tmp_path)
    output = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "out.zip")
    with zipfile.ZipFile(output) as zf:
        assert "preflight/acme_custom.py" in zf.namelist()


def test_export_bundles_sample_values(tmp_path: Path):
    project = _project(tmp_path)
    output = export_config_pack(
        project / "schemas" / "widget.yaml",
        tmp_path / "out.zip",
        sample_values={"name": "web01"},
    )
    with zipfile.ZipFile(output) as zf:
        assert "sample_values.json" in zf.namelist()
        assert "web01" in zf.read("sample_values.json").decode("utf-8")


# -- import: happy path ---------------------------------------------------------


def test_import_registers_schema_template_and_prepare_hook(tmp_path: Path):
    project = _project(tmp_path)
    pack = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "widget.zip")

    target = tmp_path / "target"
    result = import_config_pack(pack, target)

    assert result.schema_id == "widget"
    assert result.conflict_resolved is False
    assert result.schema_path == target / "schemas" / "widget.yaml"
    assert (target / "schemas" / "widget.yaml").is_file()
    assert (target / "templates" / "widget.j2").read_text(encoding="utf-8") == "hello {{ name }}"
    assert (target / "prepare" / "adjust.py").is_file()
    assert (target / "preflight" / "acme_custom.py").is_file()


def test_import_rejects_non_configpack_zip(tmp_path: Path):
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("readme.txt", "not a config pack")

    with pytest.raises(ConfigPackError, match="missing schema.yaml"):
        import_config_pack(bad_zip, tmp_path / "target")


def test_import_rejects_pack_that_fails_schema_validation(tmp_path: Path):
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr(
            "schema.yaml",
            "name: Widget\nid: widget\nversion: 1\ntemplate: widget.j2\nfields:\n"
            "  - key: name\n    label: Name\n    type: string\n",
        )
        zf.writestr("manifest.json", "{}")
        # deliberately no templates/widget.j2

    with pytest.raises(ConfigPackError, match="failed validation"):
        import_config_pack(bad_zip, tmp_path / "target")
    # Nothing should have been written on failure.
    assert not (tmp_path / "target").exists()


# -- import: conflicts ---------------------------------------------------------


def test_import_conflict_raises_by_default(tmp_path: Path):
    project = _project(tmp_path)
    pack = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "widget.zip")
    target = tmp_path / "target"
    import_config_pack(pack, target)

    with pytest.raises(ConfigPackConflict) as excinfo:
        import_config_pack(pack, target)
    assert excinfo.value.schema_id == "widget"
    assert excinfo.value.existing_path == target / "schemas" / "widget.yaml"


def test_import_conflict_overwrite_replaces_existing(tmp_path: Path):
    project = _project(tmp_path)
    pack = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "widget.zip")
    target = tmp_path / "target"
    import_config_pack(pack, target)

    # Change the source template, re-export, then overwrite-import.
    (project / "templates" / "widget.j2").write_text("v2 {{ name }}", encoding="utf-8")
    pack2 = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "widget2.zip")
    result = import_config_pack(pack2, target, on_conflict="overwrite")

    assert result.conflict_resolved is True
    assert result.schema_id == "widget"
    assert (target / "templates" / "widget.j2").read_text(encoding="utf-8") == "v2 {{ name }}"


def test_import_conflict_rename_writes_new_id(tmp_path: Path):
    project = _project(tmp_path)
    pack = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "widget.zip")
    target = tmp_path / "target"
    import_config_pack(pack, target)

    result = import_config_pack(pack, target, on_conflict="rename", new_id="widget_v2")

    assert result.schema_id == "widget_v2"
    assert result.conflict_resolved is True
    assert (target / "schemas" / "widget_v2.yaml").is_file()
    assert "id: widget_v2" in (target / "schemas" / "widget_v2.yaml").read_text(encoding="utf-8")
    # Original untouched.
    assert (target / "schemas" / "widget.yaml").is_file()


def test_import_rename_without_new_id_raises(tmp_path: Path):
    project = _project(tmp_path)
    pack = export_config_pack(project / "schemas" / "widget.yaml", tmp_path / "widget.zip")
    target = tmp_path / "target"
    import_config_pack(pack, target)

    with pytest.raises(ConfigPackError, match="requires new_id"):
        import_config_pack(pack, target, on_conflict="rename")
