"""Headless entry point. Subcommands land phase by phase; this phase adds
check / list / generate for form-only (no prepare hook, no DB) configs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from configgen.appinfo import APP_NAME, __version__
from configgen.core.exporter import save_documents
from configgen.core.renderer import RenderError, render_documents
from configgen.core.schema import (
    find_schema_files,
    load_schema_dict,
    project_dirs_for,
    schema_from_dict,
)
from configgen.core.schema_validator import SchemaValidationError, validate_schema
from configgen.core.validators import FieldValidationError, validate_values
from configgen.paths import output_dir, schemas_dir


def _validate_file(schema_path: Path) -> None:
    data = load_schema_dict(schema_path)
    templates_dir, prepare_dir = project_dirs_for(schema_path)
    validate_schema(data, templates_dir=templates_dir, prepare_dir=prepare_dir)


def cmd_check(args: argparse.Namespace) -> int:
    schema_path = Path(args.schema)
    try:
        _validate_file(schema_path)
    except SchemaValidationError as exc:
        print(f"FAILED: {schema_path}", file=sys.stderr)
        for issue in exc.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    data = load_schema_dict(schema_path)
    print(f"OK: {data['name']} ({data['id']}) v{data.get('version', 1)}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    directory = Path(args.dir) if args.dir else schemas_dir()
    files = find_schema_files(directory)
    if not files:
        print(f"No schemas found in {directory}")
        return 0
    exit_code = 0
    for path in files:
        try:
            _validate_file(path)
            data = load_schema_dict(path)
            print(
                f"{data['id']:<30} {data['name']:<40} "
                f"{data.get('status', 'draft'):<10} v{data.get('version', 1)}"
            )
        except SchemaValidationError as exc:
            exit_code = 1
            print(f"{path.name:<30} INVALID: {'; '.join(str(i) for i in exc.issues)}")
    return exit_code


def _find_schema_path(schema_id_or_path: str, directory: Path) -> Path:
    candidate = Path(schema_id_or_path)
    if candidate.suffix in (".yaml", ".yml") and candidate.is_file():
        return candidate
    for path in find_schema_files(directory):
        if load_schema_dict(path).get("id") == schema_id_or_path:
            return path
    raise FileNotFoundError(f"No schema with id '{schema_id_or_path}' found in {directory}")


def cmd_generate(args: argparse.Namespace) -> int:
    directory = Path(args.dir) if args.dir else schemas_dir()
    try:
        schema_path = _find_schema_path(args.schema, directory)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    data = load_schema_dict(schema_path)
    templates_dir, prepare_dir = project_dirs_for(schema_path)
    try:
        validate_schema(data, templates_dir=templates_dir, prepare_dir=prepare_dir)
    except SchemaValidationError as exc:
        print(f"FAILED: {schema_path}", file=sys.stderr)
        for issue in exc.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    schema = schema_from_dict(data, source_path=schema_path)
    if schema.prepare:
        print(
            f"ERROR: schema '{schema.id}' declares a prepare hook; "
            "prepare-hook generation lands in phase 4",
            file=sys.stderr,
        )
        return 1

    raw_values = json.loads(Path(args.values).read_text(encoding="utf-8"))
    try:
        context = validate_values(schema, raw_values)
    except FieldValidationError as exc:
        print("FAILED validation:", file=sys.stderr)
        for key, message in exc.errors.items():
            print(f"  - {key}: {message}", file=sys.stderr)
        return 1

    try:
        rendered = render_documents(
            schema, context, templates_dir=templates_dir, username=args.username
        )
    except RenderError as exc:
        print(f"FAILED to render: {exc}", file=sys.stderr)
        return 1

    result = save_documents(
        rendered,
        schema,
        raw_values=raw_values,
        output_root=Path(args.output) if args.output else output_dir(),
        username=args.username,
    )
    for doc_key, path in result.document_paths.items():
        print(f"{doc_key}: {path}")
    print(f"profile: {result.profile_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="configgen", description=f"{APP_NAME} CLI")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    p_check = subparsers.add_parser("check", help="Validate a schema YAML file")
    p_check.add_argument("schema", help="Path to the schema YAML file")
    p_check.set_defaults(func=cmd_check)

    p_list = subparsers.add_parser("list", help="List schemas in a directory")
    p_list.add_argument("--dir", help="Schemas directory (default: resources/schemas)")
    p_list.set_defaults(func=cmd_list)

    p_generate = subparsers.add_parser("generate", help="Generate a config from a schema")
    p_generate.add_argument("schema", help="Schema id or path to its YAML file")
    p_generate.add_argument("--dir", help="Schemas directory (default: resources/schemas)")
    p_generate.add_argument("--values", required=True, help="Path to a JSON file of form values")
    p_generate.add_argument("--output", help="Output root directory (default: ./output)")
    p_generate.add_argument("--username", default="unknown", help="Username recorded in the output")
    p_generate.set_defaults(func=cmd_generate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
