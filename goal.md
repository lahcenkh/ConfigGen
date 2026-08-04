# ConfigGen — Full Build Plan (Final)

A generic, plug-and-play desktop tool for generating text configurations from a
guided form and Jinja templates. Anyone can add a config by dropping in a schema
file, a template, and (optionally) a small Python hook — no changes to the core.

This is a clean re-implementation for public release. It carries over the working
code from the private build (bug fixes included) but removes every company-specific
detail. No real inventory, no telecom customers, no internal data.

---

## 0. Guiding principles

1. **Plug and play.** A new config = one YAML schema + one (or more) Jinja
   templates + optional one Python hook. Nothing else is touched.
2. **Two variable sources.** Field values come from the form; derived or
   looked-up values come from a Python *hook* that may read a SQLite
   database through a generic reader.
3. **Nothing company-specific in core.** The engine knows nothing about routers,
   regions, or any particular table. Domain logic lives entirely in the user's
   own schemas, templates, hooks, and database — which are not committed.
4. **Carry over, don't retype.** Every fix earned in the private build is
   preserved (listed in §15). A blank rewrite would reintroduce them.
5. **Catch errors early.** Template variables are extracted from Jinja2 AST,
   schemas are validated at load time, and mismatches between template and schema
   are flagged before runtime — not discovered when a user hits Generate.
6. **Scale from one to many.** A single config is the default; bulk generation
   from CSV or database query is a first-class workflow, not an afterthought.
7. **Separate who builds from who uses.** Template Engineers write templates and
   schemas. Config Engineers fill forms and generate configs. The roles are
   distinct and the permissions enforce it.

---

## 1. Repository layout

```
configgen/
├── src/configgen/
│   ├── app.py                  entry point, login loop, window icon
│   ├── cli.py                  headless: list / check / generate / extract / bulk / diff / history / plugins
│   ├── appinfo.py              name, version, author, contact (single source)
│   ├── paths.py                folder resolution (dev + PyInstaller frozen)
│   ├── core/
│   │   ├── schema.py           YAML loader, Field/Document/Schema dataclasses
│   │   ├── schema_validator.py schema YAML validation against Pydantic model
│   │   ├── extractor.py        Jinja2 AST variable extraction + schema mismatch detection
│   │   ├── validators.py       per-type coercion + cross-field checks
│   │   ├── renderer.py         Jinja env, filters, single + multi-doc render
│   │   ├── exporter.py         filename building, per-document save, profiles, config packs
│   │   ├── values.py           typed values (network arithmetic helpers)
│   │   ├── differ.py           unified diff between two rendered configs
│   │   ├── bulk.py             batch generation from CSV/XLSX/database query
│   │   ├── preflight.py        optional syntax pre-checks per target platform
│   │   ├── db.py               GENERIC read-only SQLite service
│   │   ├── auth.py             users, roles, groups, grants, PBKDF2, lockout, API keys
│   │   ├── registry.py         auto-discover hooks, filters, preflight checks
│   │   └── versioning.py       schema+template history, manifest, traceability
│   ├── hooks/
│   │   ├── __init__.py         hook loader + Services + HookError
│   │   └── <name>.py           one file per DB-backed / derived config
│   └── ui/
│       ├── theme.py            design tokens + stylesheets + dark mode
│       ├── widgets.py          one widget per field type
│       ├── form_builder.py     builds a form from a schema, live validation
│       ├── login_window.py     login + forced first-login password change
│       ├── dashboard.py        landing: quick-start tiles, recent, tools, search/filter
│       ├── main_window.py      stacked dashboard/generator, preview, diff, save
│       ├── bulk_dialog.py      CSV/XLSX picker, progress bar, error summary table
│       ├── template_editor.py  admin Jinja editor (check / test-render / extract variables / version history)
│       ├── user_admin.py       admin user + group + grant management
│       ├── generation_log.py   audit trail viewer with filters
│       ├── about.py            about dialog
│       └── highlighters.py     generated-config syntax highlighting
├── resources/
│   ├── schemas/                *.yaml — one per config (EXAMPLES only in repo)
│   ├── templates/              *.j2   — one or more per config
│   └── data/
│       └── README.txt          "drop your database here" — no DB committed
├── examples/                   fictional, self-contained demo configs
│   ├── schemas/  templates/  hooks/  sample.db  sample_bulk.csv
├── tests/
├── packaging/                  ConfigGen.spec, sign.ps1, deploy-cert.ps1, icon, Dockerfile
├── tools/                      make_icon.py, screenshot harness
├── docs/
│   ├── adding-a-config.md      the contributor guide
│   ├── schema-reference.md     every field type and option
│   ├── hooks.md                 the hook contract + db service
│   ├── bulk-generation.md      CSV format, database-driven batches
│   ├── roles-and-groups.md     the three-role model, group scoping, permissions
│   └── troubleshooting.md      top 10 errors and fixes
├── README.md
├── LICENSE
├── pyproject.toml
├── .pre-commit-config.yaml     ruff + black
└── .gitignore                  ignores resources/data/*.db, private overlays
```

**Company data separation.** `resources/schemas`, `resources/templates`, and
`resources/data/*.db` are the *user's* content. The repo commits only the
`examples/` set and an empty `resources/` with a README. A `.gitignore` keeps any
real config or database from being committed by accident. Users clone the repo,
then drop their own schemas/templates/hooks/DB into `resources/`.

