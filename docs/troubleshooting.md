# Troubleshooting

The errors you'll actually hit, in the words ConfigGen actually uses, and
what they mean.

## "no database found" / "schema has fields sourced from a database, but no queries.yaml found"

```text
ERROR: schema 'x' has fields sourced from a database, but no queries.yaml found at .../data/queries.yaml
```

A field declares `from_db:`, but the project has no `data/queries.yaml`
next to its `schemas/`/`templates/` folders. Either add one (see
[prepare-hooks.md](prepare-hooks.md#servicesdb-and-queriesyaml)) or drop
`from_db:` from the field if it doesn't actually need one. Note: a
`choice` field with `from_db` but no database configured *doesn't*
error — it just accepts any value unchecked, for a form-only dev path
(`lookup` fields always work this way, database or not).

## "'x' is undefined" (StrictUndefined)

```text
FAILED to render: primary: 'typo_var' is undefined
```

The template references a variable that wasn't in the rendered context
— usually a typo, or a field you renamed in the schema without updating
the template. `configgen check` catches most of these *before* Generate,
as a warning:

```text
WARNING: primary: 'typo_var' has no schema field or hook
```

If the schema has a `prepare:` hook, this warning is suppressed for
variables the hook might supply (it can't see inside the hook to know
for sure) — so a prepare-driven schema needs a real render (or the GUI's
**Test Render**) to catch a typo like this, `check` alone won't.

## "WinError 32" / a database file staying locked

Fixed, but worth knowing why it existed: every `services.db` call used
to open a SQLite connection and could leave it open across calls, which
on Windows blocks a second process (or a later run) from touching the
same file. Every database call now opens its own connection and closes
it before returning, every time — if you see a file-lock error touching
`.db` files, it's not this; check for another process (a DB browser
tool, a second ConfigGen instance) actually holding the file open.

## "does not match the expected pattern"

```text
FAILED validation:
  - hostname: 'BAD HOST!' does not match the expected pattern (expected like web01-nyc)
```

The value didn't match the field's `pattern:` regex. The `(expected
like ...)` part only appears if the field has an `example:` — add one if
it's missing, it's the fastest way to tell someone what's actually
expected. If the pattern itself looks right but still won't match,
check whether it's **double**-quoted in the schema YAML — see
[schema-reference.md](schema-reference.md#the-regex-quoting-gotcha) for
why that silently breaks `\d`/`\w`/etc.

## "hook not found" / "prepare hook not found"

```text
FAILED: schemas/z.yaml
  - prepare: prepare hook not found: nonexistent_hook (expected .../prepare/nonexistent_hook.py)
```

The schema's `prepare:` value doesn't match a real file. It has to be
just the name — `prepare: device_provisioning` resolves to
`prepare/device_provisioning.py`, not the other way around. Also check
you're editing the *project's* `prepare/` folder (a sibling of
`schemas/`), not anywhere inside the installed `configgen` package —
hooks are never loaded from there.

## "Schema validation failed"

`configgen check` (or the GUI's **Check** button) reports every issue it
finds at once, each with a field path — read the whole list, not just
the first line, since fixing one can reveal another (a bad regex often
also breaks the "does the default match its pattern" check, for
example). See [schema-reference.md](schema-reference.md#validating-a-schema)
for the full list of what's checked.

## Preflight warnings

Preflight runs *after* a successful render, looking for common
platform-specific mistakes — it doesn't block Generate, it's a second
opinion. Typical IOS-check warnings: an `interface` block with no
closing `end`, an interface name that doesn't look real, a VLAN ID
outside 1–4094. JunOS-check warnings are usually unbalanced `{ }` brace
counts. If a warning looks wrong for your platform, the check itself is
just a Python file (`preflight/<name>.py` for a custom one, or a
built-in name — `ios`/`junos`/`sros`/`vrp`/`generic`) — adjust or
replace it; it's project-owned like everything else.

## Bulk generation: partial failure

`configgen bulk` always processes every row it can — a summary line
("N valid, M errors") plus `--errors-out <file>.csv` gives you exactly
which rows failed and why, in the same `row_number,errors` shape as the
`batch_manifest.json` it writes either way. Fix the flagged rows in your
source CSV/XLSX and re-run the same command; valid rows from the first
pass aren't affected by re-running. See
[bulk-generation.md](bulk-generation.md) for the full manifest shape.

## "API key rejected" / "invalid or revoked API key"

The API key is either mistyped, or was revoked (`configgen apikey
revoke <key_id>`) — both produce the identical message on purpose, so a
rejected key never leaks whether it *used to* be valid. Check
`configgen apikey list <username>` (Admin) for its current status, and
issue a new one if needed — a revoked key can't be un-revoked.

## "Version conflict on import" (config pack)

```text
a schema with id 'widget' already exists at .../schemas/widget.yaml; pass on_conflict='overwrite' or 'rename'
```

`configgen import` (Admin only) refuses to silently clobber an existing
schema with the same `id:`. Choose one:

```bash
configgen import widget.configpack.zip --overwrite        # replace the existing one
configgen import widget.configpack.zip --rename widget_v2 # keep both, under a new id
```

The GUI's Import Config Pack dialog offers the same two choices when it
hits this.

## "Permission denied" / "lacks required role"

```text
ERROR: user 'bob' (template_engineer) lacks required role ('admin',)
```

Check two things: your **role** (only Admins manage users/groups/API
keys, delete templates, or import config packs — see
[roles-and-groups.md](roles-and-groups.md#the-three-roles) for the full
matrix), and your **group assignment** if the complaint is about not
seeing a template at all rather than an explicit permission error (a
template with `group: "Acme Corp"` is invisible to anyone not assigned
to that group, Admins excepted — that's a visibility filter, not a
denial, so it just won't show up rather than erroring).
