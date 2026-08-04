"""Users, roles, groups, API keys, and the generation log (§13 of the build
plan) — the layer that makes ConfigGen a team tool rather than a solo CLI.

Storage is a dedicated `users.db`, separate from any project inventory
database (§13.5). A brand-new users.db bootstraps a single `admin`/`admin`
account with `force_password_change` set, so a solo user can start
generating immediately (§13.8) — the role/group system exists but never
blocks anyone until a second user is created.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from configgen.core.schema import Schema

ROLE_ADMIN = "admin"
ROLE_TEMPLATE_ENGINEER = "template_engineer"
ROLE_CONFIG_ENGINEER = "config_engineer"
ROLES = {ROLE_ADMIN, ROLE_TEMPLATE_ENGINEER, ROLE_CONFIG_ENGINEER}

_USERNAME_RE = re.compile(r"^[a-z0-9_-]+$")
_PBKDF2_ITERATIONS = 260_000
MIN_PASSWORD_LENGTH = 8
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class AuthError(Exception):
    """Base for every auth failure the CLI/GUI should show cleanly."""


class InvalidCredentials(AuthError):
    pass


class AccountLocked(AuthError):
    def __init__(self, locked_until: datetime):
        self.locked_until = locked_until
        super().__init__(f"account locked until {locked_until.isoformat()}")


class PermissionDenied(AuthError):
    pass


class UserExists(AuthError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def _verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    candidate, _ = _hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(candidate, password_hash)


def _validate_username(username: str) -> None:
    if not _USERNAME_RE.fullmatch(username):
        raise AuthError(
            f"invalid username '{username}': only lowercase letters, digits, '_' and '-' allowed"
        )


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")


@dataclass
class User:
    id: int
    username: str
    role: str
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    force_password_change: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


@dataclass
class Group:
    id: int
    name: str
    slug: str
    description: str | None = None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "group"


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        company_name=row["company_name"],
        force_password_change=bool(row["force_password_change"]),
    )


class AuthStore:
    def __init__(self, db_path: str | Path, *, bootstrap: bool = True):
        self.db_path = Path(db_path)
        # sqlite3.connect() doesn't create missing parent directories —
        # harmless when db_path is app-root-adjacent (always exists), but
        # users_db_path() now lives under resources/data/, which a fresh
        # from_db-free install has no other reason to have created yet.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        if bootstrap:
            self._ensure_bootstrap_admin()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    company_name TEXT,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT,
                    force_password_change INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    slug TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_members (
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    group_id INTEGER NOT NULL REFERENCES groups(id),
                    assigned_at TEXT NOT NULL,
                    assigned_by TEXT,
                    PRIMARY KEY (user_id, group_id)
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    key_hash TEXT NOT NULL UNIQUE,
                    label TEXT,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS generation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    group_name TEXT,
                    schema_id TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    form_inputs TEXT NOT NULL,
                    output_filename TEXT NOT NULL,
                    bulk_batch_id TEXT,
                    created_at TEXT NOT NULL
                );
                """)
            conn.commit()
        finally:
            conn.close()

    def _ensure_bootstrap_admin(self) -> None:
        conn = self._connect()
        try:
            (count,) = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        finally:
            conn.close()
        if count == 0:
            # "admin"/"admin" is shorter than MIN_PASSWORD_LENGTH allows for
            # anyone else — it's exempted because force_password_change means
            # it's never actually usable past the first login (§13.6, §13.8).
            self._create_user(
                "admin", "admin", ROLE_ADMIN, force_password_change=True, _skip_password_check=True
            )

    # -- users ---------------------------------------------------------

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        company_name: str | None = None,
        force_password_change: bool = False,
    ) -> User:
        return self._create_user(
            username,
            password,
            role,
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            force_password_change=force_password_change,
        )

    def _create_user(
        self,
        username: str,
        password: str,
        role: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        company_name: str | None = None,
        force_password_change: bool = False,
        _skip_password_check: bool = False,
    ) -> User:
        _validate_username(username)
        if not _skip_password_check:
            _validate_password(password)
        if role not in ROLES:
            raise AuthError(f"unknown role '{role}'")

        password_hash, salt = _hash_password(password)
        now = _now().isoformat()
        conn = self._connect()
        try:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, salt, role, first_name, last_name,
                        company_name, force_password_change, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        username,
                        password_hash,
                        salt,
                        role,
                        first_name,
                        last_name,
                        company_name,
                        int(force_password_change),
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise UserExists(f"user '{username}' already exists") from exc
            conn.commit()
            return User(
                id=cursor.lastrowid,
                username=username,
                role=role,
                first_name=first_name,
                last_name=last_name,
                company_name=company_name,
                force_password_change=force_password_change,
            )
        finally:
            conn.close()

    def get_user(self, username: str) -> User | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        finally:
            conn.close()
        return _row_to_user(row) if row else None

    def list_users(self) -> list[User]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        finally:
            conn.close()
        return [_row_to_user(row) for row in rows]

    def authenticate(self, username: str, password: str) -> User:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if row is None:
                raise InvalidCredentials("invalid username or password")

            if row["locked_until"]:
                locked_until = datetime.fromisoformat(row["locked_until"])
                if _now() < locked_until:
                    raise AccountLocked(locked_until)

            if not _verify_password(password, row["password_hash"], row["salt"]):
                failed = row["failed_attempts"] + 1
                locked_until = None
                if failed >= MAX_FAILED_ATTEMPTS:
                    locked_until = (_now() + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
                    failed = 0
                conn.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ?, updated_at = ? "
                    "WHERE id = ?",
                    (failed, locked_until, _now().isoformat(), row["id"]),
                )
                conn.commit()
                raise InvalidCredentials("invalid username or password")

            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL, updated_at = ? "
                "WHERE id = ?",
                (_now().isoformat(), row["id"]),
            )
            conn.commit()
            return _row_to_user(row)
        finally:
            conn.close()

    def change_password(self, username: str, new_password: str) -> None:
        _validate_password(new_password)
        password_hash, salt = _hash_password(new_password)
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ?, salt = ?, force_password_change = 0, "
                "updated_at = ? WHERE username = ?",
                (password_hash, salt, _now().isoformat(), username),
            )
            if cursor.rowcount == 0:
                raise AuthError(f"no such user '{username}'")
            conn.commit()
        finally:
            conn.close()

    def set_role(self, username: str, role: str) -> None:
        if role not in ROLES:
            raise AuthError(f"unknown role '{role}'")
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE username = ?",
                (role, _now().isoformat(), username),
            )
            if cursor.rowcount == 0:
                raise AuthError(f"no such user '{username}'")
            conn.commit()
        finally:
            conn.close()

    def delete_user(self, username: str) -> None:
        """Generation log entries reference a user_id, not a live User row,
        by design (§13.7 records who/what, not a foreign key an admin
        deleting an old account could break) — but sqlite3 doesn't know
        that from the schema alone, so this only removes the user's own
        auth/group/key rows, never generation_log."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if row is None:
                raise AuthError(f"no such user '{username}'")
            user_id = row["id"]
            conn.execute("DELETE FROM group_members WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()

    # -- groups ----------------------------------------------------------

    def create_group(self, name: str, description: str | None = None) -> Group:
        conn = self._connect()
        try:
            try:
                cursor = conn.execute(
                    "INSERT INTO groups (name, slug, description, created_at) VALUES (?, ?, ?, ?)",
                    (name, _slug(name), description, _now().isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                raise AuthError(f"group '{name}' already exists") from exc
            conn.commit()
            return Group(id=cursor.lastrowid, name=name, slug=_slug(name), description=description)
        finally:
            conn.close()

    def list_groups(self) -> list[Group]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
        finally:
            conn.close()
        return [
            Group(id=r["id"], name=r["name"], slug=r["slug"], description=r["description"])
            for r in rows
        ]

    def assign_user_to_group(
        self, username: str, group_name: str, *, assigned_by: str | None = None
    ) -> None:
        user = self.get_user(username)
        if user is None:
            raise AuthError(f"no such user '{username}'")
        conn = self._connect()
        try:
            group_row = conn.execute(
                "SELECT id FROM groups WHERE name = ?", (group_name,)
            ).fetchone()
            if group_row is None:
                raise AuthError(f"no such group '{group_name}'")
            conn.execute(
                "INSERT OR IGNORE INTO group_members (user_id, group_id, assigned_at, assigned_by) "
                "VALUES (?, ?, ?, ?)",
                (user.id, group_row["id"], _now().isoformat(), assigned_by),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_user_from_group(self, username: str, group_name: str) -> None:
        user = self.get_user(username)
        if user is None:
            raise AuthError(f"no such user '{username}'")
        conn = self._connect()
        try:
            group_row = conn.execute(
                "SELECT id FROM groups WHERE name = ?", (group_name,)
            ).fetchone()
            if group_row is None:
                raise AuthError(f"no such group '{group_name}'")
            conn.execute(
                "DELETE FROM group_members WHERE user_id = ? AND group_id = ?",
                (user.id, group_row["id"]),
            )
            conn.commit()
        finally:
            conn.close()

    def members_of_group(self, group_name: str) -> list[User]:
        conn = self._connect()
        try:
            group_row = conn.execute(
                "SELECT id FROM groups WHERE name = ?", (group_name,)
            ).fetchone()
            if group_row is None:
                raise AuthError(f"no such group '{group_name}'")
            rows = conn.execute(
                """
                SELECT u.* FROM users u
                JOIN group_members gm ON gm.user_id = u.id
                WHERE gm.group_id = ?
                ORDER BY u.username
                """,
                (group_row["id"],),
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_user(row) for row in rows]

    def groups_for_user(self, username: str) -> set[str]:
        user = self.get_user(username)
        if user is None:
            raise AuthError(f"no such user '{username}'")
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT g.name FROM groups g
                JOIN group_members gm ON gm.group_id = g.id
                WHERE gm.user_id = ?
                """,
                (user.id,),
            ).fetchall()
        finally:
            conn.close()
        return {row["name"] for row in rows}

    # -- API keys ----------------------------------------------------------

    def create_api_key(self, username: str, label: str | None = None) -> str:
        """Returns the raw key exactly once — only its SHA-256 hash is stored."""
        user = self.get_user(username)
        if user is None:
            raise AuthError(f"no such user '{username}'")
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO api_keys (user_id, key_hash, label, created_at) VALUES (?, ?, ?, ?)",
                (user.id, key_hash, label, _now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return raw_key

    def verify_api_key(self, raw_key: str) -> User:
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
            if row is None or row["revoked_at"]:
                raise InvalidCredentials("invalid or revoked API key")
            user_row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (row["user_id"],)
            ).fetchone()
        finally:
            conn.close()
        return _row_to_user(user_row)

    def revoke_api_key(self, key_id: int) -> None:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (_now().isoformat(), key_id),
            )
            if cursor.rowcount == 0:
                raise AuthError(f"no active API key with id {key_id}")
            conn.commit()
        finally:
            conn.close()

    def list_api_keys(self, username: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            if username:
                user = self.get_user(username)
                if user is None:
                    raise AuthError(f"no such user '{username}'")
                rows = conn.execute(
                    "SELECT * FROM api_keys WHERE user_id = ? ORDER BY id", (user.id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM api_keys ORDER BY id").fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]

    # -- generation log ----------------------------------------------------

    def record_generation(
        self,
        user: User,
        *,
        schema_id: str,
        schema_version: int,
        form_inputs: dict,
        output_filename: str,
        group_name: str | None = None,
        bulk_batch_id: str | None = None,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO generation_log (
                    user_id, username, group_name, schema_id, schema_version, form_inputs,
                    output_filename, bulk_batch_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username,
                    group_name,
                    schema_id,
                    schema_version,
                    json.dumps(form_inputs, default=str),
                    output_filename,
                    bulk_batch_id,
                    _now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_generation_log(self, user: User) -> list[dict]:
        """Applies §13.7's viewing rule: Config Engineers see their own
        entries only; Template Engineers see their own plus their groups';
        Admins see everything.

        Reads `username` straight off generation_log (a snapshot taken at
        record_generation time), not a join to `users` — the log must
        survive a since-deleted user's account (the same "record the ID,
        not a live reference" principle §13.3 already applies to deleted
        schemas), and user_id has no foreign key for exactly that reason.
        """
        conn = self._connect()
        try:
            if user.is_admin:
                rows = conn.execute("SELECT * FROM generation_log ORDER BY id DESC").fetchall()
            elif user.role == ROLE_TEMPLATE_ENGINEER:
                group_names = self.groups_for_user(user.username)
                placeholders = ",".join("?" * len(group_names)) if group_names else "NULL"
                rows = conn.execute(
                    f"""
                    SELECT * FROM generation_log
                    WHERE user_id = ? OR group_name IN ({placeholders})
                    ORDER BY id DESC
                    """,
                    (user.id, *group_names),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM generation_log WHERE user_id = ? ORDER BY id DESC",
                    (user.id,),
                ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]


def visible_schemas(user: User, schemas: list[Schema], user_groups: set[str]) -> list[Schema]:
    """§13.2/§13.3's scoping rule: which of these schemas can this user see.

    Admins see everything (never assigned to a group; implicit access to
    all). Everyone else sees ungrouped schemas plus schemas in a group
    they're assigned to; Config Engineers additionally never see anything
    but `published` status.
    """
    visible = []
    for schema in schemas:
        if user.is_admin:
            visible.append(schema)
            continue
        if schema.group and schema.group not in user_groups:
            continue
        if user.role == ROLE_CONFIG_ENGINEER and schema.status != "published":
            continue
        visible.append(schema)
    return visible


def require_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise PermissionDenied(f"user '{user.username}' ({user.role}) lacks required role {roles}")
