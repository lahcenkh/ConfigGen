"""User-customizable syntax highlighting rules — plain words the user
wants called out with their own color, layered on top of the built-in
Jinja/network-config highlighting (`highlighters.py`).

Persisted with the same `QSettings` mechanism `theme.py` uses for the
dark-mode preference, but machine-wide rather than per-username: these
are editor preferences about how text is *displayed*, not part of what
gets generated, so there's no reason for them to differ per operator.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from PySide6.QtCore import QSettings

from configgen.ui.theme import APP_NAME, APP_ORG

_SETTINGS_KEY = "custom_highlight_rules"


@dataclass(frozen=True)
class HighlightRule:
    word: str
    color: str
    bold: bool = False


# Seeded into the rules list the first time it's ever loaded (nothing
# saved yet) so they show up in HighlightRulesDialog like any other rule —
# editable, re-colorable, removable — rather than being baked into
# highlighters.py where a user has no way to touch them. Colors are fixed
# hex, not palette-derived, same as any other rule: legible on both a
# near-black and a near-white background rather than tuned for one.
DEFAULT_RULES = [
    HighlightRule(word="interface", color="#16a34a", bold=True),
    HighlightRule(word="no", color="#dc2626", bold=True),
    HighlightRule(word="shutdown", color="#dc2626", bold=True),
    HighlightRule(word="reboot", color="#dc2626", bold=True),
    HighlightRule(word="reload", color="#dc2626", bold=True),
    HighlightRule(word="erase", color="#dc2626", bold=True),
    HighlightRule(word="delete", color="#dc2626", bold=True),
    HighlightRule(word="format", color="#dc2626", bold=True),
    HighlightRule(word="clear", color="#dc2626", bold=True),
    HighlightRule(word="default", color="#dc2626", bold=True),
]


def _settings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def load_custom_rules() -> list[HighlightRule]:
    settings = _settings()
    if not settings.contains(_SETTINGS_KEY):
        return list(DEFAULT_RULES)
    raw = settings.value(_SETTINGS_KEY, "", type=str)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return list(DEFAULT_RULES)
    return [HighlightRule(**item) for item in data]


def save_custom_rules(rules: list[HighlightRule]) -> None:
    _settings().setValue(_SETTINGS_KEY, json.dumps([asdict(rule) for rule in rules]))
