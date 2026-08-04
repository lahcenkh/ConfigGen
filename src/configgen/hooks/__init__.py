"""Tier 2 of the two-tier engine (§6 of the build plan): the hook
contract, the Services a hook receives, and the loader that turns
`hook: <name>` in a schema into a call to `hooks/<name>.py`'s `build()`.

A hook is one file per DB-backed or derived config, living in the project's
own `hooks/` folder (a sibling of `schemas/`, `templates/`, and `data/` —
see `core.schema.project_dirs_for`), not inside the installed package. It's
loaded from that file path at call time, the same way templates are loaded
from `templates/` at render time — nothing about a project's own hooks is
baked into the core.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path

from configgen.core.db import Database, NoDatabase
from configgen.core.schema import project_data_dir_for
from configgen.core.values import NetworkValue


class HookError(Exception):
    """Raised by a hook with `{field_key: message}` to reject a submission —
    surfaced the same way a Tier 1 FieldValidationError is."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


class NetService:
    """Stateless subnet/address helpers for hooks — the generalized,
    de-telecom'd version of the private build's arithmetic functions.
    Thin wrappers around core.values.NetworkValue so a hook can pass a
    plain string (or an already-typed NetworkValue) without parsing it
    itself."""

    @staticmethod
    def host_at(network: str, offset: int) -> str:
        return NetworkValue(str(network)).host_at(offset)

    @staticmethod
    def first_usable(network: str) -> str:
        return NetworkValue(str(network)).first_usable

    @staticmethod
    def nexthop(network: str) -> str:
        return NetworkValue(str(network)).nexthop

    @staticmethod
    def netmask(network: str) -> str:
        return NetworkValue(str(network)).netmask

    @staticmethod
    def prefix(network: str) -> int:
        return NetworkValue(str(network)).prefix


class Services:
    """What a hook gets besides the form values: `db` (the generic
    reader, or a NoDatabase stand-in if the project has none configured),
    `net` (subnet/address helpers), and any project-registered extras."""

    def __init__(self, db: Database | NoDatabase | None = None, **extra: object):
        self.db = db if db is not None else NoDatabase()
        self.net = NetService()
        for key, value in extra.items():
            setattr(self, key, value)


def services_for_schema(schema_path: str | Path) -> Services:
    """Builds the Services a hook runs with, given only a schema's
    path: `db` is a real Database if the project has a queries.yaml, else
    Services falls back to NoDatabase (clean error only if the hook
    actually touches `services.db`). Shared by the CLI and the GUI
    generator view, so both build a hook's Services the same way."""
    queries_path = project_data_dir_for(schema_path) / "queries.yaml"
    db = Database.from_queries_file(queries_path) if queries_path.is_file() else None
    return Services(db=db)


def load_hook(hooks_dir: str | Path, name: str) -> Callable[[dict, dict, Services], dict]:
    """Dynamically imports `<hooks_dir>/<name>.py` and returns its
    `build` function. Raises HookError (not ImportError/AttributeError)
    so a missing or malformed hook fails the same clean way as a rejected
    submission — schema_validator's own `hook:` check is what normally
    catches this before it ever gets here."""
    module_path = Path(hooks_dir) / f"{name}.py"
    if not module_path.is_file():
        raise HookError({"hook": f"hook not found: {module_path}"})

    spec = importlib.util.spec_from_file_location(f"configgen_hook_{name}", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    build_fn = getattr(module, "build", None)
    if build_fn is None:
        raise HookError({"hook": f"hook '{name}' has no build() function"})
    return build_fn


def run_hook(
    hooks_dir: str | Path,
    name: str,
    values: dict,
    context: dict,
    services: Services,
) -> dict:
    """Loads and runs a hook, returning the template context it builds.
    A hook's own HookError propagates as-is; so does any other exception
    a buggy hook raises — hooks are plain Python, not sandboxed, and their
    author sees their own tracebacks unobscured (§6: "pure Python and
    unit-testable in isolation")."""
    build_fn = load_hook(hooks_dir, name)
    return build_fn(values, context, services)
