"""Parses a Jinja2 template's AST to find the top-level variables it expects.

This is what separates ConfigGen from raw Jinja2 CLI usage (§3 of the build
plan): a template author gets mismatch warnings before Generate, and a
schema can be scaffolded straight from a template that's already written.

Extraction only sees top-level names — `{{ cfg.hostname }}` is seen as
`cfg`, never `cfg.hostname` — so it cannot trace through a prepare hook
that returns a dict of subkeys. That makes mismatch detection advisory for
hook-driven schemas, never blocking (§3.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, nodes

_LOOP_VARIABLE = "loop"  # implicitly in scope inside {% for %}, never external


def extract_variables(source: str) -> list[str]:
    """Returns the sorted, deduplicated top-level variable names a template
    references — covering `{{ var }}`, `{% for x in var %}`, `{% if var %}`,
    and dotted access. Names the template assigns itself (`{% set %}`, loop
    targets, macro parameters) are not external inputs, so they're excluded."""
    env = Environment()
    ast = env.parse(source)

    loaded: set[str] = set()
    locally_bound: set[str] = set()
    for name_node in ast.find_all(nodes.Name):
        if name_node.ctx == "load":
            loaded.add(name_node.name)
        else:  # "store" (set / for-target) or "param" (macro argument)
            locally_bound.add(name_node.name)

    excluded = set(env.globals) | locally_bound | {_LOOP_VARIABLE}
    return sorted(loaded - excluded)


def extract_variables_from_file(template_path: str | Path) -> list[str]:
    source = Path(template_path).read_text(encoding="utf-8")
    return extract_variables(source)


@dataclass
class VariableStatus:
    name: str
    source: str  # "field" | "hook" | "missing"


def classify_variables(
    variables: list[str],
    field_keys: set[str],
    *,
    has_prepare_hook: bool,
) -> list[VariableStatus]:
    """One entry per template variable: "field" if a schema field provides
    it, "hook" if we can't rule out the prepare hook providing it (schema
    declares one, so this is a guess, not a fact), else "missing"."""
    statuses = []
    for name in variables:
        if name in field_keys:
            source = "field"
        elif has_prepare_hook:
            source = "hook"
        else:
            source = "missing"
        statuses.append(VariableStatus(name=name, source=source))
    return statuses


def guess_field_type(name: str) -> str:
    """The heuristic behind `--scaffold`: string by default, ip if the name
    contains `_ip`, int if it contains `_id` or `_number`."""
    if "_ip" in name:
        return "ip"
    if "_id" in name or "_number" in name:
        return "int"
    return "string"


def scaffold_schema(template_path: str | Path) -> dict:
    """Generates a skeleton schema dict for a template that was written
    first — one field per discovered variable, ready for the author to
    refine rather than write from scratch."""
    template_path = Path(template_path)
    variables = extract_variables_from_file(template_path)
    fields = [
        {
            "key": name,
            "label": name.replace("_", " ").title(),
            "type": guess_field_type(name),
        }
        for name in variables
    ]
    stem = template_path.stem
    return {
        "name": stem.replace("_", " ").title(),
        "id": stem,
        "version": 1,
        "status": "draft",
        "template": template_path.name,
        "fields": fields,
    }
