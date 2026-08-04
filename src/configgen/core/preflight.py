"""Optional syntax pre-checks on rendered output before saving (§11 of the
build plan).

A schema opts in via `preflight: ios` (or `junos`/`sros`/`vrp`/`generic`,
or any platform name a project supplies its own checker for). After
rendering, the preflight runner scans the output text and returns warning
messages — advisory only, never blocking Generate — flagging that
platform's most common syntax mistakes before the user saves.

`ios`/`junos`/`generic` check exactly what §11.2 specifies. §11.2 doesn't
spell out checks for `sros` (Nokia SR OS) or `vrp` (Huawei VRP8) beyond
naming them, so those two are a judgment call: `sros` mirrors junos's
brace-balance idea using SR OS's own block/`exit` convention instead of
braces; `vrp` reuses ios's checks near-verbatim since VRP's CLI syntax is
itself modeled closely on Cisco IOS, except a VRP interface context is
closed with `quit`, not `end`.
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable
from pathlib import Path

CheckFn = Callable[[str], list[str]]

_IOS_INTERFACE_RE = re.compile(r"^[A-Za-z]+[A-Za-z0-9]*\d+(?:/\d+)*$")
_IOS_INTERFACE_LINE_RE = re.compile(r"(?m)^interface\s+(\S+)")
_IOS_END_LINE_RE = re.compile(r"(?m)^end\s*$")
_IOS_VLAN_LINE_RE = re.compile(r"(?mi)^\s*vlan\s+(\d+)\b")


def check_ios(text: str) -> list[str]:
    """Matching interface/end blocks, valid interface names, VLAN range
    1-4094 (§11.2)."""
    warnings: list[str] = []
    interface_names = _IOS_INTERFACE_LINE_RE.findall(text)

    if interface_names and not _IOS_END_LINE_RE.search(text):
        warnings.append("found 'interface' block(s) but no closing 'end' statement")

    for name in interface_names:
        if not _IOS_INTERFACE_RE.fullmatch(name):
            warnings.append(f"'{name}' does not look like a valid interface name")

    for match in _IOS_VLAN_LINE_RE.finditer(text):
        vlan_id = int(match.group(1))
        if not (1 <= vlan_id <= 4094):
            warnings.append(f"VLAN {vlan_id} is outside the valid range 1-4094")

    return warnings


def check_junos(text: str) -> list[str]:
    """Balanced braces, valid hierarchical structure (§11.2)."""
    warnings: list[str] = []
    opens, closes = text.count("{"), text.count("}")
    if opens != closes:
        warnings.append(f"unbalanced braces: {opens} '{{' vs {closes} '}}'")

    depth = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        depth += line.count("{") - line.count("}")
        if depth < 0:
            warnings.append(f"line {lineno}: closing brace with no matching open brace")
            depth = 0  # keep scanning for further, independent problems
    return warnings


_SROS_BLOCK_OPENER_RE = re.compile(r"(?m)^\s*(?:interface|router|port|service)\s+\S+")
_SROS_EXIT_RE = re.compile(r"(?m)^\s*exit(?:\s+all)?\s*$")


def check_sros(text: str) -> list[str]:
    """Nokia SR OS: block/`exit` balance — the `exit`-based equivalent of
    junos's brace balance, since SR OS closes a nested context (`router`,
    `interface`, `port`, `service`) with a lone `exit` rather than a `}`."""
    warnings: list[str] = []
    openers = _SROS_BLOCK_OPENER_RE.findall(text)
    exits = _SROS_EXIT_RE.findall(text)
    if len(openers) > len(exits):
        warnings.append(
            f"found {len(openers)} block(s) (interface/router/port/service) but only "
            f"{len(exits)} 'exit' statement(s)"
        )
    return warnings


_VRP_INTERFACE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*\d+(?:/\d+)*$")
_VRP_INTERFACE_LINE_RE = re.compile(r"(?m)^interface\s+(\S+)")
_VRP_QUIT_LINE_RE = re.compile(r"(?m)^quit\s*$")
_VRP_VLAN_LINE_RE = re.compile(r"(?mi)^\s*vlan\s+(\d+)\b")


def check_vrp(text: str) -> list[str]:
    """Huawei VRP8: matching interface/`quit` blocks, valid interface
    names, VLAN range 1-4094 — VRP's CLI mirrors Cisco IOS closely, but an
    interface context is closed with `quit`, not `end`."""
    warnings: list[str] = []
    interface_names = _VRP_INTERFACE_LINE_RE.findall(text)

    if interface_names and not _VRP_QUIT_LINE_RE.search(text):
        warnings.append("found 'interface' block(s) but no closing 'quit' statement")

    for name in interface_names:
        if not _VRP_INTERFACE_RE.fullmatch(name):
            warnings.append(f"'{name}' does not look like a valid interface name")

    for match in _VRP_VLAN_LINE_RE.finditer(text):
        vlan_id = int(match.group(1))
        if not (1 <= vlan_id <= 4094):
            warnings.append(f"VLAN {vlan_id} is outside the valid range 1-4094")

    return warnings


# A run of two blank (or whitespace-only) lines in a row is the classic
# fingerprint of a Jinja {% if %}...{% endif %} block that rendered nothing
# but left its surrounding whitespace behind — content was expected there.
_BLANK_RUN_RE = re.compile(r"\n[ \t]*\n[ \t]*\n")


def check_generic(text: str) -> list[str]:
    """No empty lines where a command was expected, no unresolved `{{ }}`
    markers (§11.2)."""
    warnings: list[str] = []
    if "{{" in text or "}}" in text:
        warnings.append("unresolved template marker ('{{' or '}}') found in rendered output")
    if _BLANK_RUN_RE.search(text):
        warnings.append("found consecutive blank lines where a command was likely expected")
    return warnings


BUILTIN_CHECKS: dict[str, CheckFn] = {
    "ios": check_ios,
    "junos": check_junos,
    "sros": check_sros,
    "vrp": check_vrp,
    "generic": check_generic,
}


def load_custom_check(preflight_dir: str | Path, platform: str) -> CheckFn | None:
    """A project's own `preflight/<platform>.py`, loaded from disk the same
    way a hook is — never inside the installed package. Returns
    None if the project has no such file (or it has no `check` function)."""
    module_path = Path(preflight_dir) / f"{platform}.py"
    if not module_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"configgen_preflight_{platform}", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "check", None)


def get_check(platform: str, preflight_dir: str | Path | None = None) -> CheckFn | None:
    """A project's own `<platform>.py` overrides the built-in checker of
    the same name, if any — the same plug-and-play override pattern used
    everywhere else a project can extend the core without touching it."""
    if preflight_dir is not None:
        custom = load_custom_check(preflight_dir, platform)
        if custom is not None:
            return custom
    return BUILTIN_CHECKS.get(platform)


def run_preflight(platform: str, text: str, preflight_dir: str | Path | None = None) -> list[str]:
    check_fn = get_check(platform, preflight_dir)
    if check_fn is None:
        return [f"unknown preflight platform '{platform}' (no built-in or custom check found)"]
    return check_fn(text)
