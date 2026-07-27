from pathlib import Path

from configgen.core.registry import (
    Registry,
    build_registry,
    check_references,
    discover_filters,
    discover_hooks,
    discover_preflight_checks,
    find_orphaned_plugins,
    load_project_filters,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# -- discover_hooks ---------------------------------------------------------


def test_discover_hooks_missing_dir_returns_empty(tmp_path: Path):
    assert discover_hooks(tmp_path / "nope") == {}


def test_discover_hooks_finds_py_files(tmp_path: Path):
    _write(tmp_path / "device_provisioning.py", "def build(v, c, s):\n    return {}\n")
    _write(tmp_path / "other_hook.py", "def build(v, c, s):\n    return {}\n")
    hooks = discover_hooks(tmp_path)
    assert set(hooks) == {"device_provisioning", "other_hook"}
    assert hooks["device_provisioning"] == tmp_path / "device_provisioning.py"


def test_discover_hooks_skips_init(tmp_path: Path):
    _write(tmp_path / "__init__.py", "")
    _write(tmp_path / "real_hook.py", "def build(v, c, s):\n    return {}\n")
    assert set(discover_hooks(tmp_path)) == {"real_hook"}


# -- discover_preflight_checks -----------------------------------------------


def test_discover_preflight_checks_missing_dir_returns_empty(tmp_path: Path):
    assert discover_preflight_checks(tmp_path / "nope") == {}


def test_discover_preflight_checks_only_counts_files_with_check_function(tmp_path: Path):
    _write(tmp_path / "eos.py", "def check(text):\n    return []\n")
    _write(tmp_path / "not_a_checker.py", "x = 1\n")
    checks = discover_preflight_checks(tmp_path)
    assert set(checks) == {"eos"}


# -- load_project_filters / discover_filters ---------------------------------


def test_load_project_filters_missing_file_returns_empty(tmp_path: Path):
    assert load_project_filters(tmp_path) == {}


def test_load_project_filters_returns_callables(tmp_path: Path):
    _write(
        tmp_path / "filters.py",
        "def shout(text):\n    return text.upper()\n\nFILTERS = {'shout': shout}\n",
    )
    filters = load_project_filters(tmp_path)
    assert set(filters) == {"shout"}
    assert filters["shout"]("hi") == "HI"


def test_load_project_filters_missing_filters_dict_returns_empty(tmp_path: Path):
    _write(tmp_path / "filters.py", "def shout(text):\n    return text.upper()\n")
    assert load_project_filters(tmp_path) == {}


def test_discover_filters_maps_names_to_filters_py_path(tmp_path: Path):
    filters_path = _write(
        tmp_path / "filters.py", "def shout(t):\n    return t\n\nFILTERS = {'shout': shout}\n"
    )
    assert discover_filters(tmp_path) == {"shout": filters_path}


# -- build_registry ---------------------------------------------------------


def test_build_registry_combines_all_three(tmp_path: Path):
    _write(tmp_path / "prepare" / "my_hook.py", "def build(v, c, s):\n    return {}\n")
    _write(tmp_path / "preflight" / "eos.py", "def check(t):\n    return []\n")
    _write(tmp_path / "filters.py", "def shout(t):\n    return t\n\nFILTERS = {'shout': shout}\n")

    registry = build_registry(tmp_path)
    assert set(registry.hooks) == {"my_hook"}
    assert set(registry.preflight) == {"eos"}
    assert set(registry.filters) == {"shout"}

    plugins = registry.plugins()
    assert {(p.name, p.kind) for p in plugins} == {
        ("my_hook", "hook"),
        ("eos", "preflight"),
        ("shout", "filter"),
    }


def test_build_registry_empty_project_has_nothing(tmp_path: Path):
    registry = build_registry(tmp_path)
    assert registry.plugins() == []


# -- check_references ---------------------------------------------------------


def _write_schema(schemas_dir: Path, name: str, id_: str, **extra: str) -> Path:
    lines = [f"name: {name}", f"id: {id_}", "version: 1", "status: published"]
    lines += [f"{k}: {v}" for k, v in extra.items()]
    lines += ["template: widget.j2", "fields: []"]
    return _write(schemas_dir / f"{id_}.yaml", "\n".join(lines) + "\n")


def test_check_references_no_issues_when_nothing_declared(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    _write_schema(schemas_dir, "Widget", "widget")
    registry = Registry()
    assert check_references(registry, schemas_dir) == []


def test_check_references_prepare_resolves(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    _write_schema(schemas_dir, "Widget", "widget", prepare="my_hook")
    registry = Registry(hooks={"my_hook": tmp_path / "prepare" / "my_hook.py"})
    assert check_references(registry, schemas_dir) == []


def test_check_references_prepare_missing_reports_issue(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    _write_schema(schemas_dir, "Widget", "widget", prepare="ghost_hook")
    registry = Registry()
    issues = check_references(registry, schemas_dir)
    assert len(issues) == 1
    assert issues[0].schema_id == "widget"
    assert issues[0].field == "prepare"
    assert issues[0].value == "ghost_hook"


def test_check_references_preflight_builtin_resolves_without_custom_check(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    _write_schema(schemas_dir, "Widget", "widget", preflight="ios")
    registry = Registry()  # no custom preflight checks at all
    assert check_references(registry, schemas_dir) == []


def test_check_references_preflight_custom_resolves(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    _write_schema(schemas_dir, "Widget", "widget", preflight="eos")
    registry = Registry(preflight={"eos": tmp_path / "preflight" / "eos.py"})
    assert check_references(registry, schemas_dir) == []


def test_check_references_preflight_unknown_reports_issue(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    _write_schema(schemas_dir, "Widget", "widget", preflight="not-a-platform")
    registry = Registry()
    issues = check_references(registry, schemas_dir)
    assert len(issues) == 1
    assert issues[0].field == "preflight"


# -- find_orphaned_plugins ---------------------------------------------------


def test_find_orphaned_plugins_hook_referenced_is_not_orphan(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    _write_schema(schemas_dir, "Widget", "widget", prepare="my_hook")
    registry = Registry(hooks={"my_hook": tmp_path / "prepare" / "my_hook.py"})
    orphans = find_orphaned_plugins(registry, schemas_dir, templates_dir)
    assert orphans == []


def test_find_orphaned_plugins_unreferenced_hook_is_orphan(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    _write_schema(schemas_dir, "Widget", "widget")  # no prepare:
    registry = Registry(hooks={"unused_hook": tmp_path / "prepare" / "unused_hook.py"})
    orphans = find_orphaned_plugins(registry, schemas_dir, templates_dir)
    assert [o.name for o in orphans] == ["unused_hook"]
    assert orphans[0].kind == "hook"


def test_find_orphaned_plugins_unreferenced_preflight_is_orphan(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    _write_schema(schemas_dir, "Widget", "widget")
    registry = Registry(preflight={"eos": tmp_path / "preflight" / "eos.py"})
    orphans = find_orphaned_plugins(registry, schemas_dir, templates_dir)
    assert [o.name for o in orphans] == ["eos"]


def test_find_orphaned_plugins_filter_used_in_template_is_not_orphan(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    _write_schema(schemas_dir, "Widget", "widget")
    _write(templates_dir / "widget.j2", "{{ name | shout }}")
    registry = Registry(filters={"shout": tmp_path / "filters.py"})
    orphans = find_orphaned_plugins(registry, schemas_dir, templates_dir)
    assert orphans == []


def test_find_orphaned_plugins_unused_filter_is_orphan(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    _write_schema(schemas_dir, "Widget", "widget")
    _write(templates_dir / "widget.j2", "{{ name }}")  # no filter used
    registry = Registry(filters={"shout": tmp_path / "filters.py"})
    orphans = find_orphaned_plugins(registry, schemas_dir, templates_dir)
    assert [o.name for o in orphans] == ["shout"]
    assert orphans[0].kind == "filter"


def test_find_orphaned_plugins_missing_templates_dir_is_fine(tmp_path: Path):
    schemas_dir = tmp_path / "schemas"
    _write_schema(schemas_dir, "Widget", "widget")
    registry = Registry(filters={"shout": tmp_path / "filters.py"})
    orphans = find_orphaned_plugins(registry, schemas_dir, tmp_path / "does-not-exist")
    assert [o.name for o in orphans] == ["shout"]
