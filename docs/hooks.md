# Hooks (Tier 2)

Most configs only need Tier 1: a schema's fields, validated, become the
template context directly. A **hook** is Tier 2, for the configs
that need more — a value looked up from a database, an address derived
from a subnet, a submission rejected for a reason no single field's
`pattern:` can express. It's one Python file, pure and unit-testable in
isolation, that runs between validation and rendering:

```text
form input -> Tier 1 validate (schema fields) -> [Tier 2: hook] -> render -> save + log
```

## Wiring one up

1. Add `hook: <name>` to the schema.
2. Write `<name>.py` in the project's `hooks/` folder (a sibling of
   `schemas/`, `templates/`, and `data/` — the same "resolved from the
   schema's own path" layout as everything else, see
   [schema-reference.md](schema-reference.md#file-layout)).
3. Define a `build()` function in it:

```python
def build(values: dict, context: dict, services) -> dict:
    ...
    return template_context  # a dict, passed straight to the template
```

- **`values`** — the Tier-1-validated, typed field values (same shape
  Tier 1 would hand a template directly if there were no hook).
- **`context`** — currently just `{"username": "<the generating user>"}`.
- **`services`** — a `Services` object: `services.db` and `services.net`,
  see below.
- **Return value** becomes the template's entire context — a hook can
  pass values through unchanged, add to them, or replace them
  completely (`examples/hooks/device_provisioning.py` below returns a
  single `cfg` dict, so its template reads `{{ cfg.name }}`, not
  `{{ device_name }}`).

Reject the submission by raising `HookError`, in the same
`{field_key: message}` shape a Tier 1 validation failure uses — the GUI
paints it on the same field, the CLI prints it the same way:

```python
from configgen.hooks import HookError

def build(values, context, services):
    if not looks_right(values["device_name"]):
        raise HookError({"device_name": "not a recognized device"})
    ...
```

Anything else the hook raises is **not** caught — a bug in a hook
produces a real traceback, not a swallowed error, because hooks are
plain Python, never sandboxed.

## A full example

`examples/schemas/device_provisioning.yaml` declares `hook:
device_provisioning`, taking just a `device_name` and a `subnet` from
the form. `examples/hooks/device_provisioning.py`:

```python
from configgen.hooks import HookError


def build(values: dict, context: dict, services) -> dict:
    device = services.db.query("device", name=values["device_name"])
    if not device:
        raise HookError({"device_name": f"Unknown device '{values['device_name']}'"})

    return {
        "cfg": {
            "name": values["device_name"],
            "mgmt_ip": services.net.host_at(values["subnet"], 1),
            "vendor": device["vendor"],
        }
    }
```

`examples/templates/device_provisioning.j2` then reads `{{ cfg.name }}`,
`{{ cfg.vendor }}`, `{{ cfg.mgmt_ip }}` — none of which is a form field;
all three are the hook's own construction. Run it:

```bash
configgen generate examples/schemas/device_provisioning.yaml \
  --values examples/sample_device_provisioning_values.json --output /tmp/out
```

Because `check`'s declarative variable-mismatch warning can't see inside
a hook (it only knows form fields), **hook-driven schemas are
excluded from that warning entirely** — `cfg.name` would otherwise look
like an undeclared variable. This is advisory-only in both directions:
`check` genuinely can't verify a hook's output matches what the template
expects, only a real render (`configgen generate`, or the GUI's **Test
Render**) can.

## `services.db` and `queries.yaml`

`services.db` is a generic, read-only SQL layer — never an ORM, never
schema-aware — backed by the project's `data/queries.yaml`:

```yaml
database: sample.db          # path, relative to queries.yaml itself
queries:
  regions:
    sql: "SELECT DISTINCT region FROM sites ORDER BY region"
    returns: scalar_list      # -> ["eu-central", "us-east", "us-west"]
  device:
    sql: "SELECT * FROM devices WHERE name = :name"
    returns: row               # -> {"name": ..., "vendor": ...} or None
  devices_by_site:
    sql: "SELECT * FROM devices WHERE site = :site"
    returns: rows               # -> [{"name": ..., ...}, ...]
```

Querying more than one SQLite file? Replace `database:` with `databases:`
(a mapping of alias to path) and give every query a `use:` naming which
one it runs against — required as soon as there's more than one:

```yaml
databases:
  inv: inventory.db
  dev: devices.db
queries:
  regions:
    use: inv
    sql: "SELECT DISTINCT region FROM sites ORDER BY region"
    returns: scalar_list
  device:
    use: dev
    sql: "SELECT * FROM devices WHERE name = :name"
    returns: row
```

`returns:` shapes the result: `scalar_list` (first column of every row,
flattened — what `choice`/`lookup` `from_db` fields consume directly),
`row` (a single dict, or `None` if no match), or `rows` (a list of
dicts, the default). Bind parameters use sqlite3's named-parameter
syntax (`:name`) inside the SQL, passed as keyword arguments:

```python
services.db.query("device", name=values["device_name"])   # -> a dict, or None
services.db.all("regions")                                  # -> a list
```

Every call opens its own SQLite connection and closes it before
returning — a project with no `data/queries.yaml` at all just gets
`NoDatabase()` in its place, which raises a clean `DatabaseError` only
if a hook actually calls `.query()`/`.all()` on it (a hook that never
touches the database works fine in a project that has none).

Check that every declared query still runs cleanly (with null
parameters) after editing `queries.yaml`:

```bash
configgen db check --queries resources/data/queries.yaml
```

## `services.net`

Stateless subnet/address helpers, so a hook never has to re-derive
address arithmetic by hand — thin wrappers over the same typed values
[schema-reference.md](schema-reference.md#field-types) documents for
`network`/`ip_cidr` fields:

| Call | Returns |
|---|---|
| `services.net.host_at(network, offset)` | the address `offset` positions past the network address |
| `services.net.first_usable(network)` | the first usable host address |
| `services.net.nexthop(network)` | the second usable host — the conventional gateway address |
| `services.net.netmask(network)` | the dotted netmask |
| `services.net.prefix(network)` | the prefix length, as an int |

`network` can be a plain string (`"10.20.30.0/24"`) or an already-typed
`network`-field value — both work, since these just wrap
`core.values.NetworkValue` for you.

## Custom filters

A project can register its own Jinja filters in a sibling `filters.py`,
auto-discovered by the renderer — no registration step, no core change:

```python
# filters.py
def to_wildcard(netmask: str) -> str:
    """255.255.255.0 -> 0.0.0.255 - the inverse mask an OSPF `network`
    statement expects."""
    ...

FILTERS = {
    "to_wildcard": to_wildcard,
}
```

Every name in `FILTERS` becomes usable in any template in that project:

```jinja
network {{ mgmt_ip.ip }} {{ mgmt_ip.netmask | to_wildcard }} area {{ ospf_area }}
```

See `examples/filters.py` and its use in
`examples/templates/router_base_config.j2`.

## Testing a hook

A hook is a plain function — test it directly, no ConfigGen scaffolding
needed:

```python
from configgen.hooks import HookError, Services
from examples.hooks.device_provisioning import build

def test_build_derives_management_ip():
    services = Services(db=fake_db_with_one_device())
    result = build({"device_name": "edge-01", "subnet": "10.20.30.0/24"}, {}, services)
    assert result["cfg"]["mgmt_ip"] == "10.20.30.1"

def test_build_rejects_unknown_device():
    services = Services(db=fake_db_with_no_devices())
    try:
        build({"device_name": "ghost-01", "subnet": "10.20.30.0/24"}, {}, services)
        assert False, "expected HookError"
    except HookError as exc:
        assert "device_name" in exc.errors
```
