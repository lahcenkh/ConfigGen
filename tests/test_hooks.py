from pathlib import Path

import pytest

from configgen.core.db import DatabaseError, NoDatabase
from configgen.hooks import HookError, NetService, Services, load_hook, run_hook


class _FakeDatabase:
    def __init__(self, rows: dict[str, dict]):
        self._rows = rows

    def query(self, query_name, /, **params):
        assert query_name == "device"
        return self._rows.get(params.get("name"))

    def all(self, query_name, /):
        raise AssertionError("not used by this test")


def test_hook_error_carries_field_errors():
    exc = HookError({"device_name": "Unknown device"})
    assert exc.errors == {"device_name": "Unknown device"}
    assert "device_name" in str(exc)


def test_net_service_host_at():
    assert NetService.host_at("10.20.30.0/24", 1) == "10.20.30.1"


def test_net_service_first_usable_and_nexthop():
    assert NetService.first_usable("10.20.30.0/24") == "10.20.30.1"
    assert NetService.nexthop("10.20.30.0/24") == "10.20.30.2"


def test_net_service_netmask_and_prefix():
    assert NetService.netmask("10.20.30.0/24") == "255.255.255.0"
    assert NetService.prefix("10.20.30.0/24") == 24


def test_services_defaults_to_no_database():
    services = Services()
    with pytest.raises(DatabaseError):
        services.db.query("anything")


def test_services_wraps_a_real_database_when_given():
    fake = _FakeDatabase({"edge-01": {"name": "edge-01", "vendor": "Acme"}})
    services = Services(db=fake)
    assert services.db is fake


def test_services_exposes_extra_project_helpers():
    services = Services(extra_helper="hello")
    assert services.extra_helper == "hello"


def test_no_database_raises_clean_error_not_attribute_error():
    stub = NoDatabase()
    with pytest.raises(DatabaseError):
        stub.query("regions")
    with pytest.raises(DatabaseError):
        stub.all("regions")


def test_load_hook_missing_file_raises_hook_error(tmp_path: Path):
    with pytest.raises(HookError):
        load_hook(tmp_path, "does_not_exist")


def test_load_hook_without_build_function_raises_hook_error(tmp_path: Path):
    (tmp_path / "broken.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(HookError):
        load_hook(tmp_path, "broken")


def test_load_hook_returns_callable_build_function(tmp_path: Path):
    (tmp_path / "simple.py").write_text(
        "def build(values, context, services):\n    return {'greeting': 'hi ' + values['name']}\n",
        encoding="utf-8",
    )
    build_fn = load_hook(tmp_path, "simple")
    result = build_fn({"name": "world"}, {}, Services())
    assert result == {"greeting": "hi world"}


def test_run_hook_end_to_end(tmp_path: Path):
    (tmp_path / "device_provisioning.py").write_text(
        "from configgen.hooks import HookError\n"
        "\n"
        "def build(values, context, services):\n"
        "    device = services.db.query('device', name=values['device_name'])\n"
        "    if not device:\n"
        "        raise HookError({'device_name': 'Unknown device'})\n"
        "    return {\n"
        "        'cfg': {\n"
        "            'name': values['device_name'],\n"
        "            'mgmt_ip': services.net.host_at(values['subnet'], 1),\n"
        "            'vendor': device['vendor'],\n"
        "        }\n"
        "    }\n",
        encoding="utf-8",
    )
    fake_db = _FakeDatabase({"edge-01": {"name": "edge-01", "vendor": "Acme Networks"}})
    services = Services(db=fake_db)

    context = run_hook(
        tmp_path,
        "device_provisioning",
        {"device_name": "edge-01", "subnet": "10.20.30.0/24"},
        {"username": "tester"},
        services,
    )
    assert context == {
        "cfg": {"name": "edge-01", "mgmt_ip": "10.20.30.1", "vendor": "Acme Networks"}
    }


def test_run_hook_propagates_hook_error(tmp_path: Path):
    (tmp_path / "device_provisioning.py").write_text(
        "from configgen.hooks import HookError\n"
        "\n"
        "def build(values, context, services):\n"
        "    device = services.db.query('device', name=values['device_name'])\n"
        "    if not device:\n"
        "        raise HookError({'device_name': 'Unknown device'})\n"
        "    return {}\n",
        encoding="utf-8",
    )
    services = Services(db=_FakeDatabase({}))
    with pytest.raises(HookError):
        run_hook(
            tmp_path,
            "device_provisioning",
            {"device_name": "ghost", "subnet": "10.20.30.0/24"},
            {},
            services,
        )
