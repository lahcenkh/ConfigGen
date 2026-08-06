# CLI reference

Everything the GUI does, `configgen` can do headless — CI, a server, a
cron job, or just a faster loop while you're iterating on a schema. This
doc is the command-by-command reference; for a guided walkthrough of
*writing* a config in the first place, see
[adding-a-config.md](adding-a-config.md).

## Running it

Two ways to get the `configgen` command, both giving you the exact same
CLI:

```bash
pip install -e .              # from source — no [gui] extra, no PySide6/Qt
configgen --help
```

```powershell
.\packaging\build.ps1          # packaged — see README.md#building-the-windows-exe
.\dist\ConfigGen-CLI\ConfigGen-CLI.exe --help
```

The packaged `ConfigGen-CLI.exe` has no `resources\` of its own — point
`--dir` (and similar flags below) at wherever your project's
schemas/templates/data actually live, e.g. `..\ConfigGen\resources\schemas`
if you want it operating on the same project the GUI build is seeded
with. Every example below uses the bare `configgen` form; substitute
`.\ConfigGen-CLI.exe` if you're running the packaged build.

```bash
configgen --version
configgen <command> --help      # every subcommand has its own --help
```

Every command returns exit code `0` on success and `1` on failure —
scriptable without parsing output.

## Two authentication patterns

Solo use needs no login at all — most commands below run happily with
nothing but a `--dir`. Two different flag sets show up depending on what
a command does:

- **`list` / `generate` / `bulk` / `diff`** — `--username` alone is just
  a label recorded in the output (back-compat, solo-mode-friendly, no
  `users.db` touched). Add `--password` (with `--username`) or `--api-key`
  to authenticate for real, which enforces role/group visibility and logs
  the generation. See [roles-and-groups.md](roles-and-groups.md).
- **`user` / `group` / `apikey` / `log` / `export` / `import`** — always
  require a real, already-existing actor: `--as-username` +
  `--as-password`, or `--as-api-key`. There's no unauthenticated path to
  these, on the CLI or in the GUI.

First run bootstraps `admin`/`admin` (in `users.db`, next to wherever
`--users-db` points, default the app root) — change that password
immediately:

```bash
configgen user passwd admin "a real password" --as-username admin --as-password admin
```

## Validating and exploring schemas

```bash
configgen check examples/schemas/router_base_config.yaml
```

Structural validation — field types are real, regex patterns compile,
`required_if`/`visible_if` reference real fields, the template file
exists — plus an advisory warning for any template variable no field or
hook supplies. See
[schema-reference.md#validating-a-schema](schema-reference.md#validating-a-schema).

```bash
configgen list --dir examples/schemas
configgen list --dir resources/schemas --username carol --password ...   # scoped to carol's role/groups
```

Lists every schema in a directory (id, name, status, version) — or, with
real auth, only the ones that user can actually see.

```bash
configgen extract path/to/switch_base.j2                       # list the variables it references
configgen extract path/to/switch_base.j2 --scaffold             # print a starter schema YAML
configgen extract templates/widget.j2 --check schemas/widget.yaml   # report mismatches
```

The "write the template first" workflow — see
[adding-a-config.md#writing-the-template-first](adding-a-config.md#writing-the-template-first).

```bash
configgen plugins --dir examples/schemas
configgen plugins --dir examples/schemas --check
```

Lists every discovered hook/filter/preflight check and flags orphans
(nothing references them); `--check` instead validates that every
schema's `hook:`/`preflight:` actually resolves to a real file, failing
loud (exit `1`) if not — useful as a CI gate before merging a schema
change.

## Generating configs

```bash
configgen generate router_base_config \
  --dir examples/schemas \
  --values examples/sample_router_values.json \
  --output /tmp/out \
  --username tester
```

`schema` is an id (resolved by scanning `--dir`) or a direct path to the
YAML file. `--values` is a JSON file of raw form input — the same shape
the GUI form submits. Prints each saved document's path and the shared
`.json` profile path; with a `hook:` schema, runs it between validation
and rendering (§ [hooks.md](hooks.md)) and prints `FAILED hook:` with the
field-level errors if it rejects the input.

```bash
configgen generate device_provisioning \
  --dir examples/schemas --values examples/sample_device_provisioning_values.json \
  --output /tmp/out --username bob --password "bob's password"