---

## 2. The schema file (YAML)

One file per config, the single source of truth for the form and the output.

### 2.1 Top level

```yaml
name: "Acme Router Base Config"      # shown on the tile and in pickers
group: "Acme"                        # scopes visibility to group members
id: acme_router_base                 # unique; also the default hook name
version: 1                           # schema version, auto-incremented on save
status: published                    # draft | published | deprecated
description: "Base router config with OSPF, NTP, SNMP, and management interface"
tags: ["routing", "ospf", "cisco-ios"]  # for filtering and search
supports_variants: false             # optional second axis (was "homing")
hook: acme_router_base                # optional: hooks/<name>.py
preflight: ios                       # optional: syntax pre-check for target platform
template: acme_router_base.j2        # single-document config
# --- OR, for multiple outputs ---
documents:
  - key: primary
    label: "Primary"
    template: acme_primary.j2
  - key: backup
    label: "Backup"
    template: acme_backup.j2
fields:
  - ...
```

`group`/`name`/`id` replace the private build's hardcoded `customer`/`device`, so
nothing is telecom-specific. A config declares **either** `template` (one output)
**or** `documents` (several).

### 2.2 Field types (all supported)

| type | widget | notes |
|------|--------|-------|
| `string` | line edit | `pattern` (regex) + `example` |
| `int` | spin / line edit | `min`, `max` |
| `bool` | checkbox | `default: true/false` |
| `choice` | dropdown | `options: [...]` or `from_db:` |
| `ip` | line edit | validates IPv4 |
| `ip_cidr` | ip + prefix | exposes `.ip`, `.netmask`, `.prefix` |
| `network` | line edit | subnet arithmetic (`.first_usable`, `.nexthop`, `.netmask`, offsets) |
| `cidr` | line edit | raw `x.x.x.x/nn`, validated, passed as text |
| `port` | line edit | `pattern` + `example`, no default |
| `lookup` | line edit + autocomplete | completions from `from_db:` |
| `text` | multi-line | free text |

Every field supports: `key`, `label`, `type`, `section` (groups fields in the
form), `required`, `default`, `help`, `pattern` (single-quoted in YAML — `\d`
breaks double-quoted), `example`, and the conditionals below.

### 2.3 Conditionals

```yaml
  - key: vrrp_ip
    type: ip
    visible_if: {mode: dual}         # show only when another field equals a value
    required_if: {mode: dual}        # required only then
    clear_when: {mode: single}       # wipe the value when it becomes irrelevant
```

### 2.4 Validation

- Per-field: `pattern`, `min`/`max`, type coercion.
- Cross-field: declared in the schema where simple (e.g. "these two must differ"),
  or done in the hook where it depends on a DB lookup.
- Error messages prefer `example` over raw regex ("Expected like gei-0/0/0/0").

### 2.5 DB-backed choices / autocomplete

```yaml
  - key: region
    type: choice
    from_db: {query: regions}        # a named query the db service exposes

  - key: device_name
    type: lookup
    from_db: {query: device_names}   # autocomplete from the database
```

`from_db` names a **query**, not a table — the query is defined in the project's
db config (§5), so the core never hardcodes a schema.

### 2.6 Schema validation (load-time safety)

On load, every schema YAML is validated against a Pydantic model before the form
is built. This catches:

- Missing required top-level keys (`name`, `id`, `fields`)
- Unrecognized field types
- `from_db` references to queries not defined in `queries.yaml`
- Template files that don't exist on disk
- Hook files that don't exist if `hook:` is declared
- `visible_if` / `required_if` / `clear_when` referencing non-existent field keys
- Regex patterns that don't compile
- Defaults that violate their own field's pattern
- Duplicate field keys within the same schema

On failure: structured error with the field path and a suggestion, not a raw
Python traceback. CLI: `configgen check <schema.yaml>` runs validation standalone.

---

## 3. Template variable extraction (AST)

The feature that separates ConfigGen from raw Jinja2 CLI usage.

### 3.1 How it works

`core/extractor.py` parses a Jinja2 template via `Environment.parse()`, walks the
AST, and collects every referenced `Name` node. It returns a list of top-level
variable names the template expects.

### 3.2 Three uses

**Mismatch detection.** On schema load, the extractor compares template variables
against declared schema fields (and hook return keys, if the hook exists).
Any variable in the template that has no source is flagged as a warning. This
prevents the most common user error: template references `{{ vlan_id }}` but no
field or hook provides it.

**Schema scaffolding.** When a Template Engineer writes a template first (the
natural workflow), the extractor generates a skeleton schema YAML with one field
entry per discovered variable, pre-filled with a guessed type (`string` by
default, `ip` if the name contains `_ip`, `int` if it contains `_id` or
`_number`). The engineer refines from there instead of writing the schema from
scratch.

**Template editor integration.** The "Extract Variables" button in the template
editor shows discovered variables with a status indicator: green (matched to a
schema field), yellow (matched to a hook), red (no source found).

### 3.3 CLI

```bash
configgen extract <template.j2>                    # list all variables
configgen extract <template.j2> --scaffold > s.yaml  # generate skeleton schema
configgen extract <template.j2> --check <schema.yaml> # report mismatches
```

### 3.4 Limitations

