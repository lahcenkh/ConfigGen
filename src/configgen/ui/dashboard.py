"""Landing dashboard: quick-start tiles, recent activity, search/filter
(§15/§15.1).

Tiles are scoped through `core.auth.visible_schemas` — the exact same
function `configgen list`'s auth-aware path and `configgen generate`'s
enforcement use — so "what a Config Engineer can see here" and "what they
can actually generate" can never drift apart.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from configgen.core.auth import ROLE_TEMPLATE_ENGINEER, User, visible_schemas
from configgen.core.schema import Schema
from configgen.ui import icons, theme
from configgen.ui.flow_layout import FlowLayout
from configgen.ui.widgets import StatusBadge

_TILE_COLUMNS = 2
_ACTIVITY_RAIL_WIDTH = 450
# Rail width minus panel/row margins, the time column, and the Reopen
# button — labels must stay inside this or they push Reopen off the edge
# (QLabel has no built-in truncation, only `QFontMetrics.elidedText` does).
_ACTIVITY_TEXT_WIDTH = 190


def _relative_time(iso_timestamp: str) -> str:
    then = datetime.fromisoformat(iso_timestamp)
    now = datetime.now(then.tzinfo)
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _format_date(d: date) -> str:
    return f"{d.day} {d.strftime('%b').upper()} {d.year}"


def _group_by_day(entries: list[dict]) -> list[tuple[str, list[dict]]]:
    """Groups already-DESC-ordered log entries by calendar day, labeling
    today/yesterday specially. Entries arrive newest-first and dates only
    move backward as `id` decreases, so same-day entries are contiguous —
    no need to sort or bucket out of order."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    groups: list[tuple[date, list[dict]]] = []
    for entry in entries:
        entry_date = datetime.fromisoformat(entry["created_at"]).date()
        if groups and groups[-1][0] == entry_date:
            groups[-1][1].append(entry)
        else:
            groups.append((entry_date, [entry]))

    labeled = []
    for entry_date, day_entries in groups:
        if entry_date == today:
            label = f"TODAY · {_format_date(entry_date)}"
        elif entry_date == yesterday:
            label = f"YESTERDAY · {_format_date(entry_date)}"
        else:
            label = _format_date(entry_date)
        labeled.append((label, day_entries))
    return labeled


