from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from configgen.core import auth as auth_module
from configgen.core.auth import (
    ROLE_ADMIN,
    ROLE_CONFIG_ENGINEER,
    ROLE_TEMPLATE_ENGINEER,
    AccountLocked,
    AuthError,
    AuthStore,
    InvalidCredentials,
    PermissionDenied,
    UserExists,
    require_role,
    visible_schemas,
)
from configgen.core.schema import Schema


def _store(tmp_path: Path) -> AuthStore:
    return AuthStore(tmp_path / "users.db")


def _schema(**overrides) -> Schema:
    defaults = dict(name="Widget", id="widget", fields=[], template="widget.j2")
    defaults.update(overrides)
    return Schema(**defaults)


# -- bootstrap ---------------------------------------------------------


def test_fresh_store_bootstraps_admin_admin(tmp_path: Path):
    store = _store(tmp_path)
    admin = store.get_user("admin")
    assert admin is not None
    assert admin.role == ROLE_ADMIN
    assert admin.force_password_change is True
    # the bootstrap password really is "admin"
    authenticated = store.authenticate("admin", "admin")
    assert authenticated.username == "admin"


def test_bootstrap_does_not_duplicate_admin_on_reopen(tmp_path: Path):
    db_path = tmp_path / "users.db"
    AuthStore(db_path)
    AuthStore(db_path)
    store = AuthStore(db_path)
    assert [u.username for u in store.list_users()].count("admin") == 1


# -- create_user ---------------------------------------------------------


def test_create_user_success(tmp_path: Path):
    store = _store(tmp_path)
    user = store.create_user("alice", "hunter22", ROLE_CONFIG_ENGINEER)
    assert user.username == "alice"
    assert user.role == ROLE_CONFIG_ENGINEER
    assert store.get_user("alice") is not None


