"""One widget per field type (§2.2/§15), each behind a uniform
`FieldWidget` interface — `.value()`, `.set_value()`, `.set_error()` — so
`form_builder.py` never branches on type once a widget is built. Widgets
carry no knowledge of validation rules or `from_db`; the form builder
resolves those and calls back in (`set_options`/`set_completions`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from configgen.core.schema import Field
from configgen.ui import theme

_INT_MIN = -(2**31)
_INT_MAX = 2**31 - 1


class FieldWidget(QWidget):
    """label + input + help/error text. Subclasses implement `_build_input`,
    `value`, and `set_value`; everything else is shared."""

    valueChanged = Signal()

    def __init__(self, field: Field, parent: QWidget | None = None):
        super().__init__(parent)
        self.field = field

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        label_text = field.label + (" *" if field.required else "")
        self._label = QLabel(label_text)
        layout.addWidget(self._label)

        self.input = self._build_input()
        layout.addWidget(self.input)

        self._help_label = None
        if field.help:
            self._help_label = QLabel(field.help)
            self._help_label.setObjectName("muted")
            self._help_label.setWordWrap(True)
            layout.addWidget(self._help_label)

        self._error_label = QLabel()
        self._error_label.setObjectName("error")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

    def _build_input(self) -> QWidget:
        raise NotImplementedError

    def value(self):
        raise NotImplementedError

    def set_value(self, value) -> None:
        raise NotImplementedError

    def set_visible_row(self, visible: bool) -> None:
        """`visible_if` (§2.3) hides the whole field, not just the input."""
        self.setVisible(visible)

    def set_required(self, required: bool) -> None:
        """`required_if` (§2.3) can flip mid-session as other fields change.

        Only the visual "*" is stateful here — `self.field` is the same
        object `schema.fields` holds, shared with (and re-validated by)
        core.validators. Writing the *effective* required flag back into
        `field.required` would corrupt the field's static declaration: the
        next `_apply_conditionals()` pass computes effective-required as
        `field.required or condition_met(...)`, so once mutated true it
        could never read false again, in the GUI or in a later
        validate_values() call against the same schema object.
        """
        self._label.setText(self.field.label + (" *" if required else ""))

    def set_error(self, message: str | None) -> None:
        has_error = bool(message)
        self._error_label.setText(message or "")
        self._error_label.setVisible(has_error)
        self.input.setProperty("hasError", has_error)
        style = self.input.style()
        style.unpolish(self.input)
        style.polish(self.input)


def _line_edit_with_example(field: Field) -> QLineEdit:
    line_edit = QLineEdit()
    if field.example:
        line_edit.setPlaceholderText(field.example)
    return line_edit


class StringFieldWidget(FieldWidget):
    def _build_input(self) -> QWidget:
        line_edit = _line_edit_with_example(self.field)
        line_edit.textChanged.connect(self.valueChanged)
        return line_edit

    def value(self) -> str:
        return self.input.text()

    def set_value(self, value) -> None:
        self.input.setText("" if value is None else str(value))


class TextFieldWidget(FieldWidget):
    def _build_input(self) -> QWidget:
        text_edit = QPlainTextEdit()
        text_edit.setMaximumHeight(90)
        text_edit.textChanged.connect(self.valueChanged)
        return text_edit

    def value(self) -> str:
        return self.input.toPlainText()

    def set_value(self, value) -> None:
        self.input.setPlainText("" if value is None else str(value))


class IntFieldWidget(FieldWidget):
    def _build_input(self) -> QWidget:
        spin_box = QSpinBox()
        # QSpinBox is a signed 32-bit control; a field's real min/max (e.g.
        # a full uint32 OSPF area id, up to 4294967295) can exceed that.
        # Clamp what the spinner displays — core.validators enforces the
        # field's actual declared range regardless of what the UI allows.
        low = int(self.field.min) if self.field.min is not None else _INT_MIN
        high = int(self.field.max) if self.field.max is not None else _INT_MAX
        spin_box.setRange(max(low, _INT_MIN), min(high, _INT_MAX))
        spin_box.valueChanged.connect(self.valueChanged)
        return spin_box

    def value(self) -> int:
        return self.input.value()

    def set_value(self, value) -> None:
        self.input.setValue(int(value) if value is not None else 0)


class BoolFieldWidget(FieldWidget):
    def _build_input(self) -> QWidget:
        checkbox = QCheckBox(self.field.label)
        checkbox.stateChanged.connect(self.valueChanged)
        return checkbox

    def value(self) -> bool:
        return self.input.isChecked()

    def set_value(self, value) -> None:
        self.input.setChecked(bool(value))


class ChoiceFieldWidget(FieldWidget):
    def _build_input(self) -> QWidget:
        combo = QComboBox()
        if self.field.options:
            combo.addItems(self.field.options)
        combo.currentTextChanged.connect(self.valueChanged)
        return combo

    def set_options(self, options: list[str]) -> None:
        """`from_db` choices (§2.5) — resolved and pushed in by the form
        builder, since this widget has no database access of its own."""
        current = self.input.currentText()
        self.input.blockSignals(True)
        self.input.clear()
        self.input.addItems(options)
        if current in options:
            self.input.setCurrentText(current)
        self.input.blockSignals(False)

    def value(self) -> str:
        return self.input.currentText()

    def set_value(self, value) -> None:
        if value is not None:
            self.input.setCurrentText(str(value))


class LookupFieldWidget(FieldWidget):
    """Line edit + autocomplete (§2.2) — free text is always accepted,
    completions are just a hint, resolved the same way as choice options."""

    def _build_input(self) -> QWidget:
        line_edit = _line_edit_with_example(self.field)
        line_edit.textChanged.connect(self.valueChanged)
        return line_edit

    def set_completions(self, completions: list[str]) -> None:
        completer = QCompleter(completions, self.input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.input.setCompleter(completer)

    def value(self) -> str:
        return self.input.text()

    def set_value(self, value) -> None:
        self.input.setText("" if value is None else str(value))


# ip / ip_cidr / network / cidr / port all behave like a plain string field
# at the widget layer — type-specific parsing and validation happens in
# core/validators.py, not here. Each still gets a monospace font (address/
# port digits should align the way they would in a real config file) and a
# default placeholder shaped like the expected input, used only when the
# schema doesn't already supply its own `example:`.
def _mono_line_edit(field: Field, default_placeholder: str) -> QLineEdit:
    line_edit = _line_edit_with_example(field)
    line_edit.setFont(QFont(theme.MONO_FONT_FAMILY))
    if not field.example:
        line_edit.setPlaceholderText(default_placeholder)
    return line_edit


class IPFieldWidget(StringFieldWidget):
    def _build_input(self) -> QWidget:
        line_edit = _mono_line_edit(self.field, "000.000.000.000")
        line_edit.textChanged.connect(self.valueChanged)
        return line_edit


class IPCIDRFieldWidget(StringFieldWidget):
    def _build_input(self) -> QWidget:
        line_edit = _mono_line_edit(self.field, "000.000.000.000/00")
        line_edit.textChanged.connect(self.valueChanged)
        return line_edit


class NetworkFieldWidget(StringFieldWidget):
    def _build_input(self) -> QWidget:
        line_edit = _mono_line_edit(self.field, "000.000.000.000/00")
        line_edit.textChanged.connect(self.valueChanged)
        return line_edit


class CIDRFieldWidget(StringFieldWidget):
    def _build_input(self) -> QWidget:
        line_edit = _mono_line_edit(self.field, "000.000.000.000/00")
        line_edit.textChanged.connect(self.valueChanged)
        return line_edit


class PortFieldWidget(StringFieldWidget):
    def _build_input(self) -> QWidget:
        line_edit = _mono_line_edit(self.field, "0-65535")
        line_edit.textChanged.connect(self.valueChanged)
        return line_edit


class StatusBadge(QLabel):
    """Small uppercase status chip (draft/published/deprecated/...) shared
    by the dashboard's template tiles and the template editor's header —
    one place that decides what color a status is, instead of each screen
    re-deriving it."""

    _COLOR_ATTR = {
        "published": "success",
        "deprecated": "warning",
    }

    def __init__(self, status: str, palette: theme.Palette, parent: QWidget | None = None):
        super().__init__(status.upper(), parent)
        self.setObjectName("badge")
        self.set_status(status, palette)

    def set_status(self, status: str, palette: theme.Palette) -> None:
        self.setText(status.upper())
        color = getattr(palette, self._COLOR_ATTR.get(status, "text_muted"))
        self.setStyleSheet(
            f"QLabel#badge {{ color: {color}; border: 1px solid {color}; "
            f"border-radius: {theme.RADIUS_SM}; padding: 1px 6px; "
            f"font-weight: 700; font-size: 10px; }}"
        )


WIDGET_CLASSES: dict[str, type[FieldWidget]] = {
    "string": StringFieldWidget,
    "int": IntFieldWidget,
    "bool": BoolFieldWidget,
    "choice": ChoiceFieldWidget,
    "ip": IPFieldWidget,
    "ip_cidr": IPCIDRFieldWidget,
    "network": NetworkFieldWidget,
    "cidr": CIDRFieldWidget,
    "port": PortFieldWidget,
    "lookup": LookupFieldWidget,
    "text": TextFieldWidget,
}


def build_field_widget(field: Field, parent: QWidget | None = None) -> FieldWidget:
    widget_cls = WIDGET_CLASSES[field.type]
    return widget_cls(field, parent)
