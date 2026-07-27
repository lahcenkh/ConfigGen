"""Import Config Pack dialog (§14.3) — Admin only, wired from the
dashboard's "Import Config Pack" tile.

On an id conflict, prompts to overwrite or rename per §14.2 rather than
just failing — the same choice `configgen import --overwrite`/`--rename`
gives on the CLI side.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from configgen.core.configpack import ConfigPackConflict, ConfigPackError, import_config_pack


class ImportConfigPackDialog(QDialog):
    def __init__(self, resources_root: str | Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.resources_root = Path(resources_root)
        self.imported_schema_id: str | None = None

        self.setWindowTitle("Import Config Pack")
        self.resize(480, 160)
        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setReadOnly(True)
        file_row.addWidget(self.file_input, stretch=1)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse)
        file_row.addWidget(browse_button)
        layout.addLayout(file_row)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(lambda: self._run_import())
        close_button = QPushButton("Close")
        close_button.setObjectName("secondary")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.import_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _browse(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select config pack", "", "Config packs (*.zip)"
        )
        if path_str:
            self.file_input.setText(path_str)

    def _run_import(self, *, on_conflict: str = "error", new_id: str | None = None) -> None:
        path_str = self.file_input.text().strip()
        if not path_str:
            QMessageBox.warning(self, "No file", "Choose a .configpack.zip file first.")
            return
        try:
            result = import_config_pack(
                path_str, self.resources_root, on_conflict=on_conflict, new_id=new_id
            )
        except ConfigPackConflict as exc:
            self._resolve_conflict(exc)
            return
        except ConfigPackError as exc:
            self.status_label.setText(f"Import failed: {exc}")
            return

        self.imported_schema_id = result.schema_id
        self.status_label.setText(f"Imported '{result.schema_id}' -> {result.schema_path}")
        self.accept()

    def _resolve_conflict(self, conflict: ConfigPackConflict) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Config already exists")
        box.setText(
            f"A schema with id '{conflict.schema_id}' already exists "
            f"at {conflict.existing_path}.\nOverwrite it, or import under a new id?"
        )
        overwrite_button = box.addButton("Overwrite", QMessageBox.ButtonRole.DestructiveRole)
        rename_button = box.addButton("Rename", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is overwrite_button:
            self._run_import(on_conflict="overwrite")
        elif clicked is rename_button:
            new_id, ok = QInputDialog.getText(
                self, "Rename", f"New id for the imported schema (was '{conflict.schema_id}'):"
            )
            if ok and new_id.strip():
                self._run_import(on_conflict="rename", new_id=new_id.strip())