```

Adding real auth (`--password` or `--api-key`) enforces that bob can
actually see `device_provisioning` (role + group) and records the
generation in his log entry — otherwise `--username` is just a label.

```bash
configgen bulk server_provisioning --dir examples/schemas \
  --input examples/sample_bulk.csv --output /tmp/out --errors-out /tmp/errors.csv
```

Batch-generate from a CSV/XLSX — one row per config, partial failure
isolated per row. Full format, database-driven batches (`--query`
instead of `--input`), and the manifest shape are in
[bulk-generation.md](bulk-generation.md).

```bash
configgen diff /tmp/out/old.txt /tmp/out/new.txt
configgen diff router_base_config rtr-core-01 --last --username tester
```

Unified diff between two explicit files, or (`--last`) between the two
most recent saved outputs for a schema id + identity value — the same
lookup the GUI's **Diff** button uses.

## Version history

```bash
configgen history router_base_config --dir examples/schemas
configgen history router_base_config --save --author bob --note "add SNMPv3"
configgen history router_base_config --restore 2 --author bob
configgen history router_base_config --diff 2 3
```

Snapshot, restore, or diff a schema+template's version history — the CLI
equivalent of the Template Editor's **History** button. With no flags,
lists every saved version (author, timestamp, note).

## Sharing a template

```bash
configgen export router_base_config --dir examples/schemas \
  --output router_base_config.configpack.zip \
  --author bob --description "core router base config" \
  --as-username bob --as-password "bob's password"
```

Bundles a schema + its template + hook + custom preflight check (if any)
into one `.zip` — Admin or Template Engineer only.

```bash
configgen import router_base_config.configpack.zip --overwrite \
  --as-username admin --as-password admin
configgen import router_base_config.configpack.zip --rename router_base_config_v2 \
  --as-username admin --as-password admin
```

Imports it into a project's `resources/` (or `--resources` elsewhere) —
Admin only, since importing can bring in an executable hook. Refuses to
silently clobber an existing schema with the same id; pick `--overwrite`
or `--rename NEW_ID`. See
[troubleshooting.md#version-conflict-on-import-config-pack](troubleshooting.md#version-conflict-on-import-config-pack).

## Database utilities

```bash
configgen db check --queries examples/data/queries.yaml
```

Runs every named query in `queries.yaml` with null parameters and
reports which succeed/fail — catches drift between the query file and
the database it points at, including with the multi-database `databases:`
form (§ [hooks.md#servicesdb-and-queriesyaml](hooks.md#servicesdb-and-queriesyaml)).

## User, group, and API-key management

The CLI equivalent of the GUI's User Admin panel — every command here
needs `--as-username`/`--as-password` or `--as-api-key` for an Admin
actor. Full walkthrough (bootstrapping a team from scratch) in
[roles-and-groups.md#setting-up-a-team](roles-and-groups.md#setting-up-a-team).

```bash
configgen user create bob "a real password" --role template_engineer \
  --as-username admin --as-password admin
configgen user list --as-username admin --as-password admin
configgen user passwd bob "a new password" --as-username admin --as-password admin

configgen group create "Acme Corp" --description "Acme's network templates" \
  --as-username admin --as-password admin
configgen group assign bob "Acme Corp" --as-username admin --as-password admin
configgen group list --as-username admin --as-password admin

configgen apikey create bob --label "CI pipeline" --as-username admin --as-password admin
configgen apikey list bob --as-username admin --as-password admin
configgen apikey revoke 3 --as-username admin --as-password admin

configgen log list --as-username bob --as-password "bob's password"
```

`user passwd` also lets a user change their own password (no `--role`
required for that) — an Admin actor can change anyone's; a non-Admin
actor can only change their own. `apikey list` with no username lists
every key (Admin only); with one, just that user's.

## See also

| Doc | What's in it |
|---|---|
| [adding-a-config.md](adding-a-config.md) | Writing a schema + template from scratch |
| [schema-reference.md](schema-reference.md) | Every field type, every schema option |
| [hooks.md](hooks.md) | The `build()` hook contract, `services.db`/`services.net` |
| [bulk-generation.md](bulk-generation.md) | CSV/database-driven batch generation in full |
| [roles-and-groups.md](roles-and-groups.md) | The three-role model, group scoping, setting up a team |
| [troubleshooting.md](troubleshooting.md) | The errors you'll actually hit, and where to look next (`logs/app.log`) |