def _clamp_description(text: str, limit: int = 150) -> str:
    """Word-boundary truncation with an ellipsis — Qt's QLabel has no
    native multi-line clamp, and a hard `setMaximumHeight` pixel-clips
    text mid-word/mid-line instead of ending cleanly."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _tag_chip(tag: str) -> QLabel:
    chip = QLabel(f"#{tag}")
    chip.setObjectName("chip")
    chip.setFont(QFont(theme.MONO_FONT_FAMILY))
    return chip


class TemplateTile(QFrame):
    clicked = Signal(str)  # schema id

    def __init__(self, schema: Schema, palette: theme.Palette, parent: QWidget | None = None):
        super().__init__(parent)
        self.schema = schema
        self.setObjectName("tile")
        self.setStyleSheet(theme.tile_style(palette))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(120)
        # Without this, QGridLayout stretches every tile in a row to match
        # the row's tallest tile (its default Preferred vertical policy) —
        # padding shorter cards out with dead space instead of letting each
        # one hug its own content like the reference design.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        title = QLabel(schema.name)
        title.setObjectName("headline-md")
        title.setWordWrap(True)
        header_row.addWidget(title, stretch=1)
        self._status_badge = StatusBadge(schema.status, palette)
        header_row.addWidget(self._status_badge)
        layout.addLayout(header_row)

        desc = QLabel(_clamp_description(schema.description or ""))
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)

        # Tag chips get their own full-width row rather than sharing the
        # meta/Generate row: a FlowLayout's height depends on the width
        # it's given, and Qt's QHBoxLayout doesn't reliably negotiate that
        # for a stretch child (it was handing the chips a 0px-wide box,
        # stacking every chip at x=0 instead of flowing them).
        if schema.tags:
            tags_container = QWidget()
            # A bare QWidget picks up the app-wide `QWidget { background-color }`
            # rule same as everything else — spanning the card's full width,
            # that painted a solid dark bar behind the (actually transparent)
            # chip pills instead of letting the card's own background show.
            tags_container.setStyleSheet("background: transparent;")
            tags_flow = FlowLayout(tags_container, h_spacing=4, v_spacing=4)
            tags_flow.setContentsMargins(0, 0, 0, 0)
            for tag in schema.tags:
                tags_flow.addWidget(_tag_chip(tag))
            layout.addWidget(tags_container)

        footer_row = QHBoxLayout()
        footer_row.addStretch()
        doc_count = len(schema.document_list())
        meta = QLabel(f"{doc_count} output{'s' if doc_count != 1 else ''}")
        meta.setObjectName("tertiary")
        footer_row.addWidget(meta)

        generate_button = QPushButton("Generate")
        generate_button.setObjectName("ghost-accent")
        generate_button.clicked.connect(lambda: self.clicked.emit(self.schema.id))
        footer_row.addWidget(generate_button)

        layout.addLayout(footer_row)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.schema.id)

    def refresh_palette(self, palette: theme.Palette) -> None:
        """The card's accent stripe (`tile_style`) and the status badge
        both set their own inline stylesheet at construction time — that
        snapshot doesn't repaint on its own when the app-wide palette
        changes, unlike everything else on the card, which just cascades
        from the tile's global objectName rules. Without this, toggling
        dark/light mode left every card's border and badge stuck on the
        old palette while its text and buttons updated instantly."""
        self.setStyleSheet(theme.tile_style(palette))
        self._status_badge.set_status(self.schema.status, palette)


class Dashboard(QWidget):
    """Header (title/stats/search/actions) + tile grid + a fixed activity
    rail. Global navigation (Template Editor, User Admin, Bulk Generate,
    etc.) lives in the persistent Sidebar (§15 GUI redesign) — Dashboard
    only owns its own content, not app-wide nav."""

    templateSelected = Signal(str)
    regenerateRequested = Signal(str, dict)
    newTemplateRequested = Signal()
    viewAllActivityRequested = Signal()

    def __init__(
        self,
        user: User,
        schemas: list[Schema],
        user_groups: set[str],
        palette: theme.Palette,
        *,
        recent_log_entries: list[dict] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.user = user
        self.all_schemas = schemas
        self.user_groups = user_groups
        self.palette = palette
        self._recent_log_entries = recent_log_entries or []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)
        outer.addLayout(self._build_header_row())

        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        self.tiles_area = QScrollArea()
        self.tiles_area.setWidgetResizable(True)
        self.tiles_area.setFrameShape(QFrame.Shape.NoFrame)
        self.tiles_container = QWidget()
        self.tiles_layout = QGridLayout(self.tiles_container)
        self.tiles_layout.setSpacing(12)
        self.tiles_area.setWidget(self.tiles_container)
        content_row.addWidget(self.tiles_area, stretch=1)

        content_row.addWidget(self._build_activity_rail(self._recent_log_entries))
        outer.addLayout(content_row, stretch=1)

        self._refresh_tiles()

        shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut.activated.connect(self.search_input.setFocus)

    # -- header ---------------------------------------------------------

    def _build_header_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title = QLabel("Templates")
        title.setObjectName("headline-lg")
        title_column.addWidget(title)
        self.stat_summary_label = QLabel(self._stat_summary())
        self.stat_summary_label.setObjectName("muted")
        title_column.addWidget(self.stat_summary_label)
        row.addLayout(title_column)
        row.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search name or tag")
        self.search_input.setToolTip("Search (Ctrl+K)")
        self.search_input.setFixedWidth(220)
        self._search_icon_action = self.search_input.addAction(
            icons.search_icon(self.palette.text_muted), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_input.textChanged.connect(self._refresh_tiles)
        row.addWidget(self.search_input)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All statuses", "draft", "published", "deprecated"])
        self.status_filter.currentTextChanged.connect(self._refresh_tiles)
        row.addWidget(self.status_filter)

        self.group_filter = QComboBox()
        self.group_filter.addItem("All groups")
        group_names = sorted({s.group for s in self.all_schemas if s.group})
        self.group_filter.addItems(group_names)
        self.group_filter.currentTextChanged.connect(self._refresh_tiles)
        row.addWidget(self.group_filter)

        if self.user.is_admin or self.user.role == ROLE_TEMPLATE_ENGINEER:
            new_template_button = QPushButton("+ New Template")
            new_template_button.clicked.connect(self.newTemplateRequested)
            row.addWidget(new_template_button)

        return row

    def _stat_summary(self) -> str:
        visible = self.visible_schemas()
        total = len(visible)
        published = sum(1 for s in visible if s.status == "published")
        parts = [f"{total} template{'s' if total != 1 else ''}", f"{published} published"]
        if self._recent_log_entries:
            latest = self._recent_log_entries[0]["created_at"]
            parts.append(f"last generation {_relative_time(latest)}")
        return " · ".join(parts)

    # -- tiles ---------------------------------------------------------

    def visible_schemas(self) -> list[Schema]:
        return visible_schemas(self.user, self.all_schemas, self.user_groups)

    def refresh_palette(self, palette: theme.Palette) -> None:
        self.palette = palette
        self._search_icon_action.setIcon(icons.search_icon(palette.text_muted))
        for index in range(self.tiles_layout.count()):
            widget = self.tiles_layout.itemAt(index).widget()
            if isinstance(widget, TemplateTile):
                widget.refresh_palette(palette)

    def _refresh_tiles(self) -> None:
        while self.tiles_layout.count():
            item = self.tiles_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        query = self.search_input.text().strip().lower()
        group_filter = self.group_filter.currentText()
        status_filter = self.status_filter.currentText()

        filtered = []
        for schema in self.visible_schemas():
            if group_filter != "All groups" and schema.group != group_filter:
                continue
            if status_filter != "All statuses" and schema.status != status_filter:
                continue
            haystack = " ".join([schema.name, schema.id, *schema.tags]).lower()
            if query and query not in haystack:
                continue
            filtered.append(schema)

        if not filtered:
            self.tiles_layout.addWidget(QLabel("No templates match."), 0, 0)
            return

        for index, schema in enumerate(filtered):
            tile = TemplateTile(schema, self.palette)
            tile.clicked.connect(self.templateSelected)
            self.tiles_layout.addWidget(tile, index // _TILE_COLUMNS, index % _TILE_COLUMNS)

    # -- activity rail ---------------------------------------------------------

    def _build_activity_rail(self, entries: list[dict]) -> QFrame:
        rail = QFrame()
        rail.setObjectName("panel")
        rail.setFixedWidth(_ACTIVITY_RAIL_WIDTH)
        outer = QVBoxLayout(rail)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Recent generations")
        title.setObjectName("headline-md")
        header_row.addWidget(title, stretch=1)
        view_all = QPushButton("View all →")
        view_all.setObjectName("secondary")
        view_all.clicked.connect(self.viewAllActivityRequested)
        header_row.addWidget(view_all)
        outer.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # QScrollArea and its content widget are bare QWidgets, so both pick
        # up the app-wide `QWidget { background-color }` rule (the page
        # background, not the panel's) — same bug as the tag-chip wrapper,
        # just covering nearly the whole rail instead of one row.
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        if not entries:
            empty = QLabel("No generations yet — output will show up here.")
            empty.setObjectName("muted")
            empty.setWordWrap(True)
            content_layout.addWidget(empty)
        else:
            for label, day_entries in _group_by_day(entries):
                run_count = len(day_entries)
                heading = QLabel(f"{label}   ·   {run_count} run{'s' if run_count != 1 else ''}")
                heading.setObjectName("label-sm")
                content_layout.addWidget(heading)
                divider = QFrame()
                divider.setObjectName("divider")
                content_layout.addWidget(divider)
                for entry in day_entries:
                    content_layout.addWidget(self._build_activity_row(entry))

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)
        return rail

    def _build_activity_row(self, entry: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("activity-row")
        row.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 6, 6, 6)
        row_layout.setSpacing(10)

        mono_font = QFont(theme.MONO_FONT_FAMILY)

        time_label = QLabel(datetime.fromisoformat(entry["created_at"]).strftime("%H:%M"))
        time_label.setObjectName("tertiary")
        time_label.setFont(mono_font)
        time_label.setFixedWidth(40)
        row_layout.addWidget(time_label)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)

        filename_label = QLabel()
        filename_label.setFont(mono_font)
        filename_label.setFixedWidth(_ACTIVITY_TEXT_WIDTH)
        mono_metrics = QFontMetrics(mono_font)
        filename_label.setText(
            mono_metrics.elidedText(
                entry["output_filename"], Qt.TextElideMode.ElideLeft, _ACTIVITY_TEXT_WIDTH
            )
        )
        filename_label.setToolTip(entry["output_filename"])
        text_column.addWidget(filename_label)

        meta_text = f"{entry['schema_id']} · {entry.get('group_name') or 'ungrouped'}"
        meta_label = QLabel()
        meta_label.setObjectName("tertiary")
        meta_label.setFixedWidth(_ACTIVITY_TEXT_WIDTH)
        meta_label.setText(
            QFontMetrics(meta_label.font()).elidedText(
                meta_text, Qt.TextElideMode.ElideRight, _ACTIVITY_TEXT_WIDTH
            )
        )
        meta_label.setToolTip(meta_text)
        text_column.addWidget(meta_label)

        row_layout.addLayout(text_column, stretch=1)

        reopen_button = QPushButton("Reopen")
        reopen_button.setObjectName("secondary")
        reopen_button.clicked.connect(
            lambda _checked=False, e=entry: self.regenerateRequested.emit(
                e["schema_id"], json.loads(e["form_inputs"])
            )
        )
        row_layout.addWidget(reopen_button)

        return row
