import sqlite3
from pathlib import Path

import pytest
import yaml

from configgen.core.db import Database, DatabaseError, health_check, load_queries


def _build_sample_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE sites (region TEXT NOT NULL);
        CREATE TABLE devices (name TEXT NOT NULL, site TEXT NOT NULL);
        """)
    conn.executemany("INSERT INTO sites (region) VALUES (?)", [("us-east",), ("us-west",)])
    conn.executemany(
        "INSERT INTO devices (name, site) VALUES (?, ?)",
        [("edge-01", "us-east"), ("edge-02", "us-west")],
    )
    conn.commit()
    conn.close()


QUERIES_YAML = {
    "database": "sample.db",
    "queries": {
        "regions": {
            "sql": "SELECT DISTINCT region FROM sites ORDER BY region",
            "returns": "scalar_list",
        },
        "device_names": {
            "sql": "SELECT name FROM devices ORDER BY name",
            "returns": "scalar_list",
        },
        "device": {"sql": "SELECT * FROM devices WHERE name = :name", "returns": "row"},
        "devices_by_site": {"sql": "SELECT * FROM devices WHERE site = :site", "returns": "rows"},
    },
}


def _write_project(tmp_path: Path) -> Path:
    _build_sample_db(tmp_path / "sample.db")
    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(yaml.dump(QUERIES_YAML), encoding="utf-8")
    return queries_path


def test_load_queries_resolves_db_path_relative_to_yaml(tmp_path: Path):
    queries_path = _write_project(tmp_path)
    databases, queries = load_queries(queries_path)
    assert databases == {"default": tmp_path / "sample.db"}
    assert set(queries) == {"regions", "device_names", "device", "devices_by_site"}
    assert all(q.use == "default" for q in queries.values())


def test_load_queries_missing_database_key_raises(tmp_path: Path):
    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(yaml.dump({"queries": {}}), encoding="utf-8")
    with pytest.raises(DatabaseError):
        load_queries(queries_path)


# -- multiple databases (`databases:` + per-query `use:`) -------------------


def _write_multi_db_project(tmp_path: Path) -> Path:
    _build_sample_db(tmp_path / "inventory.db")
    conn = sqlite3.connect(tmp_path / "devices.db")
    conn.executescript("CREATE TABLE devices (name TEXT NOT NULL, vendor TEXT NOT NULL);")
    conn.execute("INSERT INTO devices (name, vendor) VALUES ('edge-01', 'Acme')")
    conn.commit()
    conn.close()

    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(
        yaml.dump(
            {
                "databases": {"inv": "inventory.db", "dev": "devices.db"},
                "queries": {
                    "regions": {
                        "use": "inv",
                        "sql": "SELECT DISTINCT region FROM sites ORDER BY region",
                        "returns": "scalar_list",
                    },
                    "device": {
                        "use": "dev",
                        "sql": "SELECT * FROM devices WHERE name = :name",
                        "returns": "row",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return queries_path


def test_load_queries_resolves_multiple_database_paths(tmp_path: Path):
    queries_path = _write_multi_db_project(tmp_path)
    databases, queries = load_queries(queries_path)
    assert databases == {"inv": tmp_path / "inventory.db", "dev": tmp_path / "devices.db"}
    assert queries["regions"].use == "inv"
    assert queries["device"].use == "dev"


def test_database_query_routes_to_the_right_database(tmp_path: Path):
    database = Database.from_queries_file(_write_multi_db_project(tmp_path))
    assert database.query("regions") == ["us-east", "us-west"]
    assert database.query("device", name="edge-01") == {"name": "edge-01", "vendor": "Acme"}


def test_load_queries_query_without_use_and_multiple_databases_raises(tmp_path: Path):
    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(
        yaml.dump(
            {
                "databases": {"inv": "inventory.db", "dev": "devices.db"},
                "queries": {"regions": {"sql": "SELECT 1", "returns": "scalar_list"}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DatabaseError):
        load_queries(queries_path)


def test_load_queries_unknown_use_raises(tmp_path: Path):
    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(
        yaml.dump(
            {
                "databases": {"inv": "inventory.db"},
                "queries": {
                    "regions": {"use": "ghost", "sql": "SELECT 1", "returns": "scalar_list"}
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DatabaseError):
        load_queries(queries_path)


def test_load_queries_both_database_and_databases_raises(tmp_path: Path):
    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(
        yaml.dump({"database": "sample.db", "databases": {"inv": "inventory.db"}, "queries": {}}),
        encoding="utf-8",
    )
    with pytest.raises(DatabaseError):
        load_queries(queries_path)


def test_load_queries_databases_must_be_a_non_empty_mapping(tmp_path: Path):
    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(yaml.dump({"databases": {}, "queries": {}}), encoding="utf-8")
    with pytest.raises(DatabaseError):
        load_queries(queries_path)


def test_database_query_scalar_list(tmp_path: Path):
    database = Database.from_queries_file(_write_project(tmp_path))
    assert database.query("regions") == ["us-east", "us-west"]


def test_database_query_row_with_bound_param(tmp_path: Path):
    database = Database.from_queries_file(_write_project(tmp_path))
    row = database.query("device", name="edge-01")
    assert row == {"name": "edge-01", "site": "us-east"}


def test_database_query_row_no_match_returns_none(tmp_path: Path):
    database = Database.from_queries_file(_write_project(tmp_path))
    assert database.query("device", name="does-not-exist") is None


def test_database_query_rows(tmp_path: Path):
    database = Database.from_queries_file(_write_project(tmp_path))
    rows = database.query("devices_by_site", site="us-east")
    assert rows == [{"name": "edge-01", "site": "us-east"}]


def test_database_all_runs_query_with_no_params(tmp_path: Path):
    database = Database.from_queries_file(_write_project(tmp_path))
    assert database.all("device_names") == ["edge-01", "edge-02"]


def test_query_name_positional_never_collides_with_a_name_bind_param(tmp_path: Path):
    # Regression test: `query`'s own identifier used to be a keyword
    # parameter called `name`, which collided with SQL bind parameters also
    # called `:name` (a very common name, and the plan's own example).
    database = Database.from_queries_file(_write_project(tmp_path))
    assert database.query("device", name="edge-02") == {"name": "edge-02", "site": "us-west"}


def test_unknown_query_raises_database_error(tmp_path: Path):
    database = Database.from_queries_file(_write_project(tmp_path))
    with pytest.raises(DatabaseError):
        database.query("does_not_exist")


def test_missing_database_file_raises_database_error(tmp_path: Path):
    queries_path = tmp_path / "queries.yaml"
    queries_path.write_text(yaml.dump(QUERIES_YAML), encoding="utf-8")
    # Note: no sample.db written this time.
    database = Database.from_queries_file(queries_path)
    with pytest.raises(DatabaseError):
        database.query("regions")


def test_connection_is_closed_after_each_call(tmp_path: Path):
    # The Windows file-lock fix (§19): nothing should keep a handle open
    # between calls, so the db file can be deleted/replaced afterward.
    queries_path = _write_project(tmp_path)
    database = Database.from_queries_file(queries_path)
    database.query("regions")
    (tmp_path / "sample.db").unlink()  # would fail on Windows if still locked
    assert not (tmp_path / "sample.db").exists()


def test_health_check_all_ok(tmp_path: Path):
    database = Database.from_queries_file(_write_project(tmp_path))
    results = health_check(database)
    assert all(r.ok for r in results)
    assert {r.name for r in results} == {"regions", "device_names", "device", "devices_by_site"}


def test_health_check_reports_failure_for_bad_sql(tmp_path: Path):
    queries_path = tmp_path / "queries.yaml"
    _build_sample_db(tmp_path / "sample.db")
    bad = {
        "database": "sample.db",
        "queries": {"broken": {"sql": "SELECT * FROM no_such_table", "returns": "rows"}},
    }
    queries_path.write_text(yaml.dump(bad), encoding="utf-8")
    database = Database.from_queries_file(queries_path)

    results = health_check(database)
    assert len(results) == 1
    assert results[0].ok is False
    assert "broken" in [r.name for r in results]
    assert results[0].message
