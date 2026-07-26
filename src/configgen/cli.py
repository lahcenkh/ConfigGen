"""Headless entry point. Subcommands land phase by phase; this phase adds
check / list / generate for form-only (no prepare hook, no DB) configs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from configgen.appinfo import APP_NAME, __version__
from configgen.core.auth import (
    ROLE_ADMIN,
    ROLES,
    AuthError,
    AuthStore,
    User,
    require_role,
    visible_schemas,
)
from configgen.core.db import Database, DatabaseError, health_check, load_queries
from configgen.core.exporter import save_documents
from configgen.core.extractor import (
    classify_variables,
    extract_variables_from_file,
    scaffold_schema,
)
from configgen.core.renderer import RenderError, render_documents
from configgen.core.schema import (
    Schema,
    find_schema_files,
    load_schema_dict,
    project_data_dir_for,
    project_dirs_for,
    schema_from_dict,
)
from configgen.core.schema_validator import SchemaValidationError, validate_schema
from configgen.core.validators import FieldValidationError, validate_values
from configgen.paths import data_dir, output_dir, schemas_dir, users_db_path
from configgen.prepare import PrepareError, Services, run_prepare_hook


def _auth_store_for(args: argparse.Namespace) -> AuthStore:
    db_path = Path(args.users_db) if getattr(args, "users_db", None) else users_db_path()
    return AuthStore(db_path)


def _authenticate_optional(args: argparse.Namespace, store: AuthStore) -> User | None:
    """For `list`/`generate`: --username alone is just a label (back-compat,
    solo-mode-friendly); adding --password or --api-key upgrades it to real
    authentication and role/group enforcement."""
    api_key = getattr(args, "api_key", None)
    password = getattr(args, "password", None)
    username = getattr(args, "username", None)
    if api_key:
        return store.verify_api_key(api_key)
    if password:
        if not username:
            raise AuthError("--username is required together with --password")
        return store.authenticate(username, password)
    return None


def _authenticate_actor(args: argparse.Namespace, store: AuthStore) -> User:
    """For user/group/apikey/log management: the caller's own identity is
    mandatory — there's no unauthenticated fallback for these."""
    if getattr(args, "as_api_key", None):
        return store.verify_api_key(args.as_api_key)
    if getattr(args, "as_username", None) and getattr(args, "as_password", None):
        return store.authenticate(args.as_username, args.as_password)
    raise AuthError(
        "authentication required: pass --as-api-key, or --as-username with --as-password"
    )


def _known_queries_for(schema_path: Path) -> set[str] | None:
    """None if queries.yaml doesn't exist (skip the from_db check — can't
    verify what we can't see); a set of names if it does."""
    queries_path = project_data_dir_for(schema_path) / "queries.yaml"
    if not queries_path.is_file():
        return None
    _, queries = load_queries(queries_path)
    return set(queries)


def _database_for(schema: Schema, schema_path: Path) -> Database | None:
    """None if the schema has no from_db fields; raises DatabaseError with a
    clean message (§5.3) if it does but queries.yaml isn't there."""
    if not any(f.from_db for f in schema.fields):
        return None
    queries_path = project_data_dir_for(schema_path) / "queries.yaml"
    if not queries_path.is_file():
        raise DatabaseError(
            f"schema '{schema.id}' has fields sourced from a database, "
            f"but no queries.yaml found at {queries_path}"
        )
    return Database.from_queries_file(queries_path)


def _services_for(schema_path: Path) -> Services:
    """Builds the Services a prepare hook runs with. `db` is a real Database
    if the project has a queries.yaml, else Services falls back to a
    NoDatabase that raises cleanly only if the hook actually tries to use
    it — a hook that doesn't touch `services.db` works with no db at all."""
    queries_path = project_data_dir_for(schema_path) / "queries.yaml"
    db = Database.from_queries_file(queries_path) if queries_path.is_file() else None
    return Services(db=db)


def _validate_file(schema_path: Path) -> None:
    data = load_schema_dict(schema_path)
    templates_dir, prepare_dir = project_dirs_for(schema_path)
    validate_schema(
        data,
        templates_dir=templates_dir,
        prepare_dir=prepare_dir,
        known_queries=_known_queries_for(schema_path),
    )


