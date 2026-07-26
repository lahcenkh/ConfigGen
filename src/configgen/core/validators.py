"""Turns raw form values (strings, mostly — whatever a text widget, CSV cell,
or CLI arg hands us) into typed values ready for a template context.

Per-field: type coercion, pattern, min/max. Cross-field: `visible_if` /
`required_if` gate whether a field is shown / mandatory given the current
values of other fields. Deeper cross-field rules (lookups, "these two must
differ") belong in a prepare hook, which can reject the whole submission with
a PrepareError — see docs/prepare-hooks.md.
"""

from __future__ import annotations

import re

from configgen.core.db import Database
from configgen.core.schema import Field, Schema
from configgen.core.values import CIDRValue, IPCIDRValue, IPValue, NetworkValue

_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}


class FieldValidationError(Exception):
    """Raised with one message per invalid field, keyed by field key."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def _condition_met(condition: dict | None, values: dict) -> bool:
    if not condition:
        return True
    return all(str(values.get(k)) == str(v) for k, v in condition.items())


def _coerce_string(field: Field, raw: str, database: Database | None = None) -> str:
    value = str(raw)
    if field.pattern and not re.fullmatch(field.pattern, value):
        raise ValueError(f"'{value}' does not match the expected pattern")
    return value  # a missing return here is the bug this codebase already paid for once


def _coerce_int(field: Field, raw, database: Database | None = None) -> int:
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise ValueError(f"'{raw}' is not a whole number") from None
    if field.min is not None and value < field.min:
        raise ValueError(f"{value} is below the minimum of {field.min}")
    if field.max is not None and value > field.max:
        raise ValueError(f"{value} is above the maximum of {field.max}")
    return value


def _coerce_bool(field: Field, raw, database: Database | None = None) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in _TRUE_STRINGS:
        return True
    if text in _FALSE_STRINGS:
        return False
    raise ValueError(f"'{raw}' is not a valid yes/no value")


def _coerce_choice(field: Field, raw, database: Database | None = None) -> str:
    value = str(raw)
    if field.options:
        if value not in field.options:
            raise ValueError(f"'{value}' is not one of: {', '.join(field.options)}")
        return value
    # A `lookup` field's from_db is autocomplete only (any text is accepted);
    # a `choice` field's from_db is a closed set, checked only when a
    # Database is available — with none configured, we can't verify it, so
    # the value passes through (§5.3: form-only paths still work).
    if field.from_db and database is not None:
        options = database.all(field.from_db["query"])
        if value not in options:
            raise ValueError(f"'{value}' is not one of the values from '{field.from_db['query']}'")
    return value


_COERCERS = {
    "string": _coerce_string,
    "port": _coerce_string,
    "lookup": _coerce_string,
    "text": _coerce_string,
    "int": _coerce_int,
    "bool": _coerce_bool,
    "choice": _coerce_choice,
    "ip": lambda field, raw, database=None: IPValue(raw),
    "ip_cidr": lambda field, raw, database=None: IPCIDRValue(raw),
    "network": lambda field, raw, database=None: NetworkValue(raw),
    "cidr": lambda field, raw, database=None: CIDRValue(raw),
}


def coerce_field(field: Field, raw, database: Database | None = None) -> object:
    coercer = _COERCERS[field.type]
    return coercer(field, raw, database=database)


def validate_values(schema: Schema, raw_values: dict, *, database: Database | None = None) -> dict:
    """Returns a dict of typed values, keyed by field key.

    Fields hidden by `visible_if` are omitted from the result entirely (they
    are not part of this submission, not merely blank). `database`, if
    given, resolves `from_db` choice fields against the live query results;
    without one, those fields are accepted unchecked.
    """
    errors: dict[str, str] = {}
    result: dict[str, object] = {}

    for f in schema.fields:
        if not _condition_met(f.visible_if, raw_values):
            continue

        required = f.required or (bool(f.required_if) and _condition_met(f.required_if, raw_values))
        raw = raw_values.get(f.key, f.default)

        if raw is None or raw == "":
            if required:
                errors[f.key] = "This field is required"
            else:
                result[f.key] = None
            continue

        try:
            result[f.key] = coerce_field(f, raw, database=database)
        except ValueError as exc:
            message = str(exc)
            if f.example:
                message = f"{message} (expected like {f.example})"
            errors[f.key] = message

    if errors:
        raise FieldValidationError(errors)
    return result
