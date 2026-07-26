"""A read-only, project-agnostic SQLite reader (§5 of the build plan).

The core knows nothing about any particular table or schema. A project
supplies its own `queries.yaml` naming SQL statements; `from_db:` in a
schema field and `services.db.query(...)` in a prepare hook both resolve
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

_PARAM_RE = re.compile(r":(\w+)")


class DatabaseError(Exception):
    pass


@dataclass
class QueryDef:
    name: str
    sql: str
    returns: str  # "scalar_list" | "row" | "rows"


def load_queries(queries_path: str | Path) -> tuple[Path, dict[str, QueryDef]]:
    """Reads a project's queries.yaml. The database path inside it is
    resolved relative to queries.yaml's own directory."""
    queries_path = Path(queries_path)
    try:
        data = yaml.safe_load(queries_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise DatabaseError(f"could not read {queries_path}: {exc}") from exc

    if "database" not in data:
        raise DatabaseError(f"{queries_path} is missing a top-level 'database' key")

    db_path = queries_path.parent / data["database"]
    queries = {
        name: QueryDef(name=name, sql=q["sql"], returns=q.get("returns", "rows"))
        for name, q in (data.get("queries") or {}).items()
    }
    return db_path, queries


class Database:
    def __init__(self, db_path: str | Path, queries: dict[str, QueryDef]):
        self.db_path = Path(db_path)
        self.queries = queries

    @classmethod
    def from_queries_file(cls, queries_path: str | Path) -> Database:
        db_path, queries = load_queries(queries_path)
        return cls(db_path, queries)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise DatabaseError(f"database file not found: {self.db_path}")
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, query_name: str, /, **params: object) -> object:
        # query_name is positional-only so it can never collide with a bind
        # parameter of the same name — and SQL params are routinely called
        # `name` (see the `device` query below), so this isn't hypothetical.
        if query_name not in self.queries:
            raise DatabaseError(f"unknown query '{query_name}'")
        query_def = self.queries[query_name]
        conn = self._connect()
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

    A prepare hook that calls `services.db.query(...)` unconditionally would
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