def _mismatch_warnings(schema: Schema, templates_dir: Path) -> list[str]:
    """Template variables with no declared source. Advisory only — see
    core/extractor.py for why this can never be a hard failure when a
    prepare hook is involved."""
    field_keys = set(schema.field_map())
    warnings: list[str] = []
    for doc in schema.document_list():
        variables = extract_variables_from_file(templates_dir / doc.template)
        for status in classify_variables(
            variables, field_keys, has_prepare_hook=bool(schema.prepare)
        ):
            if status.source == "missing":
                warnings.append(f"{doc.key}: '{status.name}' has no schema field or hook")
    return warnings


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

    schema = schema_from_dict(data, source_path=schema_path)
    templates_dir, _ = project_dirs_for(schema_path)
    for warning in _mismatch_warnings(schema, templates_dir):
        print(f"WARNING: {warning}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    directory = Path(args.dir) if args.dir else schemas_dir()
    files = find_schema_files(directory)
    if not files:
        print(f"No schemas found in {directory}")
        return 0

    # Only touch users.db (which bootstraps admin/admin on first open) when
    # the caller actually asked to authenticate — a plain `list` must never
    # have that side effect.
    user = None
    user_groups: set[str] = set()
    if getattr(args, "api_key", None) or getattr(args, "password", None):
        store = _auth_store_for(args)
        try:
            user = _authenticate_optional(args, store)
        except AuthError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        user_groups = store.groups_for_user(user.username) if user else set()

    exit_code = 0
    for path in files:
        try:
            _validate_file(path)
            data = load_schema_dict(path)
            schema = schema_from_dict(data, source_path=path)
            if user and not visible_schemas(user, [schema], user_groups):
                continue
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
        validate_schema(
            data,
            templates_dir=templates_dir,
            prepare_dir=prepare_dir,
            known_queries=_known_queries_for(schema_path),
        )
    except SchemaValidationError as exc:
        print(f"FAILED: {schema_path}", file=sys.stderr)
        for issue in exc.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    schema = schema_from_dict(data, source_path=schema_path)

    # Only touch users.db (which bootstraps admin/admin on first open) when
    # the caller actually asked to authenticate — a plain --username label
    # must never have that side effect (§13.8: solo mode stays frictionless).
    store = None
    user = None
    if getattr(args, "api_key", None) or getattr(args, "password", None):
        store = _auth_store_for(args)
        try:
            user = _authenticate_optional(args, store)
        except AuthError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        user_groups = store.groups_for_user(user.username)
        if not visible_schemas(user, [schema], user_groups):
            print(
                f"ERROR: user '{user.username}' ({user.role}) cannot access "
                f"schema '{schema.id}' (wrong group or status)",
                file=sys.stderr,
            )
            return 1
    effective_username = user.username if user else args.username

    try:
        database = _database_for(schema, schema_path)
    except DatabaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    raw_values = json.loads(Path(args.values).read_text(encoding="utf-8"))
    try:
        values = validate_values(schema, raw_values, database=database)
    except FieldValidationError as exc:
        print("FAILED validation:", file=sys.stderr)
        for key, message in exc.errors.items():
            print(f"  - {key}: {message}", file=sys.stderr)
        return 1
    except DatabaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if schema.prepare:
        hook_context = {
            "username": effective_username,
            "schema_id": schema.id,
            "schema_version": schema.version,
        }
        try:
            context = run_prepare_hook(
                prepare_dir, schema.prepare, values, hook_context, _services_for(schema_path)
            )
        except PrepareError as exc:
            print("FAILED prepare hook:", file=sys.stderr)
            for key, message in exc.errors.items():
                print(f"  - {key}: {message}", file=sys.stderr)
            return 1
        except DatabaseError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    else:
        context = values

    try:
        rendered = render_documents(
            schema, context, templates_dir=templates_dir, username=effective_username
        )
    except RenderError as exc:
        print(f"FAILED to render: {exc}", file=sys.stderr)
        return 1

    result = save_documents(
        rendered,
        schema,
        raw_values=raw_values,
        output_root=Path(args.output) if args.output else output_dir(),
        username=effective_username,
    )
    if user is not None:
        for path in result.document_paths.values():
            store.record_generation(
                user,
                schema_id=schema.id,
                schema_version=schema.version,
                form_inputs=raw_values,
                output_filename=path.name,
                group_name=schema.group,
            )
    for doc_key, path in result.document_paths.items():
        print(f"{doc_key}: {path}")
    print(f"profile: {result.profile_path}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    template_path = Path(args.template)
    variables = extract_variables_from_file(template_path)

    if args.scaffold:
        print(yaml.dump(scaffold_schema(template_path), sort_keys=False))
        return 0

    if args.check:
        data = load_schema_dict(args.check)
        schema = schema_from_dict(data, source_path=args.check)
        field_keys = set(schema.field_map())
        exit_code = 0
        for status in classify_variables(
            variables, field_keys, has_prepare_hook=bool(schema.prepare)
        ):
            label = {"field": "OK", "hook": "HOOK", "missing": "MISSING"}[status.source]
            print(f"{status.name}: {label}")
            if status.source == "missing":
                exit_code = 1
        return exit_code

    for name in variables:
        print(name)
    return 0


def cmd_db_check(args: argparse.Namespace) -> int:
    queries_path = Path(args.queries) if args.queries else (data_dir() / "queries.yaml")
    if not queries_path.is_file():
        print(f"ERROR: queries.yaml not found at {queries_path}", file=sys.stderr)
        return 1

    database = Database.from_queries_file(queries_path)
    exit_code = 0
    for result in health_check(database):
        status = "OK" if result.ok else "FAIL"
        line = f"{result.name}: {status}"
        if not result.ok:
            line += f" ({result.message})"
            exit_code = 1
        print(line)
    return exit_code


def cmd_user_create(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
        user = store.create_user(
            args.new_username,
            args.new_password,
            args.role,
            first_name=args.first_name,
            last_name=args.last_name,
            company_name=args.company,
        )
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"created user '{user.username}' ({user.role})")
    return 0


def cmd_user_list(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for user in store.list_users():
        print(
            f"{user.username:<20} {user.role:<20} "
            f"force_password_change={user.force_password_change}"
        )
    return 0


def cmd_user_passwd(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        if not actor.is_admin and actor.username != args.target_username:
            print(
                f"ERROR: user '{actor.username}' may not change another user's password",
                file=sys.stderr,
            )
            return 1
        store.change_password(args.target_username, args.new_password)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"password updated for '{args.target_username}'")
    return 0


def cmd_group_create(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
        group = store.create_group(args.name, description=args.description)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"created group '{group.name}'")
    return 0


def cmd_group_assign(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
        store.assign_user_to_group(
            args.target_username, args.group_name, assigned_by=actor.username
        )
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"assigned '{args.target_username}' to group '{args.group_name}'")
    return 0


def cmd_group_list(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for group in store.list_groups():
        print(f"{group.name} ({group.description or ''})")
    return 0


def cmd_apikey_create(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
        raw_key = store.create_api_key(args.target_username, label=args.label)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(raw_key)
    return 0


def cmd_apikey_revoke(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
        store.revoke_api_key(args.key_id)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"revoked API key {args.key_id}")
    return 0


def cmd_apikey_list(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
        require_role(actor, ROLE_ADMIN)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for key in store.list_api_keys(args.target_username):
        status = "revoked" if key["revoked_at"] else "active"
        print(f"{key['id']:<5} user_id={key['user_id']:<5} {status:<8} {key['label'] or ''}")
    return 0


def cmd_log_list(args: argparse.Namespace) -> int:
    store = _auth_store_for(args)
    try:
        actor = _authenticate_actor(args, store)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for entry in store.list_generation_log(actor):
        print(
            f"{entry['created_at']} {entry['username']:<15} {entry['schema_id']}"
            f" v{entry['schema_version']} -> {entry['output_filename']}"
        )
    return 0


def _print_help(parser: argparse.ArgumentParser) -> int:
    parser.print_help()
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
    p_list.add_argument(
        "--username", help="Authenticate and scope results to this user's role/groups"
    )
    p_list.add_argument("--password", help="Password (with --username) to authenticate")
    p_list.add_argument(
        "--api-key", help="API key to authenticate with instead of --username/--password"
    )
    p_list.add_argument("--users-db", help="Path to users.db (default: users.db in the app root)")
    p_list.set_defaults(func=cmd_list)

    p_generate = subparsers.add_parser("generate", help="Generate a config from a schema")
    p_generate.add_argument("schema", help="Schema id or path to its YAML file")
    p_generate.add_argument("--dir", help="Schemas directory (default: resources/schemas)")
    p_generate.add_argument("--values", required=True, help="Path to a JSON file of form values")
    p_generate.add_argument("--output", help="Output root directory (default: ./output)")
    p_generate.add_argument(
        "--username",
        default="unknown",
        help="Username recorded in the output; add --password or --api-key to "
        "authenticate for real and enforce role/group access + logging",
    )
    p_generate.add_argument("--password", help="Password (with --username) to authenticate")
    p_generate.add_argument(
        "--api-key", help="API key to authenticate with instead of --username/--password"
    )
    p_generate.add_argument(
        "--users-db", help="Path to users.db (default: users.db in the app root)"
    )
    p_generate.set_defaults(func=cmd_generate)

    p_extract = subparsers.add_parser("extract", help="List a template's variables")
    p_extract.add_argument("template", help="Path to a Jinja2 template file")
    p_extract.add_argument(
        "--scaffold", action="store_true", help="Print a skeleton schema YAML instead"
    )
    p_extract.add_argument("--check", help="Report mismatches against this schema YAML")
    p_extract.set_defaults(func=cmd_extract)

    p_db = subparsers.add_parser("db", help="Database utilities")
    p_db.set_defaults(func=lambda a, _p=p_db: _print_help(_p))
    db_subparsers = p_db.add_subparsers(dest="db_command")
    p_db_check = db_subparsers.add_parser(
        "check", help="Run every named query in queries.yaml with null parameters"
    )
    p_db_check.add_argument(
        "--queries", help="Path to queries.yaml (default: resources/data/queries.yaml)"
    )
    p_db_check.set_defaults(func=cmd_db_check)

    def _add_actor_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--as-username", help="Acting user's username")
        p.add_argument("--as-password", help="Acting user's password")
        p.add_argument(
            "--as-api-key", help="Acting user's API key (instead of --as-username/--as-password)"
        )
        p.add_argument("--users-db", help="Path to users.db (default: users.db in the app root)")

    p_user = subparsers.add_parser("user", help="User management (Admin only)")
    p_user.set_defaults(func=lambda a, _p=p_user: _print_help(_p))
    user_subparsers = p_user.add_subparsers(dest="user_command")

    p_user_create = user_subparsers.add_parser("create", help="Create a user")
    p_user_create.add_argument("new_username", help="Username for the new user")
    p_user_create.add_argument("new_password", help="Password for the new user")
    p_user_create.add_argument("--role", required=True, choices=sorted(ROLES))
    p_user_create.add_argument("--first-name")
    p_user_create.add_argument("--last-name")
    p_user_create.add_argument("--company")
    _add_actor_args(p_user_create)
    p_user_create.set_defaults(func=cmd_user_create)

    p_user_list = user_subparsers.add_parser("list", help="List users")
    _add_actor_args(p_user_list)
    p_user_list.set_defaults(func=cmd_user_list)

    p_user_passwd = user_subparsers.add_parser("passwd", help="Change a user's password")
    p_user_passwd.add_argument("target_username")
    p_user_passwd.add_argument("new_password")
    _add_actor_args(p_user_passwd)
    p_user_passwd.set_defaults(func=cmd_user_passwd)

    p_group = subparsers.add_parser("group", help="Group management (Admin only)")
    p_group.set_defaults(func=lambda a, _p=p_group: _print_help(_p))
    group_subparsers = p_group.add_subparsers(dest="group_command")

    p_group_create = group_subparsers.add_parser("create", help="Create a group")
    p_group_create.add_argument("name")
    p_group_create.add_argument("--description")
    _add_actor_args(p_group_create)
    p_group_create.set_defaults(func=cmd_group_create)

    p_group_assign = group_subparsers.add_parser("assign", help="Assign a user to a group")
    p_group_assign.add_argument("target_username")
    p_group_assign.add_argument("group_name")
    _add_actor_args(p_group_assign)
    p_group_assign.set_defaults(func=cmd_group_assign)

    p_group_list = group_subparsers.add_parser("list", help="List groups")
    _add_actor_args(p_group_list)
    p_group_list.set_defaults(func=cmd_group_list)

    p_apikey = subparsers.add_parser("apikey", help="API key management (Admin only)")
    p_apikey.set_defaults(func=lambda a, _p=p_apikey: _print_help(_p))
    apikey_subparsers = p_apikey.add_subparsers(dest="apikey_command")

    p_apikey_create = apikey_subparsers.add_parser("create", help="Create an API key for a user")
    p_apikey_create.add_argument("target_username")
    p_apikey_create.add_argument("--label")
    _add_actor_args(p_apikey_create)
    p_apikey_create.set_defaults(func=cmd_apikey_create)

    p_apikey_revoke = apikey_subparsers.add_parser("revoke", help="Revoke an API key")
    p_apikey_revoke.add_argument("key_id", type=int)
    _add_actor_args(p_apikey_revoke)
    p_apikey_revoke.set_defaults(func=cmd_apikey_revoke)

    p_apikey_list = apikey_subparsers.add_parser("list", help="List API keys")
    p_apikey_list.add_argument("target_username", nargs="?", default=None)
    _add_actor_args(p_apikey_list)
    p_apikey_list.set_defaults(func=cmd_apikey_list)

    p_log = subparsers.add_parser("log", help="Generation log")
    p_log.set_defaults(func=lambda a, _p=p_log: _print_help(_p))
    log_subparsers = p_log.add_subparsers(dest="log_command")

    p_log_list = log_subparsers.add_parser(
        "list", help="List generation log entries visible to you"
    )
    _add_actor_args(p_log_list)
    p_log_list.set_defaults(func=cmd_log_list)

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
