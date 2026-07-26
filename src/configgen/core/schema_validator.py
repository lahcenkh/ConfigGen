"""Validates a loaded schema YAML dict against a Pydantic model plus a set of
structural checks (§2.6 of the build plan) before a form is ever built from
it. The goal is that a bad schema fails at load time — or via
`configgen check` — with a field path and a suggestion, never as an
AttributeError surfacing mid-render.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from configgen.core.schema import FIELD_TYPES


class SchemaIssue:
    def __init__(self, path: str, message: str, suggestion: str | None = None):
        self.path = path
        self.message = message
        self.suggestion = suggestion

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SchemaIssue) and (self.path, self.message) == (
            other.path,
            other.message,
        )

    def __repr__(self) -> str:
        return f"SchemaIssue(path={self.path!r}, message={self.message!r})"

    def __str__(self) -> str:
        text = f"{self.path}: {self.message}"
        if self.suggestion:
            text += f" ({self.suggestion})"
        return text


class SchemaValidationError(Exception):
    def __init__(self, issues: list[SchemaIssue]):
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))


class _FieldModel(BaseModel):
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

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in FIELD_TYPES:
            raise ValueError(f"unrecognized field type '{value}'")
        return value


class _DocumentModel(BaseModel):
    key: str
    label: str
    template: str


class _SchemaModel(BaseModel):
    name: str
    group: str | None = None
    id: str
    version: int = 1
    status: Literal["draft", "published", "deprecated"] = "draft"
    description: str | None = None
    tags: list[str] = []
    supports_variants: bool = False
    prepare: str | None = None
    preflight: str | None = None
    comment_prefix: str = "!"
    template: str | None = None
    documents: list[_DocumentModel] | None = None
    identity_field: str | None = None
    fields: list[_FieldModel]

    @model_validator(mode="after")
    def _one_output_form(self) -> _SchemaModel:
        has_template = bool(self.template)
        has_documents = bool(self.documents)
        if has_template == has_documents:
            raise ValueError(
                "declare exactly one of 'template' or 'documents', not both or neither"
            )
        return self


def _pydantic_issues(exc: ValidationError) -> list[SchemaIssue]:
    issues = []
    for err in exc.errors():
        path = ".".join(str(p) for p in err["loc"]) or "<schema>"
        issues.append(SchemaIssue(path, err["msg"]))
    return issues


def _check_duplicate_keys(model: _SchemaModel) -> list[SchemaIssue]:
    seen: dict[str, int] = {}
    issues = []
    for f in model.fields:
        seen[f.key] = seen.get(f.key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            issues.append(
                SchemaIssue(f"fields[{key}]", f"duplicate field key '{key}' ({count} occurrences)")
            )
    return issues


def _check_patterns_compile(model: _SchemaModel) -> list[SchemaIssue]:
    issues = []
    for f in model.fields:
        if f.pattern is None:
            continue
        try:
            re.compile(f.pattern)
        except re.error as exc:
            issues.append(
                SchemaIssue(
                    f"fields[{f.key}].pattern",
                    f"invalid regex: {exc}",
                    suggestion="patterns must be single-quoted in YAML so '\\d' isn't unescaped",
                )
            )
    return issues


def _check_defaults_match_pattern(model: _SchemaModel) -> list[SchemaIssue]:
    issues = []
    for f in model.fields:
        if f.pattern is None or f.default is None:
            continue
        try:
            compiled = re.compile(f.pattern)
        except re.error:
            continue  # already reported by _check_patterns_compile
        if not compiled.fullmatch(str(f.default)):
            suggestion = f"expected like {f.example}" if f.example else None
            issues.append(
                SchemaIssue(
                    f"fields[{f.key}].default",
                    f"default {f.default!r} does not match pattern '{f.pattern}'",
                    suggestion=suggestion,
                )
            )
    return issues


def _check_conditional_references(model: _SchemaModel) -> list[SchemaIssue]:
    issues = []
    keys = {f.key for f in model.fields}
    for f in model.fields:
        for attr in ("visible_if", "required_if", "clear_when"):
            condition = getattr(f, attr)
            if not condition:
                continue
            for other_key in condition:
                if other_key not in keys:
                    issues.append(
                        SchemaIssue(
                            f"fields[{f.key}].{attr}",
                            f"references unknown field '{other_key}'",
                        )
                    )
    return issues


def _check_templates_exist(model: _SchemaModel, templates_dir: Path | None) -> list[SchemaIssue]:
    if templates_dir is None:
        return []
    issues = []
    if model.documents:
        documents = model.documents
    else:
        # _one_output_form guarantees template is set when documents is not.
        assert model.template is not None
        documents = [_DocumentModel(key="primary", label=model.name, template=model.template)]
    for doc in documents:
        if not (templates_dir / doc.template).is_file():
            issues.append(
                SchemaIssue(
                    f"documents[{doc.key}].template" if model.documents else "template",
                    f"template file not found: {doc.template}",
                    suggestion=f"expected at {templates_dir / doc.template}",
                )
            )
    return issues


def _check_prepare_hook_exists(model: _SchemaModel, prepare_dir: Path | None) -> list[SchemaIssue]:
    if prepare_dir is None or not model.prepare:
        return []
    issues = []
    if not (prepare_dir / f"{model.prepare}.py").is_file():
        issues.append(
            SchemaIssue(
                "prepare",
                f"prepare hook not found: {model.prepare}",
                suggestion=f"expected {prepare_dir / (model.prepare + '.py')}",
            )
        )
    return issues


def _check_port_lookup_no_default(model: _SchemaModel) -> list[SchemaIssue]:
    issues = []
    for f in model.fields:
        if f.type in ("port", "lookup") and f.default is not None:
            issues.append(
                SchemaIssue(
                    f"fields[{f.key}].default",
                    f"'{f.type}' fields must not declare a default",
                    suggestion=(
                        "use 'example' to show the expected format as placeholder text instead"
                    ),
                )
            )
    return issues


def _check_from_db_queries(
    model: _SchemaModel, known_queries: set[str] | None
) -> list[SchemaIssue]:
    if known_queries is None:
        return []
    issues = []
    for f in model.fields:
        if not f.from_db:
            continue
        query = f.from_db.get("query")
        if query not in known_queries:
            issues.append(
                SchemaIssue(
                    f"fields[{f.key}].from_db.query",
                    f"unknown query '{query}'",
                    suggestion="add it to queries.yaml or fix the query name",
                )
            )
    return issues


def validate_schema(
    data: dict,
    *,
    templates_dir: Path | str | None = None,
    prepare_dir: Path | str | None = None,
    known_queries: set[str] | None = None,
) -> None:
    """Raises SchemaValidationError if the schema fails any check in §2.6."""
    templates_dir = Path(templates_dir) if templates_dir else None
    prepare_dir = Path(prepare_dir) if prepare_dir else None

    try:
        model = _SchemaModel.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(_pydantic_issues(exc)) from exc

    issues = [
        *_check_duplicate_keys(model),
        *_check_patterns_compile(model),
        *_check_defaults_match_pattern(model),
        *_check_conditional_references(model),
        *_check_port_lookup_no_default(model),
        *_check_templates_exist(model, templates_dir),
        *_check_prepare_hook_exists(model, prepare_dir),
        *_check_from_db_queries(model, known_queries),
    ]
    if issues:
        raise SchemaValidationError(issues)
