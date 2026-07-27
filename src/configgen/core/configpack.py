"""Config pack export/import (§14 of the build plan) — bundling a schema +
its templates/prepare hook/preflight checker into a portable
`.configpack.zip`, and registering one back into a resources/ tree.

Import validates against a temporary extraction first (§2.6's checks, the
same ones `configgen check` runs) so a broken or malicious pack never
touches the live resources/ tree — either the whole pack registers, or
nothing does.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from configgen.core.preflight import BUILTIN_CHECKS
from configgen.core.schema import (
    find_schema_files,
    load_schema,
    load_schema_dict,
    project_dirs_for,
    project_preflight_dir_for,
    schema_from_dict,
)
from configgen.core.schema_validator import SchemaValidationError, validate_schema

_ID_RE = re.compile(r"(?m)^id:\s*\S+")


class ConfigPackError(Exception):
    pass


class ConfigPackConflict(ConfigPackError):
    """Raised when the packaged id already exists in the target resources
    tree — the caller must retry with `on_conflict="overwrite"` or
    `"rename"` (§14.2: "prompt the user to overwrite or rename")."""

    def __init__(self, schema_id: str, existing_path: Path):
        self.schema_id = schema_id
        self.existing_path = existing_path
        super().__init__(
            f"a schema with id '{schema_id}' already exists at {existing_path}; "
            "pass on_conflict='overwrite' or 'rename'"
        )


@dataclass
class ImportResult:
    schema_id: str
    schema_path: Path
    conflict_resolved: bool


def export_config_pack(
    schema_path: str | Path,
    output_path: str | Path,
    *,
    author: str | None = None,
    description: str | None = None,
    sample_values: dict | None = None,
) -> Path:
    """Bundles a schema + its templates/prepare hook/preflight checker into
    a `.configpack.zip`. Only a *custom* preflight checker is bundled — a
    built-in platform name (`BUILTIN_CHECKS`) has nothing to bundle, since
    every install already has it."""
    schema_path = Path(schema_path)
    schema = load_schema(schema_path)
    templates_dir, prepare_dir = project_dirs_for(schema_path)
    preflight_dir = project_preflight_dir_for(schema_path)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": schema.id,
        "version": schema.version,
        "author": author,
        "description": description or schema.description,
        "tags": schema.tags,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "configgen_format": 1,
    }

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(schema_path, "schema.yaml")
        for doc in schema.document_list():
            template_path = templates_dir / doc.template
            if template_path.is_file():
                zf.write(template_path, f"templates/{doc.template}")
        if schema.prepare:
            hook_path = prepare_dir / f"{schema.prepare}.py"
            if hook_path.is_file():
                zf.write(hook_path, f"prepare/{schema.prepare}.py")
        if schema.preflight and schema.preflight not in BUILTIN_CHECKS:
            check_path = preflight_dir / f"{schema.preflight}.py"
            if check_path.is_file():
                zf.write(check_path, f"preflight/{schema.preflight}.py")
        if sample_values is not None:
            zf.writestr("sample_values.json", json.dumps(sample_values, indent=2, default=str))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return output_path


def _existing_schema_path_for_id(schemas_dir: Path, schema_id: str) -> Path | None:
    if not schemas_dir.is_dir():
        return None
    for path in find_schema_files(schemas_dir):
        if load_schema_dict(path).get("id") == schema_id:
            return path
    return None


def _rewrite_id(text: str, new_id: str) -> str:
    new_text, count = _ID_RE.subn(f"id: {new_id}", text, count=1)
    if count == 0:
        raise ConfigPackError("packaged schema.yaml has no top-level 'id:' field")
    return new_text


def import_config_pack(
    zip_path: str | Path,
    resources_root: str | Path,
    *,
    on_conflict: str = "error",
    new_id: str | None = None,
) -> ImportResult:
    """Extracts and registers a `.configpack.zip` into `resources_root`.

    `on_conflict` controls what happens when the packaged id already
    exists: `"error"` (default — raises `ConfigPackConflict`),
    `"overwrite"`, or `"rename"` (requires `new_id`)."""
    zip_path = Path(zip_path)
    resources_root = Path(resources_root)
    schemas_dir = resources_root / "schemas"

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        if "schema.yaml" not in names:
            raise ConfigPackError(f"{zip_path} is not a config pack: missing schema.yaml")

        schema_text = zf.read("schema.yaml").decode("utf-8")
        data = yaml.safe_load(schema_text) or {}
        schema_id = data.get("id")
        if not schema_id:
            raise ConfigPackError("packaged schema.yaml has no 'id' field")

        existing = _existing_schema_path_for_id(schemas_dir, schema_id)
        final_id = schema_id
        if existing is not None:
            if on_conflict == "rename":
                if not new_id:
                    raise ConfigPackError("on_conflict='rename' requires new_id")
                final_id = new_id
                schema_text = _rewrite_id(schema_text, new_id)
                data = yaml.safe_load(schema_text)
            elif on_conflict == "overwrite":
                pass
            else:
                raise ConfigPackConflict(schema_id, existing)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tmp_templates = tmp_path / "templates"
            tmp_templates.mkdir()
            tmp_prepare = tmp_path / "prepare"

            schema = schema_from_dict(data, source_path=tmp_path / "schema.yaml")
            for doc in schema.document_list():
                member = f"templates/{doc.template}"
                if member in names:
                    (tmp_templates / doc.template).write_bytes(zf.read(member))

            if schema.prepare and f"prepare/{schema.prepare}.py" in names:
                tmp_prepare.mkdir()
                (tmp_prepare / f"{schema.prepare}.py").write_bytes(
                    zf.read(f"prepare/{schema.prepare}.py")
                )

            try:
                validate_schema(
                    data,
                    templates_dir=tmp_templates,
                    prepare_dir=tmp_prepare if schema.prepare else None,
                )
            except SchemaValidationError as exc:
                raise ConfigPackError(f"imported schema failed validation: {exc}") from exc

            # Validated — now register it for real.
            schemas_dir.mkdir(parents=True, exist_ok=True)
            templates_dest = resources_root / "templates"
            templates_dest.mkdir(parents=True, exist_ok=True)

            schema_dest = schemas_dir / f"{final_id}.yaml"
            if (
                on_conflict == "overwrite"
                and existing is not None
                and existing != schema_dest
                and existing.is_file()
            ):
                existing.unlink()
            schema_dest.write_text(schema_text, encoding="utf-8")

            for doc in schema.document_list():
                src = tmp_templates / doc.template
                if src.is_file():
                    shutil.copy2(src, templates_dest / doc.template)

            if schema.prepare and (tmp_prepare / f"{schema.prepare}.py").is_file():
                prepare_dest = resources_root / "prepare"
                prepare_dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    tmp_prepare / f"{schema.prepare}.py", prepare_dest / f"{schema.prepare}.py"
                )

            if schema.preflight and f"preflight/{schema.preflight}.py" in names:
                preflight_dest = resources_root / "preflight"
                preflight_dest.mkdir(parents=True, exist_ok=True)
                (preflight_dest / f"{schema.preflight}.py").write_bytes(
                    zf.read(f"preflight/{schema.preflight}.py")
                )

    return ImportResult(
        schema_id=final_id, schema_path=schema_dest, conflict_resolved=existing is not None
    )
