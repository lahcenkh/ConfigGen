"""A read-only, project-agnostic SQLite reader (§5 of the build plan).

The core knows nothing about any particular table or schema. A project
supplies its own `queries.yaml` naming SQL statements; `from_db:` in a
schema field and `services.db.query(...)` in a hook both resolve
through this module. Every call opens its own connection and closes it
before returning — the fix for the Windows file-lock issue (§19) — since
that's cheap for form submission and Generate calls; a session-scoped
connection for per-keystroke autocomplete is a UI-layer concern (§5.5),
not this module's.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from configgen.core.schema import Schema, project_data_dir_for

_PARAM_RE = re.compile(r":(\w+)")

# The alias a legacy single-`database:` queries.yaml is filed under
# internally, so every query has a `use:` to resolve regardless of which
# top-level form the file used. Never seen by a queries.yaml author.
_SINGLE_DB_ALIAS = "default"


class DatabaseError(Exception):
    pass


@dataclass
class QueryDef:
    name: str
    sql: str
    returns: str  # "scalar_list" | "row" | "rows"
    use: str  # which database alias this query runs against


def load_queries(queries_path: str | Path) -> tuple[dict[str, Path], dict[str, QueryDef]]:
    """Reads a project's queries.yaml. Database paths inside it are
    resolved relative to queries.yaml's own directory.

    Supports two top-level forms: a single `database: path.db` (every
    query implicitly uses it), or a multi-database `databases: {alias:
    path.db, ...}` where each query names which one it needs via `use:`
    (required whenever more than one database is configured)."""
    queries_path = Path(queries_path)
    try:
        data = yaml.safe_load(queries_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise DatabaseError(f"could not read {queries_path}: {exc}") from exc

    if "database" in data and "databases" in data:
        raise DatabaseError(f"{queries_path} has both 'database' and 'databases' — use only one")
    if "databases" in data:
        raw_databases = data["databases"]
        if not isinstance(raw_databases, dict) or not raw_databases:
            raise DatabaseError(
                f"{queries_path} 'databases' must be a non-empty mapping of alias: path"
            )
        databases = {alias: queries_path.parent / path for alias, path in raw_databases.items()}
    elif "database" in data:
        databases = {_SINGLE_DB_ALIAS: queries_path.parent / data["database"]}
    else:
        raise DatabaseError(f"{queries_path} is missing a top-level 'database' or 'databases' key")

    queries: dict[str, QueryDef] = {}
    for name, q in (data.get("queries") or {}).items():
        use = q.get("use")
        if use is None:
            if len(databases) > 1:
                raise DatabaseError(
                    f"query '{name}' in {queries_path} must set 'use:' — "
                    f"multiple databases are configured ({', '.join(sorted(databases))})"
                )
            use = next(iter(databases))
        elif use not in databases:
            raise DatabaseError(
                f"query '{name}' in {queries_path} uses unknown database '{use}' "
                f"(configured: {', '.join(sorted(databases))})"
            )
        queries[name] = QueryDef(name=name, sql=q["sql"], returns=q.get("returns", "rows"), use=use)
    return databases, queries


class Database:
    def __init__(self, databases: dict[str, str | Path], queries: dict[str, QueryDef]):
        self.databases = {alias: Path(path) for alias, path in databases.items()}
        self.queries = queries

    @classmethod
    def from_queries_file(cls, queries_path: str | Path) -> Database:
        databases, queries = load_queries(queries_path)
        return cls(databases, queries)

    def _connect(self, alias: str) -> sqlite3.Connection:
        db_path = self.databases[alias]
        if not db_path.is_file():
            raise DatabaseError(f"database file not found: {db_path}")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, query_name: str, /, **params: object) -> object:
        # query_name is positional-only so it can never collide with a bind
        # parameter of the same name — and SQL params are routinely called
        # `name` (see the `device` query below), so this isn't hypothetical.
        if query_name not in self.queries:
            raise DatabaseError(f"unknown query '{query_name}'")
        query_def = self.queries[query_name]
        conn = self._connect(query_def.use)
        try:
            rows = conn.execute(query_def.sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"query '{query_name}' failed: {exc}") from exc
        finally:
            conn.close()
        return _shape(query_def.returns, rows)

    def all(self, query_name: str, /) -> object:
        """Runs a named query with no parameters — the common case for
        populating a `choice`/`lookup` field's options from the database."""
        return self.query(query_name)


class NoDatabase:
    """Stands in for `Services.db` when a project has no queries.yaml.

    A hook that calls `services.db.query(...)` unconditionally would
    otherwise hit an AttributeError on `None` — this raises the same
    DatabaseError a real Database would for an unreachable file, so the
    error a hook author sees is always the same shape."""

    def query(self, query_name: str, /, **params: object) -> object:
        raise DatabaseError("no database configured for this project (queries.yaml not found)")

    def all(self, query_name: str, /) -> object:
        raise DatabaseError("no database configured for this project (queries.yaml not found)")


def _shape(returns: str, rows: list[sqlite3.Row]) -> object:
    if returns == "scalar_list":
        return [row[0] for row in rows]
    if returns == "row":
        return dict(rows[0]) if rows else None
    if returns == "rows":
        return [dict(row) for row in rows]
    raise DatabaseError(f"unknown 'returns' type: '{returns}'")


@dataclass
class HealthCheckResult:
    name: str
    ok: bool
    message: str = ""


def health_check(database: Database) -> list[HealthCheckResult]:
    """Runs every named query with null parameters and reports which
    succeed and which fail — catches schema drift between queries.yaml
    and the database it points at."""
    results = []
    for query_name, query_def in database.queries.items():
        params = dict.fromkeys(_PARAM_RE.findall(query_def.sql))
        try:
            database.query(query_name, **params)
            results.append(HealthCheckResult(name=query_name, ok=True))
        except DatabaseError as exc:
            results.append(HealthCheckResult(name=query_name, ok=False, message=str(exc)))
    return results


def known_queries_for_schema(schema_path: str | Path) -> set[str] | None:
    """The query names a project's queries.yaml declares — None if it
    doesn't exist (can't verify a from_db reference against a file that
    isn't there, so schema_validator skips that check rather than failing
    it). Shared by the CLI's schema validation and the GUI template editor."""
    queries_path = project_data_dir_for(schema_path) / "queries.yaml"
    if not queries_path.is_file():
        return None
    _, queries = load_queries(queries_path)
    return set(queries)


def database_for_schema(schema: Schema, schema_path: str | Path) -> Database | None:
    """None if the schema has no from_db fields; raises DatabaseError with a
    clean message (§5.3) if it does but queries.yaml isn't there. Shared by
    the CLI (generate/bulk) and the GUI generator view, so both resolve a
    schema's database the same way."""
    if not any(f.from_db for f in schema.fields):
        return None
    queries_path = project_data_dir_for(schema_path) / "queries.yaml"
    if not queries_path.is_file():
        raise DatabaseError(
            f"schema '{schema.id}' has fields sourced from a database, "
            f"but no queries.yaml found at {queries_path}"
        )
    return Database.from_queries_file(queries_path)