Extraction covers `{{ var }}`, `{% for x in var %}`, `{% if var %}`, and dotted
access (`{{ cfg.hostname }}`). It does not trace through hooks — if a
hook returns `cfg` with subkeys, the extractor sees `cfg` but not `cfg.hostname`.
The mismatch check is therefore advisory for hook-driven configs, not blocking.

---

## 4. The two-tier engine

```
form values ──▶ validate (Tier 1) ──▶ hook (Tier 2, optional) ──▶ preflight (optional) ──▶ render ──▶ save + log
```

- **Tier 1 (declarative).** Fields → validated typed values. A config with only
  form inputs and simple validation needs no code at all.
- **Tier 2 (hook).** For derived or looked-up values. The hook receives
  the validated values and a `Services` object, and returns the final template
  context. This is where DB lookups and custom arithmetic live.
- **Preflight (optional).** After rendering, a platform-specific check scans the
  output for common syntax errors before saving.
- **Log.** Every generation is recorded in the audit trail with user, group,
  schema version, inputs, and timestamp.

A config with no `hook` renders straight from Tier 1.

---

## 5. The generic database service (the key generalization)

The private build hardcoded three inventory tables. The public build must not.

### 5.1 Design

- `core/db.py` provides a **read-only, project-agnostic** SQLite reader:
  `Database(path)` with `query(name, **params)` and `all(name)`.
- Named queries live in a **project db config**, not in code:

```yaml
# resources/data/queries.yaml   (user-supplied, not committed)
database: my_inventory.db
queries:
  regions:
    sql: "SELECT DISTINCT region FROM sites ORDER BY region"
    returns: scalar_list
  device_names:
    sql: "SELECT name FROM devices"
    returns: scalar_list
  device:
    sql: "SELECT * FROM devices WHERE name = :name"
    returns: row
  devices_by_site:
    sql: "SELECT * FROM devices WHERE site = :site"
    returns: rows
```

- The core loads `queries.yaml`, exposes each query by name, runs it with bound
  parameters (never string interpolation), and closes the connection after each
  call (the Windows-lock fix). `from_db: {query: regions}` and hooks calling
  `services.db.query("device", name=...)` both go through this.

### 5.2 Why this matters for GitHub

Anyone can point ConfigGen at **any** SQLite database by writing a `queries.yaml`
and referencing those query names from schemas and hooks. Your specific
three-table telecom logic becomes *your* `queries.yaml` + *your* hooks + *your*
`.db`, none of which are committed. The engine ships knowing nothing about it.

### 5.3 Missing database

If `queries.yaml` or the `.db` is absent, DB-backed configs report it cleanly and
form-only configs still work.

### 5.4 Database health check

`configgen db check` runs every query defined in `queries.yaml` with empty/null
parameters and reports which ones succeed and which fail. This catches schema
drift — when the user updates their database structure but forgets to update the
queries.

### 5.5 Connection strategy

Open-close per call remains the default (Windows file lock safety). For
autocomplete fields where every keystroke triggers a query, the db service uses a
session-scoped connection that opens when the form loads and closes when the form
closes or the user navigates away. This prevents lock issues while avoiding the
latency of per-keystroke open/close cycles.

---

## 6. The hook contract

One file per config that needs derivation or lookups: `hooks/<id>.py`.

```python
def build(values: dict, context: dict, services: Services) -> dict:
    """Return the template context. Raise HookError({field: msg}) to reject."""
    device = services.db.query("device", name=values["device_name"])
    if not device:
        raise HookError({"device_name": "Unknown device"})
    return {
        "cfg": {
            "name": values["device_name"],
            "mgmt_ip": services.net.host_at(values["subnet"], 1),
            "vendor": device["vendor"],
        }
    }
```

- **`services`** exposes: `db` (the generic reader), `net` (subnet/address
  helpers — the generalized, de-telecom'd version of the private build's
  functions), and any project-registered helpers.
- The returned dict's keys are the **template's** top-level variables. Names are
  the author's choice — the engine imposes none.
- Binding: explicit via `hook:` in the schema (renameable, visible).
- Hooks are pure Python and unit-testable in isolation.