def test_create_user_rejects_bad_username(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(AuthError):
        store.create_user("Alice Smith", "hunter22", ROLE_CONFIG_ENGINEER)


def test_create_user_rejects_short_password(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(AuthError):
        store.create_user("alice", "short", ROLE_CONFIG_ENGINEER)


def test_create_user_rejects_unknown_role(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(AuthError):
        store.create_user("alice", "hunter22", "superuser")


def test_create_user_duplicate_raises(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("alice", "hunter22", ROLE_CONFIG_ENGINEER)
    with pytest.raises(UserExists):
        store.create_user("alice", "hunter22", ROLE_CONFIG_ENGINEER)


# -- authenticate / lockout -----------------------------------------------


def test_authenticate_wrong_password_raises(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("alice", "hunter22", ROLE_CONFIG_ENGINEER)
    with pytest.raises(InvalidCredentials):
        store.authenticate("alice", "wrong-password")


def test_authenticate_unknown_user_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(InvalidCredentials):
        store.authenticate("ghost", "whatever1")


def test_lockout_after_five_failed_attempts(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("alice", "hunter22", ROLE_CONFIG_ENGINEER)
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            store.authenticate("alice", "wrong-password")
    # 6th attempt, even with the *correct* password, is locked out
    with pytest.raises(AccountLocked):
        store.authenticate("alice", "hunter22")


def test_lockout_expires_after_window(tmp_path: Path, monkeypatch):
    store = _store(tmp_path)
    store.create_user("alice", "hunter22", ROLE_CONFIG_ENGINEER)
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            store.authenticate("alice", "wrong-password")

    future = datetime.now(timezone.utc) + timedelta(minutes=16)
    monkeypatch.setattr(auth_module, "_now", lambda: future)
    # lockout window has passed - correct password now succeeds
    user = store.authenticate("alice", "hunter22")
    assert user.username == "alice"


def test_successful_login_resets_failed_attempts(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("alice", "hunter22", ROLE_CONFIG_ENGINEER)
    for _ in range(3):
        with pytest.raises(InvalidCredentials):
            store.authenticate("alice", "wrong-password")
    store.authenticate("alice", "hunter22")
    # three more failures shouldn't be enough to lock out post-reset
    for _ in range(3):
        with pytest.raises(InvalidCredentials):
            store.authenticate("alice", "wrong-password")
    store.authenticate("alice", "hunter22")  # would raise AccountLocked if not reset


def test_change_password_clears_force_flag_and_updates_hash(tmp_path: Path):
    store = _store(tmp_path)
    store.change_password("admin", "newpassword1")
    admin = store.get_user("admin")
    assert admin.force_password_change is False
    assert store.authenticate("admin", "newpassword1").username == "admin"
    with pytest.raises(InvalidCredentials):
        store.authenticate("admin", "admin")


def test_set_role_changes_a_users_role(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    store.set_role("carol", ROLE_TEMPLATE_ENGINEER)
    assert store.get_user("carol").role == ROLE_TEMPLATE_ENGINEER


def test_set_role_rejects_unknown_role(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    with pytest.raises(AuthError):
        store.set_role("carol", "superuser")


def test_set_role_unknown_user_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(AuthError):
        store.set_role("ghost", ROLE_ADMIN)


def test_delete_user_removes_the_account(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    store.delete_user("carol")
    assert store.get_user("carol") is None
    with pytest.raises(InvalidCredentials):
        store.authenticate("carol", "hunter22pw")


def test_delete_user_also_removes_group_memberships_and_api_keys(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    store.create_group("Acme Corp")
    store.assign_user_to_group("carol", "Acme Corp")
    store.create_api_key("carol", label="test")

    store.delete_user("carol")

    assert store.members_of_group("Acme Corp") == []
    assert store.list_api_keys() == []


def test_delete_user_preserves_generation_log_entries(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    carol = store.get_user("carol")
    store.record_generation(
        carol, schema_id="widget", schema_version=1, form_inputs={}, output_filename="a.txt"
    )

    store.delete_user("carol")

    admin = store.get_user("admin")
    entries = store.list_generation_log(admin)
    assert len(entries) == 1
    assert entries[0]["output_filename"] == "a.txt"


def test_delete_unknown_user_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(AuthError):
        store.delete_user("ghost")


# -- groups ----------------------------------------------------------------


def test_create_and_list_groups(tmp_path: Path):
    store = _store(tmp_path)
    store.create_group("Acme Corp", description="Acme's templates")
    names = [g.name for g in store.list_groups()]
    assert names == ["Acme Corp"]


def test_duplicate_group_raises(tmp_path: Path):
    store = _store(tmp_path)
    store.create_group("Acme Corp")
    with pytest.raises(AuthError):
        store.create_group("Acme Corp")


def test_assign_user_to_group_and_query(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    store.create_group("Acme Corp")
    store.assign_user_to_group("carol", "Acme Corp", assigned_by="admin")
    assert store.groups_for_user("carol") == {"Acme Corp"}


def test_assign_to_unknown_group_raises(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    with pytest.raises(AuthError):
        store.assign_user_to_group("carol", "Ghost Group")


def test_assign_unknown_user_raises(tmp_path: Path):
    store = _store(tmp_path)
    store.create_group("Acme Corp")
    with pytest.raises(AuthError):
        store.assign_user_to_group("ghost", "Acme Corp")


def test_user_can_belong_to_multiple_groups(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    store.create_group("Acme Corp")
    store.create_group("Beta Industries")
    store.assign_user_to_group("carol", "Acme Corp")
    store.assign_user_to_group("carol", "Beta Industries")
    assert store.groups_for_user("carol") == {"Acme Corp", "Beta Industries"}


def test_remove_user_from_group(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    store.create_group("Acme Corp")
    store.assign_user_to_group("carol", "Acme Corp")

    store.remove_user_from_group("carol", "Acme Corp")

    assert store.groups_for_user("carol") == set()


def test_remove_from_group_unknown_group_raises(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    with pytest.raises(AuthError):
        store.remove_user_from_group("carol", "Ghost Group")


def test_members_of_group(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22pw", ROLE_CONFIG_ENGINEER)
    store.create_user("dave", "hunter22pw", ROLE_CONFIG_ENGINEER)
    store.create_group("Acme Corp")
    store.assign_user_to_group("carol", "Acme Corp")

    members = store.members_of_group("Acme Corp")

    assert [m.username for m in members] == ["carol"]


def test_members_of_unknown_group_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(AuthError):
        store.members_of_group("Ghost Group")


# -- API keys ----------------------------------------------------------------


def test_create_and_verify_api_key(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    raw_key = store.create_api_key("carol", label="CI pipeline")
    user = store.verify_api_key(raw_key)
    assert user.username == "carol"


def test_verify_unknown_api_key_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(InvalidCredentials):
        store.verify_api_key("not-a-real-key")


def test_revoked_api_key_fails_verification(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    raw_key = store.create_api_key("carol")
    [key_row] = store.list_api_keys("carol")
    store.revoke_api_key(key_row["id"])
    with pytest.raises(InvalidCredentials):
        store.verify_api_key(raw_key)


def test_revoke_unknown_key_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(AuthError):
        store.revoke_api_key(9999)


def test_list_api_keys_filters_by_user(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    store.create_user("dave", "hunter22", ROLE_CONFIG_ENGINEER)
    store.create_api_key("carol", label="a")
    store.create_api_key("dave", label="b")
    assert len(store.list_api_keys("carol")) == 1
    assert len(store.list_api_keys()) == 2


# -- generation log ----------------------------------------------------------


def test_record_and_list_generation_log_for_admin(tmp_path: Path):
    store = _store(tmp_path)
    admin = store.get_user("admin")
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    carol = store.get_user("carol")
    store.record_generation(
        admin,
        schema_id="widget",
        schema_version=1,
        form_inputs={"x": "1"},
        output_filename="widget.txt",
    )
    store.record_generation(
        carol,
        schema_id="widget",
        schema_version=1,
        form_inputs={"x": "2"},
        output_filename="widget2.txt",
        group_name="Acme Corp",
    )
    entries = store.list_generation_log(admin)
    assert len(entries) == 2  # admin sees everything


def test_config_engineer_sees_only_own_log_entries(tmp_path: Path):
    store = _store(tmp_path)
    admin = store.get_user("admin")
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    store.create_user("dave", "hunter22", ROLE_CONFIG_ENGINEER)
    carol = store.get_user("carol")
    dave = store.get_user("dave")
    store.record_generation(
        carol, schema_id="widget", schema_version=1, form_inputs={}, output_filename="a.txt"
    )
    store.record_generation(
        dave, schema_id="widget", schema_version=1, form_inputs={}, output_filename="b.txt"
    )
    entries = store.list_generation_log(carol)
    assert len(entries) == 1
    assert entries[0]["username"] == "carol"
    assert admin  # keep reference, unused otherwise


def test_template_engineer_sees_own_and_group_entries(tmp_path: Path):
    store = _store(tmp_path)
    store.create_user("bob", "hunter22", ROLE_TEMPLATE_ENGINEER)
    store.create_user("carol", "hunter22", ROLE_CONFIG_ENGINEER)
    store.create_user("dave", "hunter22", ROLE_CONFIG_ENGINEER)
    store.create_group("Acme Corp")
    store.create_group("Beta Industries")
    store.assign_user_to_group("bob", "Acme Corp")
    store.assign_user_to_group("carol", "Acme Corp")
    store.assign_user_to_group("dave", "Beta Industries")
    bob = store.get_user("bob")
    carol = store.get_user("carol")
    dave = store.get_user("dave")

    store.record_generation(
        carol,
        schema_id="widget",
        schema_version=1,
        form_inputs={},
        output_filename="a.txt",
        group_name="Acme Corp",
    )
    store.record_generation(
        dave,
        schema_id="widget",
        schema_version=1,
        form_inputs={},
        output_filename="b.txt",
        group_name="Beta Industries",
    )

    entries = store.list_generation_log(bob)
    assert {e["username"] for e in entries} == {"carol"}


# -- visible_schemas ---------------------------------------------------------


def test_admin_sees_every_schema_regardless_of_group_or_status():
    admin_user = auth_module.User(id=1, username="admin", role=ROLE_ADMIN)
    schemas = [
        _schema(id="a", group="Acme", status="draft"),
        _schema(id="b", group="Beta", status="deprecated"),
        _schema(id="c", group=None, status="published"),
    ]
    assert visible_schemas(admin_user, schemas, user_groups=set()) == schemas


def test_config_engineer_sees_only_published_in_own_groups_or_ungrouped():
    ce = auth_module.User(id=2, username="carol", role=ROLE_CONFIG_ENGINEER)
    schemas = [
        _schema(id="published_in_group", group="Acme", status="published"),
        _schema(id="draft_in_group", group="Acme", status="draft"),
        _schema(id="published_other_group", group="Beta", status="published"),
        _schema(id="published_ungrouped", group=None, status="published"),
    ]
    result = visible_schemas(ce, schemas, user_groups={"Acme"})
    assert {s.id for s in result} == {"published_in_group", "published_ungrouped"}


def test_template_engineer_sees_draft_and_deprecated_in_own_groups():
    te = auth_module.User(id=3, username="bob", role=ROLE_TEMPLATE_ENGINEER)
    schemas = [
        _schema(id="draft_in_group", group="Acme", status="draft"),
        _schema(id="deprecated_in_group", group="Acme", status="deprecated"),
        _schema(id="published_other_group", group="Beta", status="published"),
    ]
    result = visible_schemas(te, schemas, user_groups={"Acme"})
    assert {s.id for s in result} == {"draft_in_group", "deprecated_in_group"}


def test_ungrouped_schema_visible_to_everyone():
    ce = auth_module.User(id=2, username="carol", role=ROLE_CONFIG_ENGINEER)
    schemas = [_schema(id="shared", group=None, status="published")]
    assert visible_schemas(ce, schemas, user_groups=set()) == schemas


# -- require_role ---------------------------------------------------------


def test_require_role_passes_when_matching():
    admin_user = auth_module.User(id=1, username="admin", role=ROLE_ADMIN)
    require_role(admin_user, ROLE_ADMIN)  # no exception


def test_require_role_raises_when_not_matching():
    ce = auth_module.User(id=2, username="carol", role=ROLE_CONFIG_ENGINEER)
    with pytest.raises(PermissionDenied):
        require_role(ce, ROLE_ADMIN)
