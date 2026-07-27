"""Landing dashboard: quick-start tiles, recent history, tools,
search/filter (§15/§15.1).

Tiles are scoped through `core.auth.visible_schemas` — the exact same
function `configgen list`'s auth-aware path and `configgen generate`'s
enforcement use — so "what a Config Engineer can see here" and "what they
can actually generate" can never drift apart.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from configgen.core.auth import ROLE_TEMPLATE_ENGINEER, User, visible_schemas
from configgen.core.schema import Schema
from configgen.ui import theme

_TILE_COLUMNS = 3


class TemplateTile(QFrame):
    clicked = Signal(str)  # schema id

    def __init__(self, schema: Schema, palette: theme.Palette, parent: QWidget | None = None):
        super().__init__(parent)
        self.schema = schema
        self.setObjectName("tile")
        self.setStyleSheet(theme.tile_style(palette))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(110)

        layout = QVBoxLayout(self)
        title = QLabel(schema.name)
        title.setStyleSheet("font-weight: 600;")
        title.setWordWrap(True)
        layout.addWidget(title)

        if schema.description:
            desc = QLabel(schema.description)
            desc.setObjectName("muted")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        status_bit = None if schema.status == "published" else schema.status.upper()
        meta_bits = [b for b in (schema.group, status_bit) if b]
        if meta_bits:
            meta = QLabel(" · ".join(meta_bits))
            meta.setObjectName("muted")
            layout.addWidget(meta)

        if schema.tags:
            tags_label = QLabel(" ".join(f"#{t}" for t in schema.tags))
            tags_label.setObjectName("muted")
            layout.addWidget(tags_label)

        layout.addStretch()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.schema.id)


class Dashboard(QWidget):
    templateSelected = Signal(str)
    bulkGenerateRequested = Signal()
    templateEditorRequested = Signal()
    userAdminRequested = Signal()
    importConfigPackRequested = Signal()
    generationLogRequested = Signal()

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

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_header())
        layout.addLayout(self._build_filters())

        self.tiles_area = QScrollArea()
        self.tiles_area.setWidgetResizable(True)
        self.tiles_container = QWidget()
        self.tiles_layout = QGridLayout(self.tiles_container)
        self.tiles_area.setWidget(self.tiles_container)
        layout.addWidget(self.tiles_area, stretch=1)

        if recent_log_entries:
            layout.addWidget(self._build_recent_panel(recent_log_entries))

        self._refresh_tiles()

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.addWidget(QLabel(f"Welcome, {self.user.username} ({self.user.role})"))
        header.addStretch()

        if self.user.is_admin or self.user.role == ROLE_TEMPLATE_ENGINEER:
            editor_button = QPushButton("Template Editor")
            editor_button.setObjectName("secondary")
            editor_button.clicked.connect(self.templateEditorRequested)
            header.addWidget(editor_button)

            log_button = QPushButton("Generation Log")
            log_button.setObjectName("secondary")
            log_button.clicked.connect(self.generationLogRequested)
            header.addWidget(log_button)

        if self.user.is_admin:
            admin_button = QPushButton("User Admin")
            admin_button.setObjectName("secondary")
            admin_button.clicked.connect(self.userAdminRequested)
            header.addWidget(admin_button)

            import_button = QPushButton("Import Config Pack")
            import_button.setObjectName("secondary")
            import_button.clicked.connect(self.importConfigPackRequested)
            header.addWidget(import_button)

        bulk_button = QPushButton("Bulk Generate")
        bulk_button.clicked.connect(self.bulkGenerateRequested)
        header.addWidget(bulk_button)
        return header

    def _build_filters(self) -> QHBoxLayout:
        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or tag…")
        self.search_input.textChanged.connect(self._refresh_tiles)
        filter_row.addWidget(self.search_input, stretch=1)

        self.group_filter = QComboBox()
        self.group_filter.addItem("All groups")
        group_names = sorted({s.group for s in self.all_schemas if s.group})
        self.group_filter.addItems(group_names)
        self.group_filter.currentTextChanged.connect(self._refresh_tiles)
        filter_row.addWidget(self.group_filter)
        return filter_row

    def _build_recent_panel(self, entries: list[dict]) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Recent"))
        for entry in entries[:10]:
            text = f"{entry['created_at']}  {entry['schema_id']}  →  {entry['output_filename']}"
            row = QLabel(text)
            row.setObjectName("muted")
            layout.addWidget(row)
        return panel

    def visible_schemas(self) -> list[Schema]:
        return visible_schemas(self.user, self.all_schemas, self.user_groups)

    def _refresh_tiles(self) -> None:
        while self.tiles_layout.count():
            item = self.tiles_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        query = self.search_input.text().strip().lower()
        group_filter = self.group_filter.currentText()

        filtered = []
        for schema in self.visible_schemas():
            if group_filter != "All groups" and schema.group != group_filter:
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
