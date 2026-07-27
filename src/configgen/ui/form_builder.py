"""Builds a form from a schema (§15), with live validation and
`visible_if`/`required_if`/`clear_when` reactivity (§2.3).

Validation here is never a second implementation of the rules — every
call goes through `core.validators.validate_values`, the same function
the CLI uses, so a field that's invalid in the GUI is invalid on
`configgen generate` too, and vice versa.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from configgen.core.db import Database, DatabaseError
from configgen.core.schema import Schema
from configgen.core.validators import FieldValidationError, condition_met, validate_values
from configgen.ui.widgets import (
    ChoiceFieldWidget,
    FieldWidget,
    LookupFieldWidget,
    build_field_widget,
)

logger = logging.getLogger(__name__)


class FormBuilder(QWidget):
    """One instance per schema/generation session."""

    valuesChanged = Signal()

    def __init__(
        self,
        schema: Schema,
        *,
        database: Database | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.schema = schema
        self.database = database
        self.widgets: dict[str, FieldWidget] = {}

        layout = QVBoxLayout(self)
        section_layouts: dict[str | None, QVBoxLayout] = {}

        # Two passes: build every widget (including defaults) with signals
        # silent first, then wire live reactivity. A field's default can be
        # set before every other field's widget exists yet — if that fired
        # valueChanged synchronously, _apply_conditionals would look up a
        # widget that isn't in self.widgets yet. (PySide swallows exceptions
        # raised inside a slot rather than propagating them, so this failed
        # silently instead of loudly — caught it only by testing by hand.)
        for field in schema.fields:
            widget = build_field_widget(field)
            self.widgets[field.key] = widget
            self._resolve_from_db_options(field, widget)

            if field.section not in section_layouts:
                box = QGroupBox(field.section or "")
                section_layouts[field.section] = QVBoxLayout(box)
                layout.addWidget(box)
            section_layouts[field.section].addWidget(widget)

            if field.default is not None:
                widget.set_value(field.default)

        for widget in self.widgets.values():
            widget.valueChanged.connect(self._on_value_changed)

        layout.addStretch()
        self._apply_conditionals()

    def _resolve_from_db_options(self, field, widget: FieldWidget) -> None:
        if not field.from_db or self.database is None:
            return
        try:
            options = [str(v) for v in self.database.all(field.from_db["query"])]
        except DatabaseError:
            logger.warning(
                "from_db query '%s' failed; field '%s' has no live options",
                field.from_db["query"],
                field.key,
            )
            return
        if isinstance(widget, ChoiceFieldWidget):
            widget.set_options(options)
        elif isinstance(widget, LookupFieldWidget):
            widget.set_completions(options)

    def raw_values(self) -> dict:
        return {key: widget.value() for key, widget in self.widgets.items()}

    def set_raw_values(self, values: dict) -> None:
        """Repopulates the form — used by "reopen"/"regenerate with these
        inputs" (§13.7) and by the bulk error-row fix-and-retry flow."""
        for key, value in values.items():
            if key in self.widgets:
                self.widgets[key].set_value(value)
        self._apply_conditionals()

    def _apply_conditionals(self) -> None:
        raw = self.raw_values()
        for field in self.schema.fields:
            widget = self.widgets[field.key]
            widget.set_visible_row(condition_met(field.visible_if, raw))
            required = field.required or (
                bool(field.required_if) and condition_met(field.required_if, raw)
            )
            widget.set_required(required)
            if field.clear_when and condition_met(field.clear_when, raw):
                widget.set_value(None)

    def _on_value_changed(self) -> None:
        self._apply_conditionals()
        self.validate()
        self.valuesChanged.emit()

    def validate(self) -> dict | None:
        """Returns the typed context on success, paints per-field error
        text and returns None on failure."""
        raw = self.raw_values()
        for widget in self.widgets.values():
            widget.set_error(None)
        try:
            return validate_values(self.schema, raw, database=self.database)
        except FieldValidationError as exc:
            for key, message in exc.errors.items():
                if key in self.widgets:
                    self.widgets[key].set_error(message)
            return None
