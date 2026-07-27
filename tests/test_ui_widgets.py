from configgen.core.schema import Field
from configgen.ui.widgets import (
    WIDGET_CLASSES,
    BoolFieldWidget,
    ChoiceFieldWidget,
    IntFieldWidget,
    LookupFieldWidget,
    StringFieldWidget,
    TextFieldWidget,
    build_field_widget,
)


def test_all_field_types_have_a_widget_class():
    expected = {
        "string",
        "int",
        "bool",
        "choice",
        "ip",
        "ip_cidr",
        "network",
        "cidr",
        "port",
        "lookup",
        "text",
    }
    assert set(WIDGET_CLASSES) == expected


def test_string_widget_get_set_value(qtbot):
    field = Field(key="name", label="Name", type="string")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert isinstance(widget, StringFieldWidget)
    widget.set_value("web01")
    assert widget.value() == "web01"


def test_string_widget_shows_example_as_placeholder(qtbot):
    field = Field(key="name", label="Name", type="string", example="web01-nyc")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert widget.input.placeholderText() == "web01-nyc"


def test_int_widget_get_set_value(qtbot):
    field = Field(key="count", label="Count", type="int", min=1, max=10)
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert isinstance(widget, IntFieldWidget)
    widget.set_value(5)
    assert widget.value() == 5


def test_int_widget_clamps_display_range_beyond_int32(qtbot):
    # Regression test: a field.max like a full uint32 OSPF area id used to
    # overflow QSpinBox's signed-32-bit setRange() call.
    field = Field(key="area", label="Area", type="int", min=0, max=4294967295)
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert widget.input.maximum() <= 2**31 - 1


def test_bool_widget_get_set_value(qtbot):
    field = Field(key="flag", label="Flag", type="bool")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert isinstance(widget, BoolFieldWidget)
    widget.set_value(True)
    assert widget.value() is True
    widget.set_value(False)
    assert widget.value() is False


def test_choice_widget_options_and_value(qtbot):
    field = Field(key="mode", label="Mode", type="choice", options=["a", "b"])
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert isinstance(widget, ChoiceFieldWidget)
    assert [widget.input.itemText(i) for i in range(widget.input.count())] == ["a", "b"]
    widget.set_value("b")
    assert widget.value() == "b"


def test_choice_widget_set_options_preserves_current_selection_if_still_valid(qtbot):
    field = Field(key="region", label="Region", type="choice")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    widget.set_options(["us-east", "us-west"])
    widget.set_value("us-west")
    widget.set_options(["us-east", "us-west", "eu-central"])
    assert widget.value() == "us-west"


def test_lookup_widget_accepts_free_text_and_completions(qtbot):
    field = Field(key="device_name", label="Device", type="lookup")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert isinstance(widget, LookupFieldWidget)
    widget.set_completions(["edge-01", "edge-02"])
    widget.set_value("brand-new-device")
    assert widget.value() == "brand-new-device"


def test_text_widget_get_set_value(qtbot):
    field = Field(key="notes", label="Notes", type="text")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert isinstance(widget, TextFieldWidget)
    widget.set_value("multi\nline")
    assert widget.value() == "multi\nline"


def test_required_field_label_has_asterisk(qtbot):
    field = Field(key="name", label="Name", type="string", required=True)
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert widget._label.text() == "Name *"


def test_optional_field_label_has_no_asterisk(qtbot):
    field = Field(key="name", label="Name", type="string", required=False)
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    assert widget._label.text() == "Name"


def test_set_error_toggles_error_label_and_property(qtbot):
    field = Field(key="name", label="Name", type="string")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    widget.show()  # isVisible() is only meaningful once actually shown

    widget.set_error("bad value")
    assert widget._error_label.isVisible()
    assert widget._error_label.text() == "bad value"
    assert widget.input.property("hasError") is True

    widget.set_error(None)
    assert not widget._error_label.isVisible()
    assert widget.input.property("hasError") is False


def test_set_required_never_mutates_the_shared_field_object(qtbot):
    # Regression test: set_required() used to write the *effective*
    # required flag back into field.required, permanently corrupting the
    # field's static declaration (and any later core.validators call
    # against the same Schema/Field objects) after the first time a
    # required_if condition evaluated true.
    field = Field(key="x", label="X", type="string", required=False)
    widget = build_field_widget(field)
    qtbot.addWidget(widget)

    widget.set_required(True)
    assert field.required is False
    widget.set_required(False)
    assert field.required is False
    assert widget._label.text() == "X"


def test_set_visible_row_toggles_widget_visibility(qtbot):
    field = Field(key="x", label="X", type="string")
    widget = build_field_widget(field)
    qtbot.addWidget(widget)
    widget.set_visible_row(False)
    assert widget.isHidden()
    widget.set_visible_row(True)
    assert not widget.isHidden()
