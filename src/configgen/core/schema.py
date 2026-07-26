"""YAML loader and the Field/Document/Schema dataclasses that everything
else in core operates on. Loading a schema does NOT validate it — call
`schema_validator.validate_schema_dict` first (see that module) so failures
surface as structured errors, not attribute errors deep in the form builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path

import yaml

FIELD_TYPES = {
    "string",
    "int",
    "bool",
    "choice",
    "ip",
    "ip_cidr",
    "network",
    "cidr",
    "port",
    "lookup",
    "text",
}


@dataclass
class Field:
    key: str
    label: str
    type: str
    section: str | None = None
    required: bool = False
    default: object = None
    help: str | None = None
    pattern: str | None = None
    example: str | None = None
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None
    from_db: dict | None = None
    visible_if: dict | None = None
    required_if: dict | None = None
    clear_when: dict | None = None


@dataclass
class Document:
    key: str
    label: str
    template: str


@dataclass
class Schema:
    name: str
    id: str
    fields: list[Field]
    group: str | None = None
    version: int = 1
    status: str = "draft"
    description: str | None = None
    tags: list[str] = dc_field(default_factory=list)
    supports_variants: bool = False
    prepare: str | None = None
    preflight: str | None = None
    comment_prefix: str = "!"
    template: str | None = None
    documents: list[Document] | None = None
    identity_field: str | None = None
    source_path: Path | None = None

    def field_map(self) -> dict[str, Field]:
        return {f.key: f for f in self.fields}

    def document_list(self) -> list[Document]:
        """Normalizes the single-`template` and multi-`documents` forms into
        one list, so callers never branch on which form the schema used."""
        if self.documents:
            return self.documents
        return [Document(key="primary", label=self.name, template=self.template)]


def load_schema_dict(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def schema_from_dict(data: dict, source_path: str | Path | None = None) -> Schema:
    fields = [Field(**f) for f in data.get("fields", [])]
    documents = None
    if "documents" in data and data["documents"]:
        documents = [Document(**d) for d in data["documents"]]

    return Schema(
        name=data["name"],
        id=data["id"],
        fields=fields,
        group=data.get("group"),
        version=data.get("version", 1),
        status=data.get("status", "draft"),
        description=data.get("description"),
        tags=data.get("tags", []),
        supports_variants=data.get("supports_variants", False),
        prepare=data.get("prepare"),
        preflight=data.get("preflight"),
        comment_prefix=data.get("comment_prefix", "!"),
        template=data.get("template"),
        documents=documents,
        identity_field=data.get("identity_field"),
        source_path=Path(source_path) if source_path else None,
    )


def load_schema(path: str | Path) -> Schema:
    data = load_schema_dict(path)
    return schema_from_dict(data, source_path=path)


def project_dirs_for(schema_path: str | Path) -> tuple[Path, Path]:
    """A schema at `<root>/schemas/foo.yaml` keeps its templates and prepare
    hooks in sibling `<root>/templates/` and `<root>/prepare/` folders —
    true both for `resources/` and for a self-contained `examples/` set."""
    root = Path(schema_path).resolve().parent.parent
    return root / "templates", root / "prepare"


def project_data_dir_for(schema_path: str | Path) -> Path:
    """The sibling `<root>/data/` folder holding queries.yaml and the .db
    file, for schemas that use `from_db`."""
    root = Path(schema_path).resolve().parent.parent
    return root / "data"


def project_history_dir_for(schema_path: str | Path) -> Path:
    """The sibling `<root>/.history/` folder where saved schema+template
    versions live, per §10 of the build plan."""
    root = Path(schema_path).resolve().parent.parent
    return root / ".history"


def project_preflight_dir_for(schema_path: str | Path) -> Path:
    """The sibling `<root>/preflight/` folder holding a project's own
    `<platform>.py` checkers, per §11.3 of the build plan."""
    root = Path(schema_path).resolve().parent.parent
    return root / "preflight"


def find_schema_files(schemas_dir: str | Path) -> list[Path]:
    schemas_dir = Path(schemas_dir)
    if not schemas_dir.is_dir():
        return []
    return sorted({*schemas_dir.glob("*.yaml"), *schemas_dir.glob("*.yml")})
