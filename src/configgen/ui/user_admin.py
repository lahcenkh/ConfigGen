"""Admin user + group + API-key management (§13.4 Admin flows).

Every mutation here is a straight call into core.auth.AuthStore — the
same store the CLI's `user`/`group`/`apikey` commands use — so a user
created in the GUI shows up in `configgen user list` and vice versa.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from configgen.core.auth import ROLES, AuthError, AuthStore, User
from configgen.core.schema import find_schema_files, load_schema, set_schema_group


class CreateUserDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Create User")
        layout = QFormLayout(self)

        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.role_input = QComboBox()
        self.role_input.addItems(sorted(ROLES))

        layout.addRow("Username", self.username_input)
        layout.addRow("Password", self.password_input)
        layout.addRow("Role", self.role_input)

        buttons = QHBoxLayout()
        create_button = QPushButton("Create")
        create_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondary")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(create_button)
        buttons.addWidget(cancel_button)
        layout.addRow(buttons)

    def values(self) -> tuple[str, str, str]:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        role = self.role_input.currentText()
        return username, password, role


class UserAdminWindow(QDialog):
    def __init__(
        self,
        store: AuthStore,
        actor: User,
        schemas_dir: str | Path,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.actor = actor
        self.schemas_dir = Path(schemas_dir)
        self.setWindowTitle("User Admin")
        self.resize(900, 500)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_users_tab(), "Users")
        tabs.addTab(self._build_groups_tab(), "Groups")
        tabs.addTab(self._build_api_keys_tab(), "API Keys")
        layout.addWidget(tabs)

    # -- users ---------------------------------------------------------

    def _build_users_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.users_table = QTableWidget(0, 3)
        self.users_table.setHorizontalHeaderLabels(["Username", "Role", "Force PW Change"])
        self.users_table.setAlternatingRowColors(True)
        layout.addWidget(self.users_table)

        buttons = QHBoxLayout()
        create_button = QPushButton("Create User")
        create_button.clicked.connect(self._create_user)
        role_button = QPushButton("Change Role")
        role_button.setObjectName("secondary")
        role_button.clicked.connect(self._change_role)
        reset_button = QPushButton("Reset Password")
        reset_button.setObjectName("secondary")
        reset_button.clicked.connect(self._reset_password)
        delete_button = QPushButton("Delete User")
        delete_button.setObjectName("secondary")
        delete_button.clicked.connect(self._delete_user)
        for button in (create_button, role_button, reset_button, delete_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.refresh_users()
        return page

    def refresh_users(self) -> None:
        users = self.store.list_users()
        self.users_table.setRowCount(len(users))
        for row, user in enumerate(users):
            self.users_table.setItem(row, 0, QTableWidgetItem(user.username))
            self.users_table.setItem(row, 1, QTableWidgetItem(user.role))
            self.users_table.setItem(
                row, 2, QTableWidgetItem("yes" if user.force_password_change else "")
            )

    def _selected_username(self, table: QTableWidget) -> str | None:
        row = table.currentRow()
        if row < 0:
            return None
        return table.item(row, 0).text()

    def _create_user(self) -> None:
        dialog = CreateUserDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        username, password, role = dialog.values()
        try:
            self.store.create_user(username, password, role)
        except AuthError as exc:
            QMessageBox.warning(self, "Could not create user", str(exc))
            return
        self.refresh_users()

    def _change_role(self) -> None:
        username = self._selected_username(self.users_table)
        if username is None:
            return
        role, ok = QInputDialog.getItem(
            self, "Change Role", f"New role for '{username}':", sorted(ROLES), 0, False
        )
        if not ok:
            return
        try:
            self.store.set_role(username, role)
        except AuthError as exc:
            QMessageBox.warning(self, "Could not change role", str(exc))
            return
        self.refresh_users()

    def _reset_password(self) -> None:
        username = self._selected_username(self.users_table)
        if username is None:
            return
        password, ok = QInputDialog.getText(
            self, "Reset Password", f"New password for '{username}':", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        try:
            self.store.change_password(username, password)
        except AuthError as exc:
            QMessageBox.warning(self, "Could not reset password", str(exc))
            return
        QMessageBox.information(self, "Password reset", f"Password updated for '{username}'.")

    def _delete_user(self) -> None:
        username = self._selected_username(self.users_table)
        if username is None:
            return
        if username == self.actor.username:
            QMessageBox.warning(self, "Not allowed", "You can't delete your own account.")
            return
        confirmed = QMessageBox.question(
            self, "Delete user", f"Delete user '{username}'? This cannot be undone."
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_user(username)
        except AuthError as exc:
            QMessageBox.warning(self, "Could not delete user", str(exc))
            return
        self.refresh_users()

    # -- groups ----------------------------------------------------------

    def _build_groups_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)

        left = QVBoxLayout()
        self.groups_table = QTableWidget(0, 2)
        self.groups_table.setHorizontalHeaderLabels(["Group", "Description"])
        self.groups_table.setAlternatingRowColors(True)
        self.groups_table.currentItemChanged.connect(lambda *_: self._on_group_selected())
        left.addWidget(self.groups_table)

        group_buttons = QHBoxLayout()
        create_group_button = QPushButton("Create Group")
        create_group_button.clicked.connect(self._create_group)
        group_buttons.addWidget(create_group_button)
        left.addLayout(group_buttons)
        layout.addLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel("Members"))
        self.members_table = QTableWidget(0, 1)
        self.members_table.setHorizontalHeaderLabels(["Username"])
        self.members_table.setAlternatingRowColors(True)
        right.addWidget(self.members_table)

        member_buttons = QHBoxLayout()
        add_member_button = QPushButton("Add Member")
        add_member_button.clicked.connect(self._add_member)
        remove_member_button = QPushButton("Remove Member")
        remove_member_button.setObjectName("secondary")
        remove_member_button.clicked.connect(self._remove_member)
        member_buttons.addWidget(add_member_button)
        member_buttons.addWidget(remove_member_button)
        right.addLayout(member_buttons)
        layout.addLayout(right)

        access = QVBoxLayout()
        access.addWidget(QLabel("Config Access"))
        self.access_list = QListWidget()
        self.access_list.itemChanged.connect(self._on_access_item_changed)
        access.addWidget(self.access_list)
        layout.addLayout(access)

        self.refresh_groups()
        return page

    def refresh_groups(self) -> None:
        groups = self.store.list_groups()
        self.groups_table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            self.groups_table.setItem(row, 0, QTableWidgetItem(group.name))
            self.groups_table.setItem(row, 1, QTableWidgetItem(group.description or ""))
        self._on_group_selected()

    def _selected_group(self) -> str | None:
        row = self.groups_table.currentRow()
        if row < 0:
            return None
        item = self.groups_table.item(row, 0)
        return item.text() if item else None

    def _on_group_selected(self) -> None:
        self._refresh_group_members()
        self._refresh_access_list()

    def _refresh_group_members(self) -> None:
        group_name = self._selected_group()
        if group_name is None:
            self.members_table.setRowCount(0)
            return
        try:
            members = self.store.members_of_group(group_name)
        except AuthError:
            members = []
        self.members_table.setRowCount(len(members))
        for row, member in enumerate(members):
            self.members_table.setItem(row, 0, QTableWidgetItem(member.username))

    def _refresh_access_list(self) -> None:
        """Every schema, checked for whichever one group currently owns it
        (§13.2/§13.3: `schema.group` is a single access-control owner, not
        a many-to-many membership) — checking a box for the selected group
        reassigns that schema to it, taking it away from whatever group,
        if any, had it before."""
        group_name = self._selected_group()
        self.access_list.blockSignals(True)
        self.access_list.clear()
        if group_name is not None:
            for path in find_schema_files(self.schemas_dir):
                try:
                    schema = load_schema(path)
                except Exception:  # noqa: BLE001 - just skip an unparseable schema here
                    continue
                item = QListWidgetItem(schema.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if schema.group == group_name else Qt.CheckState.Unchecked
                )
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                if schema.group and schema.group != group_name:
                    item.setToolTip(f"Currently assigned to '{schema.group}'")
                self.access_list.addItem(item)
        self.access_list.blockSignals(False)

    def _on_access_item_changed(self, item: QListWidgetItem) -> None:
        group_name = self._selected_group()
        if group_name is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        new_group = group_name if item.checkState() == Qt.CheckState.Checked else None
        set_schema_group(path, new_group)
        self._refresh_access_list()

    def _create_group(self) -> None:
        name, ok = QInputDialog.getText(self, "Create Group", "Group name:")
        if not ok or not name.strip():
            return
        try:
            self.store.create_group(name.strip())
        except AuthError as exc:
            QMessageBox.warning(self, "Could not create group", str(exc))
            return
        self.refresh_groups()

    def _add_member(self) -> None:
        group_name = self._selected_group()
        if group_name is None:
            QMessageBox.information(self, "No group selected", "Select a group first.")
            return
        usernames = [u.username for u in self.store.list_users()]
        username, ok = QInputDialog.getItem(self, "Add Member", "User:", usernames, 0, False)
        if not ok:
            return
        try:
            self.store.assign_user_to_group(username, group_name, assigned_by=self.actor.username)
        except AuthError as exc:
            QMessageBox.warning(self, "Could not add member", str(exc))
            return
        self._refresh_group_members()

    def _remove_member(self) -> None:
        group_name = self._selected_group()
        row = self.members_table.currentRow()
        if group_name is None or row < 0:
            return
        username = self.members_table.item(row, 0).text()
        try:
            self.store.remove_user_from_group(username, group_name)
        except AuthError as exc:
            QMessageBox.warning(self, "Could not remove member", str(exc))
            return
        self._refresh_group_members()

    # -- API keys ----------------------------------------------------------

    def _build_api_keys_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.keys_table = QTableWidget(0, 4)
        self.keys_table.setHorizontalHeaderLabels(["ID", "Username", "Label", "Status"])
        self.keys_table.setAlternatingRowColors(True)
        layout.addWidget(self.keys_table)

        buttons = QHBoxLayout()
        create_button = QPushButton("Create Key")
        create_button.clicked.connect(self._create_api_key)
        revoke_button = QPushButton("Revoke")
        revoke_button.setObjectName("secondary")
        revoke_button.clicked.connect(self._revoke_api_key)
        buttons.addWidget(create_button)
        buttons.addWidget(revoke_button)
        layout.addLayout(buttons)

        self.refresh_api_keys()
        return page

    def refresh_api_keys(self) -> None:
        usernames_by_id = {u.id: u.username for u in self.store.list_users()}
        keys = self.store.list_api_keys()
        self.keys_table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            self.keys_table.setItem(row, 0, QTableWidgetItem(str(key["id"])))
            self.keys_table.setItem(
                row, 1, QTableWidgetItem(usernames_by_id.get(key["user_id"], "?"))
            )
            self.keys_table.setItem(row, 2, QTableWidgetItem(key["label"] or ""))
            status = "revoked" if key["revoked_at"] else "active"
            self.keys_table.setItem(row, 3, QTableWidgetItem(status))

    def _create_api_key(self) -> None:
        usernames = [u.username for u in self.store.list_users()]
        username, ok = QInputDialog.getItem(self, "Create API Key", "User:", usernames, 0, False)
        if not ok:
            return
        label, ok = QInputDialog.getText(self, "Create API Key", "Label (e.g. 'CI pipeline'):")
        if not ok:
            return
        raw_key = self.store.create_api_key(username, label=label or None)
        QMessageBox.information(
            self,
            "API key created",
            f"Key for '{username}':\n\n{raw_key}\n\nThis is shown once — store it now.",
        )
        self.refresh_api_keys()

    def _revoke_api_key(self) -> None:
        row = self.keys_table.currentRow()
        if row < 0:
            return
        key_id = int(self.keys_table.item(row, 0).text())
        try:
            self.store.revoke_api_key(key_id)
        except AuthError as exc:
            QMessageBox.warning(self, "Could not revoke key", str(exc))
            return
        self.refresh_api_keys()
