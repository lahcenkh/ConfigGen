from datetime import datetime
from pathlib import Path

import pytest

from configgen.core.renderer import RenderError, header_comment, render_documents
from configgen.core.schema import Document, Schema


def _schema(**overrides) -> Schema:
    defaults = dict(name="Widget", id="widget", fields=[], template="widget.j2")
    defaults.update(overrides)
    return Schema(**defaults)


def test_render_single_document(tmp_path: Path):
    (tmp_path / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    schema = _schema()
    rendered = render_documents(schema, {"name": "world"}, templates_dir=tmp_path)
    assert rendered["primary"].endswith("hello world")


def test_render_includes_header_comment(tmp_path: Path):
    (tmp_path / "widget.j2").write_text("body", encoding="utf-8")
    schema = _schema(version=3)
    ts = datetime(2026, 1, 15, 14, 30, 0)
    rendered = render_documents(schema, {}, templates_dir=tmp_path, username="alice", timestamp=ts)
    text = rendered["primary"]
    assert "widget v3" in text
    assert "alice" in text
    assert "2026-01-15 14:30:00" in text
    assert text.strip().endswith("body")


def test_strict_undefined_raises_on_missing_variable(tmp_path: Path):
    (tmp_path / "widget.j2").write_text("{{ missing_var }}", encoding="utf-8")
    schema = _schema()
    with pytest.raises(RenderError):
        render_documents(schema, {}, templates_dir=tmp_path)


def test_a_buggy_custom_filter_becomes_a_render_error_not_a_raw_exception(tmp_path: Path):
    # Jinja2 only wraps template *syntax*/undefined-variable problems in its
    # own TemplateError hierarchy — an exception raised by a project's own
    # filter mid-render (a bad regex, a bad type assumption, ...) is NOT
    # wrapped and propagates straight out of .render() as whatever raw type
    # it is. That used to escape uncaught here, which is exactly the class
    # of "click render, nothing visibly happens" bug in a --windowed build
    # with no console for the raw traceback to land on.
    (tmp_path / "widget.j2").write_text("{{ name | explode }}", encoding="utf-8")
    schema = _schema()

    def explode(_value):
        raise ZeroDivisionError("deliberately broken filter")

    with pytest.raises(RenderError, match="deliberately broken filter"):
        render_documents(
            schema, {"name": "x"}, templates_dir=tmp_path, filters={"explode": explode}
        )


def test_render_logs_start_and_success(tmp_path: Path, caplog):
    (tmp_path / "widget.j2").write_text("hello {{ name }}", encoding="utf-8")
    schema = _schema()
    with caplog.at_level("INFO", logger="configgen.core.renderer"):
        render_documents(schema, {"name": "world"}, templates_dir=tmp_path)
    messages = "\n".join(caplog.messages)
    assert "rendering schema=widget doc=primary" in messages
    assert "rendered schema=widget doc=primary" in messages


def test_render_failure_is_logged_with_a_traceback(tmp_path: Path, caplog):
    (tmp_path / "widget.j2").write_text("{{ missing_var }}", encoding="utf-8")
    schema = _schema()
    with caplog.at_level("INFO", logger="configgen.core.renderer"):
        with pytest.raises(RenderError):
            render_documents(schema, {}, templates_dir=tmp_path)
    assert any(r.levelname == "ERROR" and "render failed" in r.message for r in caplog.records)


def test_render_multi_document(tmp_path: Path):
    (tmp_path / "primary.j2").write_text("PRIMARY {{ x }}", encoding="utf-8")
    (tmp_path / "backup.j2").write_text("BACKUP {{ x }}", encoding="utf-8")
    schema = _schema(
        template=None,
        documents=[
            Document(key="primary", label="Primary", template="primary.j2"),
            Document(key="backup", label="Backup", template="backup.j2"),
        ],
    )
    rendered = render_documents(schema, {"x": "1"}, templates_dir=tmp_path)
    assert set(rendered) == {"primary", "backup"}
    assert "PRIMARY 1" in rendered["primary"]
    assert "BACKUP 1" in rendered["backup"]


def test_custom_filters_are_available(tmp_path: Path):
    (tmp_path / "widget.j2").write_text("{{ name | shout }}", encoding="utf-8")
    schema = _schema()
    rendered = render_documents(
        schema, {"name": "hi"}, templates_dir=tmp_path, filters={"shout": str.upper}
    )
    assert "HI" in rendered["primary"]


def test_header_comment_uses_schema_comment_prefix():
    schema = _schema(comment_prefix="#")
    text = header_comment(schema, username="bob", timestamp=datetime(2026, 1, 1))
    assert text.startswith("#")
