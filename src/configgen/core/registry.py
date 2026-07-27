"""Plugin & extension registry (§12 of the build plan): what a project has
supplied — prepare hooks, custom Jinja filters, and preflight checkers —
and whether every schema's `prepare:`/`preflight:` reference actually
resolves to one of them (or, for preflight, to a built-in).

Auto-discovery only; nothing here runs a hook or a check for real (though
loading `filters.py` and a preflight checker means executing that file,
the same trust model prepare hooks and custom checks already use
elsewhere). It just finds what's on disk and cross-references it against
the schemas and templates that use it, so a typo in `prepare: my_hokk` is
caught before someone hits Generate.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, nodes

from configgen.core.preflight import BUILTIN_CHECKS, load_custom_check
from configgen.core.schema import find_schema_files, load_schema_dict


@dataclass
class Plugin:
    name: str
    kind: str  # "hook" | "filter" | "preflight"
    source: Path


@dataclass
class Registry:
    hooks: dict[str, Path] = field(default_factory=dict)
    filters: dict[str, Path] = field(default_factory=dict)
    preflight: dict[str, Path] = field(default_factory=dict)

    def plugins(self) -> list[Plugin]:
        items = [Plugin(name, "hook", path) for name, path in self.hooks.items()]
        items += [Plugin(name, "filter", path) for name, path in self.filters.items()]
        items += [Plugin(name, "preflight", path) for name, path in self.preflight.items()]
        return sorted(items, key=lambda p: (p.kind, p.name))


@dataclass
class ReferenceIssue:
    schema_id: str
    field: str  # "prepare" | "preflight"
    value: str
    message: str


def discover_hooks(prepare_dir: str | Path) -> dict[str, Path]:
    prepare_dir = Path(prepare_dir)
    if not prepare_dir.is_dir():
        return {}
    return {p.stem: p for p in sorted(prepare_dir.glob("*.py")) if p.stem != "__init__"}


def discover_preflight_checks(preflight_dir: str | Path) -> dict[str, Path]:
    preflight_dir = Path(preflight_dir)
    if not preflight_dir.is_dir():
        return {}
    return {
        p.stem: p
        for p in sorted(preflight_dir.glob("*.py"))
        if load_custom_check(preflight_dir, p.stem) is not None
    }


def load_project_filters(project_root: str | Path) -> dict[str, Callable]:
    """Executes the project's `filters.py` (if present) and returns its
    `FILTERS` dict of actual callables — what `render_documents` needs to
    make them usable in a template. A project with no filters.py has no
    custom filters; that's not an error."""
    filters_path = Path(project_root) / "filters.py"
    if not filters_path.is_file():
        return {}
    spec = importlib.util.spec_from_file_location("configgen_project_filters", filters_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(getattr(module, "FILTERS", None) or {})


def discover_filters(project_root: str | Path) -> dict[str, Path]:
    project_root = Path(project_root)
    filters_path = project_root / "filters.py"
    return {name: filters_path for name in load_project_filters(project_root)}


def build_registry(project_root: str | Path) -> Registry:
    project_root = Path(project_root)
    return Registry(
        hooks=discover_hooks(project_root / "prepare"),
        filters=discover_filters(project_root),
        preflight=discover_preflight_checks(project_root / "preflight"),
    )


def check_references(registry: Registry, schemas_dir: str | Path) -> list[ReferenceIssue]:
    """Every schema's `prepare:`/`preflight:` must resolve to something
    real — a discovered hook/checker, or (for preflight only) a built-in
    platform."""
    issues: list[ReferenceIssue] = []
    for path in find_schema_files(schemas_dir):
        data = load_schema_dict(path)
        schema_id = data.get("id", path.stem)

        prepare = data.get("prepare")
        if prepare and prepare not in registry.hooks:
            issues.append(
                ReferenceIssue(schema_id, "prepare", prepare, f"no hook found for '{prepare}'")
            )

        preflight = data.get("preflight")
        if preflight and preflight not in registry.preflight and preflight not in BUILTIN_CHECKS:
            issues.append(
                ReferenceIssue(
                    schema_id,
                    "preflight",
                    preflight,
                    f"no built-in or custom check found for '{preflight}'",
                )
            )
    return issues


def _filters_used_in_template(template_path: Path) -> set[str]:
    source = template_path.read_text(encoding="utf-8")
    ast = Environment().parse(source)
    return {node.name for node in ast.find_all(nodes.Filter)}


def find_orphaned_plugins(
    registry: Registry, schemas_dir: str | Path, templates_dir: str | Path
) -> list[Plugin]:
    """Plugins that exist on disk but nothing references: a hook/preflight
    check no schema names, or a filter no template applies."""
    referenced_hooks: set[str] = set()
    referenced_preflight: set[str] = set()
    for path in find_schema_files(schemas_dir):
        data = load_schema_dict(path)
        if data.get("prepare"):
            referenced_hooks.add(data["prepare"])
        if data.get("preflight"):
            referenced_preflight.add(data["preflight"])

    used_filters: set[str] = set()
    templates_dir = Path(templates_dir)
    if templates_dir.is_dir():
        for template_path in templates_dir.glob("*.j2"):
            used_filters |= _filters_used_in_template(template_path)

    orphans = [
        Plugin(name, "hook", path)
        for name, path in registry.hooks.items()
        if name not in referenced_hooks
    ]
    orphans += [
        Plugin(name, "preflight", path)
        for name, path in registry.preflight.items()
        if name not in referenced_preflight
    ]
    orphans += [
        Plugin(name, "filter", path)
        for name, path in registry.filters.items()
        if name not in used_filters
    ]
    return sorted(orphans, key=lambda p: (p.kind, p.name))
