# Adding a config

Every config in ConfigGen is three files, at most:

```text
resources/schemas/<id>.yaml     # required - the form + metadata
resources/templates/<id>.j2     # required - the Jinja2 output
resources/hooks/<id>.py         # optional - a build() hook for derived/DB-backed values
```

Nothing else changes. No core code, no registration step, no restart —
`configgen list` and the GUI dashboard both re-scan `resources/schemas/`
every time.

This doc walks through three real, runnable examples, each one step up in
complexity: **form-only**, **multi-document**, and **DB-backed**. All
three live in `examples/` and you can run every command below yourself.
For the fourth kind — a *derived* config, where a Python hook computes
values instead of a form field — see
[hooks.md](hooks.md). For generating many configs from a
CSV or a database query instead of typing one form at a time, see
[bulk-generation.md](bulk-generation.md). For every field type and schema
option in detail, see [schema-reference.md](schema-reference.md).

## 1. Form-only: `router_base_config`

The simplest shape: one schema, one template, no database, no hook.
`examples/schemas/router_base_config.yaml`:

```yaml
name: "Generic Router Base Config"
id: router_base_config
version: 1
status: published
identity_field: hostname
comment_prefix: "!"
template: router_base_config.j2
fields:
  - key: hostname
    label: "Hostname"
    type: string
    required: true
    pattern: '^[a-z0-9-]{1,63}$'
    example: "rtr-core-01"
  - key: mgmt_ip
    label: "Management IP"
    type: ip_cidr
    required: true
  - key: enable_ospf
    label: "Enable OSPF"
    type: bool
    default: true
  - key: ospf_process_id
    label: "OSPF process ID"
    type: int
    required_if: {enable_ospf: true}
  # ...
```

`template:` points at `resources/templates/router_base_config.j2` (a
schema and its template share a directory, resolved as siblings — see
[schema-reference.md](schema-reference.md) for the exact layout rule).
The template is plain Jinja2, referencing the schema's field keys. An
`ip_cidr` field renders as an object with `.ip`/`.netmask` attributes
(see [schema-reference.md](schema-reference.md#field-types) for what
each field type gives a template); `to_wildcard` here is a custom filter
the project supplies itself in a sibling `filters.py`
(`examples/filters.py` — see [hooks.md](hooks.md#custom-filters)):

```jinja
hostname {{ hostname }}
!
interface {{ mgmt_interface }}
 ip address {{ mgmt_ip.ip }} {{ mgmt_ip.netmask }}
 no shutdown
!
{% if enable_ospf %}
router ospf {{ ospf_process_id }}
 network {{ mgmt_ip.ip }} {{ mgmt_ip.netmask | to_wildcard }} area {{ ospf_area }}
{% endif %}
```

Validate, then generate:

```bash
configgen check examples/schemas/router_base_config.yaml
configgen generate examples/schemas/router_base_config.yaml \
  --values examples/sample_router_values.json --output /tmp/out
```

`check` runs the same structural validation the GUI's template editor's
**Check** button does (§2.6): field types are real, regex patterns
compile, `required_if`/`visible_if` reference real fields, the template
file exists. It also warns (never blocks) if the template references a
variable no field or hook supplies — the same check as the editor's
**Extract Variables** button.

### Writing the template first

You don't have to design the schema before the template. If you already
have a working config file, save it as `<id>.j2`, mark the parts that
vary with `{{ field_name }}`, then let ConfigGen infer the schema:

```bash
configgen extract path/to/switch_base.j2              # lists the variables it found
configgen extract path/to/switch_base.j2 --scaffold    # prints a starter schema YAML
```

`--scaffold` guesses a field type per variable from its name (`_ip` →
`ip`, `_id`/`_number` → `int`, everything else → `string`) and gives
every field a `Title Case` label — a starting point to refine, not a
finished schema. Redirect it straight into place:

```bash
configgen extract templates/switch_base.j2 --scaffold > resources/schemas/switch_base.yaml
```

## 2. Multi-document: `ha_pair_config`

One form, two related outputs — `examples/schemas/ha_pair_config.yaml`
fills in both nodes of an HA pair from one set of shared values (VLAN,
subnet, virtual IP) plus each node's own IP:

```yaml
name: "HA Pair Base Config"
id: ha_pair_config
identity_field: pair_name
documents:
  - key: primary
    label: "Primary Node"
    template: ha_pair_primary.j2
  - key: backup
    label: "Backup Node"
    template: ha_pair_backup.j2
fields:
  - key: pair_name
    type: string
    required: true
  - key: subnet
    type: network
    required: true
  - key: primary_ip
    type: ip
    required: true
  - key: backup_ip
    type: ip
    required: true
  # ...
```

A schema declares **either** `template:` (one output) **or**
`documents:` (two or more) — never both, never neither; `check` rejects
a schema that gets this wrong. Each document is rendered from the same
validated field values, so `ha_pair_primary.j2` and `ha_pair_backup.j2`
both reference `subnet`/`vrrp_vip`/etc., but each also uses its own half
of the pair (`primary_ip` vs. `backup_ip`).

```bash
configgen generate examples/schemas/ha_pair_config.yaml \
  --values examples/sample_ha_pair_values.json --output /tmp/out
```

This writes two `.txt` files (one per document) plus one shared `.json`
profile recording the inputs that produced both — reopening either file
later reopens the same profile, per document key.

## 3. DB-backed: `device_onboarding`

A field's options can come from a database instead of a fixed list.
`examples/schemas/device_onboarding.yaml`:

```yaml
name: "Device Onboarding Record"
id: device_onboarding
template: device_onboarding.j2
fields:
  - key: region
    type: choice
    from_db: {query: regions}
  - key: device_name
    type: lookup
    from_db: {query: device_names}
    help: "Autocompletes from the device inventory; free text is still accepted."
  - key: asset_tag
    type: string
    pattern: '^[A-Z]{2}-\d{4,8}$'
```

`from_db` names a query declared in the project's sibling
`resources/data/queries.yaml` (here, `examples/data/queries.yaml`,
pointed at `examples/data/sample.db`):

```yaml
database: sample.db
queries:
  regions:
    sql: "SELECT DISTINCT region FROM sites ORDER BY region"
    returns: scalar_list
  device_names:
    sql: "SELECT name FROM devices ORDER BY name"
    returns: scalar_list
```

`choice` fields validate strictly against the query's results (an
unlisted region is rejected); `lookup` fields only *suggest* — free text
that doesn't match anything in the database is still accepted, useful
for a device that hasn't been inventoried yet. See
[schema-reference.md](schema-reference.md#from_db) for the full
`from_db` shape and [hooks.md](hooks.md) for the next
step up: a hook that *uses* `services.db` to derive values no form field
holds directly (`examples/schemas/device_provisioning.yaml` is that
example).

```bash
configgen db check --queries examples/data/queries.yaml   # every query still runs cleanly
configgen generate examples/schemas/device_onboarding.yaml \
  --values examples/sample_device_onboarding_values.json --output /tmp/out
```

## Publishing it

A schema's `status:` controls who sees it (§13.3): `draft` (Template
Engineers/Admins only, for work in progress) → `published` (everyone in
the group) → `deprecated` (hidden from Config Engineers, kept for
reference). New schemas should start `draft`, get flipped to `published`
from the GUI's template editor (or by hand) once the template's been
test-rendered. See [roles-and-groups.md](roles-and-groups.md) for who's
allowed to do that.
