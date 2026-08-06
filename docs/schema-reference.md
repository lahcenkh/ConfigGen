# Schema reference

A schema is one YAML file describing a form and what it produces. This
doc covers every field type and every schema-level option. For a
step-by-step introduction, see [adding-a-config.md](adding-a-config.md).

## File layout

A schema lives at `<project>/schemas/<id>.yaml`; everything else it can
reference is a sibling directory of `schemas/`, resolved automatically:

```text
<project>/
├── schemas/<id>.yaml       # this file
├── templates/<file>.j2     # template:, or every documents[].template
├── hooks/<name>.py         # hook: <name>  ->  hooks/<name>.py
├── preflight/<name>.py     # preflight: <name> ->  preflight/<name>.py (unless it's a built-in)
└── data/queries.yaml       # from_db field options
```

`<project>` is `resources/` for real use, or a self-contained set like
`examples/` — both resolve the same way, from the schema file's own path
(`schemas/x.yaml`'s project root is two directories up).

## Top-level schema fields

| Key | Required | Meaning |
|---|:---:|---|
| `name` | yes | Display name (dashboard tile title, template editor header) — change it in place with the Template Editor's **Rename** button, or by hand |
| `id` | yes | Stable identifier — filenames, generation log entries, and version history all key off this, not the schema's filename |
| `fields` | yes | List of field definitions, see below |
| `template` | one of these two | Single output document — the `.j2` file's name, relative to `templates/` |
| `documents` | one of these two | Multiple output documents: a list of `{key, label, template}` (§ [adding-a-config.md](adding-a-config.md#2-multi-document-ha_pair_config)) |
| `version` | no (default `1`) | Bumped by hand before `configgen history --save`; recorded in every generated config's header/profile/log entry |
| `status` | no (default `draft`) | `draft` / `published` / `deprecated` — see [roles-and-groups.md](roles-and-groups.md#template-lifecycle) |
| `group` | no | Which group can see this schema; omitted means visible to everyone (§ [roles-and-groups.md](roles-and-groups.md)) |
| `description` | no | Shown on the dashboard tile |
| `tags` | no | List of strings, searchable from the dashboard |
| `identity_field` | no | Which field's value names the output file and identifies it for diff/history lookups (usually `hostname` or similar) |
| `comment_prefix` | no (default `!`) | Used to format the generated-file header comment (`!`, `#`, `//`, `;`, ...) |
| `supports_variants` | no (default `false`) | Allows multiple saved outputs per identity value (e.g. re-provisioning the same host under a different variant name) |
| `hook` | no | Name of a Tier-2 hook, resolved to `hooks/<name>.py` — see [hooks.md](hooks.md) |
| `preflight` | no | Name of a post-render syntax checker — a built-in platform (`ios`, `junos`, `sros`, `vrp`, `generic`) or a custom `preflight/<name>.py` |

## Field types

Every field has a `type:`, which controls both how raw input is
validated/coerced and what a template's `{{ field_key }}` actually is.

| `type` | Coerces to | Template gets |
|---|---|---|
| `string` | validated string | `str` |
| `text` | validated string (same rules as `string`; used for free-text/notes areas) | `str` |
| `port` | validated string (see the no-default rule below) | `str` |
| `lookup` | validated string, autocompletes from `from_db` but accepts free text | `str` |
| `int` | integer, checked against `min`/`max` | `int` |
| `bool` | `true`/`false` | `bool` |
| `choice` | one of `options`, or one of `from_db`'s results if a database is configured | `str` |
| `ip` | a validated IPv4 host address | `str` (renders as the address) |
| `ip_cidr` | a validated `host/prefix`, e.g. `10.0.0.5/24` | object with `.ip`, `.netmask`, `.prefix`, renders as `10.0.0.5/24` |
| `network` | a validated subnet, e.g. `10.0.0.0/24` | object with `.netmask`, `.prefix`, `.first_usable`, `.nexthop`, `.host_at(offset)` (also `net[offset]`), renders as `10.0.0.0/24` |
| `cidr` | a validated network, normalized to its network address | `str` (renders as `10.0.0.0/24`) |

`ip`/`ip_cidr`/`network`/`cidr` all subclass `str`, so `{{ my_ip }}`
always renders sensibly on its own — the extra attributes are there for
templates that need the parts separately:

```jinja
{{ mgmt_ip }}                {# 10.0.0.5/24 #}
{{ mgmt_ip.ip }}              {# 10.0.0.5 #}
{{ mgmt_ip.netmask }}         {# 255.255.255.0 #}

{{ subnet.first_usable }}     {# 10.0.0.1 #}
{{ subnet.nexthop }}          {# 10.0.0.2 - the conventional gateway address #}
{{ subnet.host_at(10) }}      {# 10.0.0.10 #}
```

Boolean strings accepted for `bool` fields: `true`/`1`/`yes`/`on` and
`false`/`0`/`no`/`off` (case-insensitive) — useful when values arrive as
CSV text (bulk generation) rather than a GUI checkbox.

## Field options

```yaml
fields:
  - key: hostname          # required - the template variable name and form-data key
    label: "Hostname"      # required - shown in the form
    type: string           # required - see above
    section: "Identity"    # groups fields under a heading in the form
    required: true         # missing/blank value is a validation error
    default: "edge-01"     # pre-filled value (see the port/lookup exception below)
    help: "Lowercase letters, digits, and hyphens only."
    pattern: '^[a-z0-9-]{1,63}$'   # regex the value must fully match (string/text/port/lookup)
    example: "rtr-core-01"         # shown as placeholder text; also appended to
                                    # the error message when validation fails
    min: 1                 # int fields only
    max: 4094               # int fields only
    options: ["small", "medium", "large"]   # choice fields: a fixed list
    from_db: {query: regions}               # choice/lookup fields: options from a database query
    visible_if: {enable_ospf: true}   # hide this field unless the condition holds
    required_if: {enable_ospf: true}  # this field becomes required when the condition holds
    clear_when: {enable_ospf: false}  # reset this field's value when the condition holds
```

### `from_db`

`from_db: {query: <name>}` names a query declared in the project's
`data/queries.yaml` (see [hooks.md](hooks.md#servicesdb-and-queriesyaml)
for the file format). The difference between the two field types that
use it matters:

- **`choice` + `from_db`**: a *closed* set. If a database is configured
  for the project, the submitted value must be one of the query's
  results, or validation fails. Without a database configured, the
  value passes through unchecked (so a form-only dev/test path still
  works).
- **`lookup` + `from_db`**: *autocomplete only*. The GUI suggests values
  from the query, but any text is accepted — useful for "this might not
  be in inventory yet."

### Conditionals: `visible_if` / `required_if` / `clear_when`

All three take the same shape: a dict of `{other_field_key: expected_value}`.
Multiple keys are ANDed together, and comparison is by string form (so
`{enable_ospf: true}` matches whether `enable_ospf`'s live value is the
Python `bool` `True` or the string `"true"`):

- **`visible_if`**: the field (and its value) is omitted from validation
  entirely when the condition doesn't hold — not just hidden in the GUI,
  genuinely absent from what a template or hook receives.
- **`required_if`**: on top of `required:`, the field also becomes
  mandatory whenever the condition holds (e.g. `ospf_process_id` is only
  required if `enable_ospf` is true).
- **`clear_when`**: the GUI resets the field's value to empty when the
  condition holds (e.g. clearing a "custom reason" text field once its
  triggering checkbox is unchecked).

`configgen check` flags any conditional that references a field key that
doesn't exist in the same schema.

## The regex quoting gotcha

**Always single-quote a `pattern:` in YAML.** Double-quoted YAML strings
process backslash escapes themselves, so `"^[a-z0-9-]{1,63}$"` is fine
(no backslashes), but the moment a pattern needs `\d`, `\w`, etc., double
quotes silently eat the backslash before your regex engine ever sees it:

```yaml
pattern: '^[A-Z]{2}-\d{4,8}$'    # correct - \d survives
pattern: "^[A-Z]{2}-\d{4,8}$"    # wrong - YAML unescapes \d to just d
```

`configgen check` catches an outright invalid regex (unbalanced
brackets, etc.) but can't detect "this pattern is valid but not what you
meant" — a swallowed `\d` still compiles, it just matches the literal
letter `d`.

## Defaults must satisfy their own pattern

If a field has both `default:` and `pattern:`, the default is checked
against the pattern at validation time (`configgen check`) — a default
that would fail its own field's validation is a schema bug, caught
before anyone hits Generate.

## Port and lookup fields never have a default

`port` and `lookup` fields must not declare `default:` — `configgen
check` rejects it. Both types exist specifically for values that should
always be entered deliberately (a management port number, a
looked-up/autocompleted device name); use `example:` to show the
expected format as placeholder text instead of a default that could be
submitted unnoticed.

## Multi-document schemas

Declare **either** `template:` (one output) **or** `documents:` (two or
more) — never both, never neither. `configgen check` rejects a schema
that gets this wrong. See
[adding-a-config.md](adding-a-config.md#2-multi-document-ha_pair_config)
for a worked example.

## Validating a schema

```bash
configgen check resources/schemas/my_thing.yaml
```

Checks (in order): every field's `type` is one of the eleven above;
duplicate field keys; every `pattern` compiles; every `default` matches
its own `pattern`; every `visible_if`/`required_if`/`clear_when`
references a real field key; no `port`/`lookup` field declares a
`default`; the template file(s) referenced actually exist; if
`hook:` is set, the hook file exists; if any field's `from_db.query`
is set and `data/queries.yaml` exists, the query name is declared there.
It also warns (never fails) if the template references a variable that
no field or hook appears to supply — the same warning the GUI
template editor's **Check**/**Extract Variables** buttons show.