Custom filters (like the private build's two Jinja filters) are registered the
same way: a project `filters.py` the renderer picks up.

---

## 7. Rendering & output

- Jinja with `StrictUndefined` (an undeclared variable fails loudly, not silently
  blank). The template editor's **Check** catches this before saving.
- `render_documents()` returns `{doc_key: text}`; single-template configs yield
  one entry.
- **Generated config header.** Every output file begins with a comment:
  `! Generated by ConfigGen v{version} | Template: {id} v{schema_version} | {timestamp} | User: {username}`
  The comment prefix (`!`, `#`, `//`) is configurable per schema via `comment_prefix`.
- **Save:** one `.txt` per document, named
  `{group}_{id}_{host}_{DOCKEY}_{variant}_{stamp}.txt`, plus one shared `.json`
  profile for the set. Reopen resolves the shared profile by stripping the doc
  token.
- **Save location:** `output/{username}/{group}/` — each user's outputs are
  isolated by their username folder, then by group.
- Preview shows one pane for single-doc, tabs for multi-doc (styled so inactive
  tabs are readable).

---

## 8. Bulk generation

The highest-value workflow for MSPs and teams managing multiple devices.

### 8.1 Input sources

- **CSV/XLSX file:** each row is one set of form values. Column headers must match
  schema field keys. Extra columns are ignored; missing required columns fail
  validation with a clear error.
- **Database query:** a named query from `queries.yaml` that returns multiple rows,
  each row mapped to form fields by column name.

### 8.2 Process

```
input (CSV/query) ──▶ validate all rows ──▶ collect errors ──▶ render valid rows ──▶ save to batch folder ──▶ log all
```

- All rows are validated first. The user sees a summary: "47 valid, 3 errors"
  with a table showing which rows failed and why.
- The user can fix and re-import, or generate only the valid rows.
- Output goes to `output/{username}/{group}/batch_{timestamp}/` with per-device filenames.
- A `batch_manifest.json` records what was generated, from which input, with
  which schema version.
- Every row generated is logged individually in the generation log, linked by a
  shared `bulk_batch_id`.

### 8.3 Permissions

All three roles can use bulk generation, but only on templates they can see:
- Config Engineers: published templates in their assigned groups only
- Template Engineers: all templates in their assigned groups
- Admins: all templates in all groups

### 8.4 CLI

```bash
configgen bulk <schema_id> --input devices.csv --output ./batch/
configgen bulk <schema_id> --query devices_by_site --param site=NYC --output ./batch/
```

### 8.5 GUI

"Bulk Generate" button on the dashboard (visible to all roles). File picker for
CSV/XLSX, progress bar during generation, error summary table at the end with
export-to-CSV for the error report.

---

## 9. Config diff

When regenerating a config after changing a variable or template, the user needs
to see what changed.

### 9.1 Design

`core/differ.py` produces a unified diff between two rendered config texts.
Supports three modes:

- **Current vs. last saved:** after generating, compare against the most recent
  output for the same schema + host combination.
- **Two files:** compare any two config files side by side.
- **Version comparison:** compare output from two different schema versions.

### 9.2 GUI

Side-by-side diff pane in the generator view, with additions highlighted in green
and deletions in red. Accessible via Ctrl+D after generating. Available to all
roles.

### 9.3 CLI

```bash
configgen diff <file1> <file2>
configgen diff --last <schema_id> <host>  # current vs. last generated
```

---

## 10. Config versioning & history

### 10.1 How it works

Each time a schema or template is saved through the template editor (by an Admin
or Template Engineer), a timestamped copy is created in
`resources/.history/<id>/`. A `manifest.json` per config tracks:

```json
{
  "versions": [
    {
      "version": 3,
      "author": "bob",
      "timestamp": "2026-01-15T14:30:00",
      "note": "Added SNMP v3 support"
    }
  ]
}
```

### 10.2 Traceability

Every generated config includes the schema version in its profile `.json`, in the
output header comment, and in the generation log. If a generated config caused an
issue, anyone with access to the generation log can trace back exactly which
template version produced it, who generated it, and what inputs they used.

### 10.3 CLI

```bash
configgen history <id>                      # list versions
configgen history <id> --diff 2 3           # diff between version 2 and 3
```

### 10.4 GUI

Template editor (Admin and Template Engineer only) shows a "History" panel listing
past versions with timestamps, authors, and notes. Clicking a version shows a
diff against the current version. "Restore" button replaces the current version
with a historical one (creating a new version entry).

---

## 11. Preflight checks

Optional syntax pre-checks on rendered output before saving.

### 11.1 Design

`core/preflight.py` provides a registry of platform-specific checks. A schema
declares its target platform via `preflight: ios` (optional). After rendering, the
preflight runner scans the output for common errors.

### 11.2 Built-in checks

| Platform | Checks |
|----------|--------|
| `ios` | Matching `interface`/`end` blocks, valid interface names, VLAN range 1-4094 |
| `junos` | Balanced braces, valid hierarchical structure |
| `generic` | No empty lines where a command was expected, no unresolved `{{ }}` markers |

### 11.3 Custom checks

Users register custom preflight checks by dropping a Python file in
`preflight/<platform>.py` with a `check(text: str) -> list[str]` function that
returns a list of warning messages (empty = passed).

### 11.4 Permissions

Preflight configuration (adding/editing checks) is Admin and Template Engineer
only. The checks run automatically for all roles on generation.

---

## 12. Plugin & extension registry

### 12.1 Auto-discovery

On startup, `core/registry.py` scans:

- `hooks/*.py` → hooks
- `filters.py` → custom Jinja filters
- `preflight/*.py` → preflight checkers

It builds a registry mapping each plugin to its source file, validates that every
schema's `hook:` and `preflight:` point to existing plugins, and logs warnings
for orphaned plugins (exist but no schema references them).

### 12.2 CLI

```bash
configgen plugins                     # list all registered hooks, filters, preflight checks
configgen plugins --check             # validate all schema references resolve
```

---

## 13. Auth, users, groups, roles & permissions

This is the section that makes ConfigGen a **team tool** rather than a fancy
Jinja2 CLI. The three-role model enforces the core workflow: Template Engineers
build once, Config Engineers generate many times.

### 13.1 Three roles

| | Admin | Template Engineer | Config Engineer |
|---|:---:|:---:|:---:|
| **Users & groups** | | | |
| Create / delete users | ✓ | | |
| Assign roles to users | ✓ | | |
| Create / manage groups | ✓ | | |
| Assign users to groups | ✓ | | |
| Generate / revoke API keys | ✓ | | |
| **Templates & schemas** | | | |
| Create new schema + template | ✓ | ✓ | |
| Edit existing schema + template | ✓ | ✓ | |
| Delete schema + template | ✓ | | |
| Publish / unpublish / deprecate | ✓ | ✓ | |
| Extract variables (AST) | ✓ | ✓ | |
| View template version history | ✓ | ✓ | |
| Restore a previous version | ✓ | ✓ | |
| View template source code | ✓ | ✓ | |
| **Variables & database** | | | |
| Manage global variables | ✓ | ✓ | |
| Edit queries.yaml | ✓ | ✓ | |
| Run db health check | ✓ | ✓ | |
| **Config generation** | | | |
| See draft templates | ✓ | ✓ | |
| See published templates | ✓ | ✓ | ✓ |
| See deprecated templates | ✓ | ✓ | |
| Generate single config | ✓ | ✓ | ✓ |
| Bulk generate from CSV | ✓ | ✓ | ✓ |
| Preview before saving | ✓ | ✓ | ✓ |
| Diff with last generated | ✓ | ✓ | ✓ |
| Copy to clipboard / download | ✓ | ✓ | ✓ |
| **History & audit** | | | |
| View own generation history | ✓ | ✓ | ✓ |
| View group generation history | ✓ | ✓ | |
| View all generation history | ✓ | | |
| **Sharing** | | | |
| Export config pack | ✓ | ✓ | |
| Import config pack | ✓ | | |
| **Tools & settings** | | | |
| Template editor | ✓ | ✓ | |
| User admin panel | ✓ | | |
| Preflight check settings | ✓ | ✓ | |
| Dark mode / personal preferences | ✓ | ✓ | ✓ |

### 13.2 Groups

Groups scope **what configs a user can see and generate**. They replace the
private build's hardcoded "customer" concept.

```
Group: "Acme Corp"
├── Templates: acme_router_base, acme_switch_vlan, acme_firewall
├── Members:
│   ├── alice (Admin)           → sees all groups automatically
│   ├── bob (Template Engineer) → sees only Acme Corp templates
│   └── carol (Config Engineer) → sees only published Acme Corp templates

Group: "Beta Industries"
├── Templates: beta_router_ospf, beta_wan_edge
├── Members:
│   ├── alice (Admin)           → sees this group too (sees everything)
│   └── dave (Config Engineer)  → sees only published Beta templates
```

Rules:

- A schema declares its group via `group: "Acme Corp"` at the top level.
- Admins see all groups automatically. They are never assigned to a group; they
  have implicit access to everything.
- Template Engineers and Config Engineers see only the groups they are explicitly
  assigned to.
- A user can belong to multiple groups.
- Templates without a `group` field are visible to everyone (useful for shared
  or generic configs).
- The dashboard tiles, template picker dropdowns, bulk generation inputs, and
  output folders are all filtered by group assignment.

### 13.3 Template lifecycle (who does what)

```
Template Engineer creates          Config Engineer uses
─────────────────────────          ────────────────────

  ┌──────────┐    publish    ┌───────────┐    generate    ┌──────────┐
  │  DRAFT   │──────────────▶│ PUBLISHED │───────────────▶│  CONFIG  │
  │          │◀──────────────│           │                │  OUTPUT  │
  └──────────┘   unpublish   └───────────┘                └──────────┘
       │                           │
       │                           │ deprecate
       │                           ▼
       │                     ┌────────────┐
       │                     │ DEPRECATED │  (hidden from Config Engineers)
       │                     └────────────┘
       │
       │  delete (Admin only)
       ▼
    [removed]
```

- **Draft** — visible to Admins and Template Engineers only. Used for
  work-in-progress templates being tested. Config Engineers never see these.
- **Published** — visible to everyone in the group. This is what Config
  Engineers use daily.
- **Deprecated** — hidden from Config Engineers but still accessible to Admins
  and Template Engineers for reference or restoration. Previously generated
  configs from this template remain in history.
- **Delete** — Admin only. Removes the schema, template, and hook files.
  Generation history referencing this template is preserved (the log records the
  schema ID and version, not a live reference).

### 13.4 What each role experiences

**Config Engineer (the daily user):**

```
Login ──▶ Dashboard
          │
          ├── Tiles: ONLY published templates in assigned groups
          ├── Search/filter by tags and group
          ├── "Recent" section: own last 10 generated configs
          │
          ▼
         Pick a template ──▶ Dynamic form
                              │
                              ├── Fill in fields (DB-sourced fields pre-filled)
                              ├── Live validation (red borders + error messages)
                              ├── Preview button → rendered config
                              ├── Diff button → compare with last generated
                              │
                              ▼
                            Generate ──▶ Output
                                         ├── Copy to clipboard
                                         ├── Download as .txt
                                         ├── Saved to history automatically
                                         └── Bulk: upload CSV → progress → download batch
```

They cannot create, edit, or see template source code. They cannot manage users
or groups. They cannot see other users' generation history. They interact with
forms and outputs only.

**Template Engineer (the builder):**

Everything a Config Engineer can do, plus:

```
Dashboard ──▶ Template Editor
               │
               ├── Create new schema + template
               ├── Edit existing (code editor with syntax highlighting)
               ├── Extract Variables button → AST analysis
               ├── Check button → StrictUndefined validation
               ├── Test Render button → render with sample values
               ├── Version History → diff, restore
               ├── Publish / Unpublish / Deprecate
               └── Manage global variables and queries.yaml
```

They see draft and deprecated templates. They can create and modify templates
but cannot delete them (prevents accidental loss). They can see generation
history for their groups (useful for debugging template issues reported by
Config Engineers).

**Admin (full control):**

Everything a Template Engineer can do, plus:

```
Dashboard ──▶ User Admin
               │
               ├── Create / delete users
               ├── Set roles (Admin / Template Engineer / Config Engineer)
               ├── Create / manage groups
               ├── Assign users to groups
               ├── Generate / revoke API keys
               └── View all generation history (all users, all groups)

Dashboard ──▶ Template Management
               │
               ├── Delete templates
               ├── Import config packs
               └── All template editor features
```

Admins see all groups automatically without explicit assignment. They are the
only role that can delete templates, delete users, import config packs, and
view the full cross-group generation log.

### 13.5 Storage

SQLite `users.db` (separate from any inventory DB), not committed.

**Tables:**

```sql
users
  id, username, password_hash, salt, role, first_name, last_name,
  company_name, failed_attempts, locked_until, force_password_change,
  created_at, updated_at

groups
  id, name, slug, description, created_at

group_members
  user_id, group_id, assigned_at, assigned_by

api_keys
  id, user_id, key_hash, label, created_at, revoked_at

generation_log
  id, user_id, group_id, schema_id, schema_version,
  form_inputs (JSON), output_filename, bulk_batch_id (nullable),
  created_at
```

### 13.6 Security

- Passwords: PBKDF2-SHA256, salted, minimum 8 characters
- Lockout: 5 failed attempts → 15-minute lock
- First login: forced password change
- Username charset restricted (it doubles as the output folder name): `[a-z0-9_-]`
- API keys: generated per user, stored as SHA256 hash, revocable via admin UI,
  labeled (e.g. "CI pipeline", "backup script")
- Session: no token — the desktop app holds the authenticated user object in
  memory for the session duration

### 13.7 Generation log (audit trail)

Every generated config is logged automatically. The log records:

- Who generated it (user)
- Which group and schema (with schema version)
- What inputs were provided (full form values as JSON)
- When it was generated (timestamp)
- What file was created (output filename)
- Whether it was part of a bulk batch (batch ID)

**Viewing permissions:**
- Config Engineers: own history only
- Template Engineers: own history + group history (all users in their groups)
- Admins: all history across all users and groups

**GUI:** A "Generation Log" panel accessible from the dashboard. Filterable by
user, group, schema, date range. Clicking an entry shows the form inputs and
lets the user re-generate with the same values (useful for reproducing a config
after a template update).

### 13.8 Solo user mode

All of this is optional-feeling. A solo user clones the repo, runs ConfigGen,
and logs in as admin on first launch. They are the only user, they see
everything, and the group/role system is invisible unless they choose to create
additional users. The complexity exists for teams; it stays out of the way for
individuals.

---

## 14. Config pack export / import

For sharing configs between team members, machines, or publishing to a future
marketplace.

### 14.1 Export

`configgen export <id>` bundles into a `.configpack.zip`:

```
acme_router_base.configpack/
├── schema.yaml
├── templates/
│   └── acme_router_base.j2
├── hooks/
│   └── acme_router_base.py    (if exists)
├── preflight/
│   └── ios.py                 (if exists)
├── sample_values.json         (optional: example form inputs)
└── manifest.json              (id, version, author, description, tags)
```

Export is available to Admins and Template Engineers.

### 14.2 Import

`configgen import <file.configpack>` extracts into `resources/`, validates the
schema, and registers the config. Conflicts (same `id` already exists) prompt the
user to overwrite or rename.

Import is Admin only (it adds executable code via hooks).

### 14.3 GUI

"Export Config Pack" button in the template editor (Admin + Template Engineer).
"Import Config Pack" button in the admin tools section of the dashboard (Admin
only).

---

## 15. GUI

- **Login** → **Dashboard** → **Generator** (or **Template Editor** / **User
  Admin** for privileged roles).
- Dashboard adapts to the user's role: Config Engineers see only published
  template tiles and their own recent history. Template Engineers see a
  "Template Editor" tile and draft templates. Admins see "User Admin" and
  "Import Config Pack" tiles.
- Field widgets per type; `lookup` fields autocomplete from the db service;
  `choice` with `from_db` populates from a query.
- Design tokens centralized in `theme.py`; per-group accent colours and tile
  backgrounds are data, not code.
- **Dark mode** toggle, persisted per user.

### 15.1 Dashboard by role

| Element | Admin | Template Eng | Config Eng |
|---------|:-----:|:------------:|:----------:|
| Published template tiles (own groups) | ✓ | ✓ | ✓ |
| Published template tiles (all groups) | ✓ | | |
| Draft template tiles | ✓ | ✓ | |
| Deprecated template tiles | ✓ | ✓ | |
| Own recent generation history | ✓ | ✓ | ✓ |
| Group generation history | ✓ | ✓ | |
| Template Editor tile | ✓ | ✓ | |
| User Admin tile | ✓ | | |
| Import Config Pack tile | ✓ | | |
| Bulk Generate button | ✓ | ✓ | ✓ |
| Search/filter by tags | ✓ | ✓ | ✓ |
| Search/filter by group | ✓ | ✓ | ✓ (own groups) |

### 15.2 Keyboard shortcuts

| Shortcut | Action | Available to |
|----------|--------|-------------|
| `Ctrl+G` | Generate (submit form) | All roles |
| `Ctrl+P` | Preview rendered output | All roles |
| `Ctrl+S` | Save generated config | All roles |
| `Ctrl+D` | Diff with last generated | All roles |
| `Ctrl+N` | New config (back to dashboard) | All roles |
| `Ctrl+B` | Bulk generate dialog | All roles |
| `Ctrl+E` | Extract variables (template editor) | Admin, Template Eng |
| `Ctrl+H` | Version history (template editor) | Admin, Template Eng |
| `Escape` | Back to previous view | All roles |

---

## 16. Packaging & distribution

- PyInstaller via `ConfigGen.spec`, entry point `run_configgen.py` (absolute
  import — relative import fails frozen).
- Icon compiled in and set at runtime.
- Windows signing path documented: `sign.ps1` (self-sign + timestamp),
  `deploy-cert.ps1` (trust per PC), with the honest note that only an EV cert
  clears SmartScreen everywhere. For a public tool, also document "just run from
  source" as the zero-friction path.
- `resources/data/*.db` and private overlays are git-ignored so no data ships.
- **Docker option** for teams who prefer a local service or CI usage:
  `docker run -v ./my-configs:/app/resources configgen:latest` — runs the CLI
  interface, no GUI. Supports API key auth for automated pipelines.
- **Auto-update check.** On startup, compare local version against the latest
  GitHub release tag via the GitHub API. Display a non-blocking notification if
  an update is available. Disable-able via a setting.

---

## 17. Tests

- Engine: schema loading (all field types, conditionals, documents/hooks),
  validation, coercion, network arithmetic, multi-document render.
- **Schema validator:** malformed YAML, missing fields, bad references, duplicate
  keys, invalid regex, defaults violating patterns.
- **Extractor:** AST parsing for all Jinja2 constructs (variables, loops,
  conditionals, dotted access), mismatch detection, scaffold generation.
- DB service: named queries against a tiny fixture, parameter binding, missing-DB
  behaviour, connection release, health check.
- Hook layer: hook loading, Services, HookError surfacing.
- **Bulk:** CSV parsing, per-row validation, partial-success handling, batch
  manifest generation, per-row log entries.
- **Diff:** identical files, added/removed lines, multi-document diff.
- **Preflight:** IOS checks, JunOS checks, custom check registration.
- **Versioning:** save creates history entry, manifest updates, restore works.
- **Auth:** hashing, lockout, grants, API keys, profile fields, connection
  release, forced password change.
- **RBAC:** role enforcement on every operation — Config Engineer cannot access
  template editor endpoints, Template Engineer cannot delete templates, group
  scoping filters correctly per role.
- **Generation log:** entries created on generate, bulk batch linking, permission
  filtering (Config Eng sees own only, Template Eng sees group, Admin sees all).
- **Group scoping:** user assigned to Group A cannot see Group B templates,
  Admin sees all groups, ungrouped templates visible to everyone.
- GUI (headless, offscreen): form build, live validation, multi-doc tabs,
  per-document save, reopen, per-user scope, dashboard reflow, search/filter,
  dark mode toggle, role-appropriate dashboard.
- **Config packs:** export creates valid zip, import extracts and registers,
  conflict detection, permission checks (import is Admin only).
- Registry: auto-discover, orphan detection, missing reference warnings.
- Examples: each shipped example config renders end to end.

---

## 18. Documentation (the GitHub face)

- **README:** what it is, screenshots, quick start (run from source), install,
  the four-line "add a config" pitch, badges (CI, license, Python version).
- **docs/adding-a-config.md:** worked example — form-only, then multi-document,
  then DB-backed — each as schema + template (+ hook). Includes the "template
  first" workflow using `configgen extract --scaffold`.
- **docs/schema-reference.md:** every field type, every option, regex quoting
  gotcha, conditionals, `version`, `tags`, `description`, `preflight`, `status`,
  `group`.
- **docs/hooks.md:** the `build()` contract, `services.db` / `services.net`,
  writing `queries.yaml`, registering custom filters.
- **docs/bulk-generation.md:** CSV format requirements, column-to-field mapping,
  database-driven batches, error handling, batch manifest.
- **docs/roles-and-groups.md:** the three-role model explained, group scoping,
  the full permission matrix, template lifecycle (draft/published/deprecated),
  generation log, solo user mode vs. team setup.
- **docs/troubleshooting.md:** the top errors users will hit:
  - "No database found" → where to put the .db and queries.yaml
  - "Unknown variable in template" → StrictUndefined error explained
  - "WinError 32" → the file lock issue (fixed, but documented)
  - "Pattern mismatch" → how to debug regex, single-quote reminder
  - "Hook not found" → hook: value doesn't match filename
  - "Schema validation failed" → read the error, check field types
  - "Preflight warning" → common IOS/JunOS syntax mistakes
  - "Bulk generation partial failure" → check the error CSV
  - "API key rejected" → key revoked or user locked out
  - "Version conflict on import" → rename or overwrite
  - "Permission denied" → check your role and group assignment
- **examples/:** four fictional configs proving form-only, multi-document,
  DB-backed, and bulk-ready, with a sample `.db` and sample CSV — the thing a
  newcomer copies from.

---

## 19. Carried-over fixes (must survive the rebuild)

These were found the hard way; the rebuild keeps them:

- `_coerce_string` must `return value` (missing return rendered every string
  field as `None`).
- SQLite connections open via a context manager that **closes** (Windows file
  lock / `WinError 32`).
- PyInstaller entry point is an absolute-import launcher, not `__main__.py`.
- Regex patterns single-quoted in YAML (`\d` breaks double-quoted).
- Port/lookup fields have no default; the expected format is placeholder text.
- Multi-document profile reopen strips the document token to find the shared
  `.json`.
- Preview tabs styled so inactive tabs are readable.
- Quick-start tiles use a reflowing flow layout (no horizontal overflow).
- Field defaults must satisfy their own pattern (tested).
- Template `Check` uses `StrictUndefined`; hook-driven configs are excluded
  from the declarative variable check.

---

## 20. Build phases

| Phase | Content | Done when |
|-------|---------|-----------|
| **0** | **Scaffold:** repo init, pyproject.toml, .gitignore, LICENSE, GitHub Actions CI (pytest on push), pre-commit hooks (ruff + black), Dependabot | `git push` triggers green CI |
| **1** | Core: schema, schema_validator, validators, values, renderer, exporter + tests | CLI can `check` / `list` / `generate` a form-only example |
| **2** | Extractor: Jinja2 AST parsing, mismatch detection, scaffold generation + tests | `configgen extract` works, `--scaffold` generates YAML |
| **3** | Generic db service + `queries.yaml` + `from_db` + db health check + tests | a DB-backed example renders headless |
| **4** | Hook layer + Services(net, db) + example hook + tests | a derived example renders headless |
| **5** | Multi-document render + per-document save + reopen | a multi-doc example round-trips |
| **6** | Auth + three roles + groups + group scoping + API keys + generation log + tests | login works, role enforcement tested, log entries created |
| **7** | Bulk generation: CSV parsing, per-row validation, batch save, per-row logging + tests | `configgen bulk` processes a CSV end to end with log entries |
| **8** | Diff: core differ, current-vs-last comparison + tests | `configgen diff` produces correct unified diff |
| **9** | Versioning: history, manifest, restore + tests | saves create history, restore works |
| **10** | Preflight: IOS/JunOS/Nokia SR/Huawei VRP8/generic checks, custom check registration + tests | preflight catches intentional syntax errors in test configs |
| **11** | Registry: auto-discover, orphan detection, reference validation | `configgen plugins` lists all, `--check` validates |
| **12** | GUI: theme (+ dark mode), widgets, form, login, role-aware dashboard (search/filter/tiles per role), generator (preview + diff), keyboard shortcuts | full click-through: Admin sees everything, Config Eng sees only published |
| **13** | Admin GUI: template editor (+ extract + history + publish/deprecate), user admin (create users, assign roles, manage groups, assign groups, API keys), generation log viewer, bulk dialog, about | all admin flows work, role permissions enforced in UI |
| **14** | Config pack export/import + permission checks + tests | round-trip export → import works, import is Admin only |
| **15** | Packaging: PyInstaller, signing, icon, Dockerfile, auto-update check | signed exe builds, Docker runs CLI with API key auth |
| **16** | Docs + examples + README + LICENSE + troubleshooting + roles-and-groups guide | a stranger can add a config, set up a team, and assign roles from docs alone |

Each phase ends green and is committed; examples are the acceptance test.

---

## 21. What is explicitly out of scope (v1)

These are valuable but would bloat the project. They belong in v2 or never:

- **Web UI.** The desktop + CLI model is correct for v1. A web UI is a separate
  project (and the SaaS version of this idea).
- **Multi-user server.** SQLite auth is fine for a desktop tool. No PostgreSQL,
  sessions, or API servers.
- **Config deployment/push.** Generating configs is the scope. Pushing them to
  devices is Ansible's job.
- **AI-assisted template writing.** Great for the SaaS version, but for a desktop
  open-source tool it adds API key management, cost, and an external dependency.
- **Real-time collaboration.** Single-user desktop tool. Teams share via Git and
  config packs.
- **Approval workflows.** The draft/published lifecycle is the lightweight
  alternative. Formal approval chains are a SaaS feature.
- **Template marketplace.** The config pack format is the foundation; the
  marketplace is a future web service.
- **Integration with NetBox/Nautobot.** The generic db service is the abstraction
  layer. A future plugin could sync from NetBox to a local SQLite, but that's v2.

---

## 22. Open items to confirm before phase 0

1. **License** — MIT (permissive, common for tools) unless you prefer otherwise.
2. **Terminology** — `group` + `name` + `id` to replace `customer`/`device`. Good,
   or keep `customer`/`device` as generic labels?
3. **Example domain** — the fictional examples should be non-telecom (e.g. a
   generic "server provisioning" or "device onboarding") so nothing hints at the
   private use case. Agree?
4. **`queries.yaml` vs inline** — named queries in a YAML file (recommended,
   auditable) vs. hooks writing SQL directly. Confirm the YAML approach.
5. **Bulk input format** — CSV as primary, XLSX as secondary? Or support both
   from day one?
6. **Docker priority** — build the Dockerfile in phase 15 (packaging), or earlier
   to use in CI?
7. **Default admin credentials** — first launch creates admin/admin with forced
   password change? Or interactive setup wizard?