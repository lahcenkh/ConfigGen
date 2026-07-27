# Bulk generation

Generate many configs from one CSV/XLSX file (or one database query) in a
single pass, instead of filling in the form one device at a time.

```text
input (CSV/XLSX or a query) -> validate every row -> collect errors -> render the valid rows -> save to one batch folder -> log each one
```

Every row is validated independently — one bad row never blocks the
others. You get a summary ("N valid, M errors"), can fix and re-import,
or just take the valid rows and deal with the rest later.

## CSV/XLSX format

**Column headers must match schema field keys exactly.** Extra columns
are ignored; a missing column for a required field fails that row's
validation the same way an empty form field would.
`examples/sample_bulk.csv` pairs with
`examples/schemas/server_provisioning.yaml`:

```csv
hostname,management_ip,subnet,timezone,admin_username,ssh_port,enable_firewall,notes
web01-nyc,10.20.30.5,10.20.30.0/24,America/New_York,svcadmin,22,true,initial batch
web02-nyc,10.20.30.6,10.20.30.0/24,America/New_York,svcadmin,22,true,initial batch
web01-lon,10.40.50.5,10.40.50.0/24,Europe/London,svcadmin,2222,false,initial batch
BAD HOST!,10.20.30.7,10.20.30.0/24,America/New_York,svcadmin,22,true,intentionally invalid hostname
```

(That last row is deliberately broken, to show partial-failure handling
below — `BAD HOST!` fails `hostname`'s pattern.) Every cell arrives as
text, so `bool` fields accept `true`/`false`/`1`/`0`/`yes`/`no`
case-insensitively, same as anywhere else (§ [schema-reference.md](schema-reference.md#field-types)).

```bash
configgen bulk examples/schemas/server_provisioning.yaml \
  --input examples/sample_bulk.csv --output /tmp/out --errors-out /tmp/errors.csv
```

```text
3 valid, 1 errors
  row 5: hostname: 'BAD HOST!' does not match the expected pattern (expected like web01-nyc)
output: /tmp/out/unknown/ungrouped/batch_20260727213452
manifest: /tmp/out/unknown/ungrouped/batch_20260727213452/batch_manifest.json
```

Row numbers are 1-based **including the header** — so the first data row
is row 2, matching how you'd point at it in a spreadsheet. `--errors-out`
writes just the failures as a two-column CSV (`row_number,errors`) for
handing back to whoever supplied the data.

## Database-driven batches

Instead of a file, a named query from the project's `data/queries.yaml`
(§ [prepare-hooks.md](prepare-hooks.md#servicesdb-and-queriesyaml)) can
supply the rows directly — the query must be declared `returns: rows`,
and each returned row's columns are mapped to schema fields by name,
exactly like a CSV's columns:

```bash
configgen bulk <schema_id> --query devices_by_site --param site=us-east --output ./batch/
```

`--param key=value` (repeatable) binds the query's named parameters. Use
this when the source of truth is already a database — an inventory
system, a CMDB export — so there's no CSV to keep in sync by hand.

## What gets written

- Output lands under `output/<username>/<group>/batch_<timestamp>/`, one
  file per valid row (same naming convention as a single Generate).
- **`batch_manifest.json`** in that same folder records the whole run —
  what was generated, from which input, with which schema version:

  ```json
  {
    "batch_id": "5a3d0774a87c4633a56913bfb314ae88",
    "schema_id": "server_provisioning",
    "schema_version": 1,
    "source": "examples/sample_bulk.csv",
    "username": "unknown",
    "generated_at": "2026-07-27T21:34:52.726253",
    "valid_count": 3,
    "error_count": 1,
    "rows": [
      {
        "row_number": 2,
        "inputs": { "hostname": "web01-nyc", "...": "..." },
        "documents": { "primary": "ungrouped_server_provisioning_web01-nyc_primary_20260727213452.txt" }
      }
    ],
    "errors": [
      { "row_number": 5, "errors": { "hostname": "'BAD HOST!' does not match the expected pattern (expected like web01-nyc)" } }
    ]
  }
  ```

  A row with preflight warnings also gets a `preflight_warnings` key
  (`{doc_key: [warning, ...]}`) alongside `documents`.
- Every valid row gets its own entry in the generation log (§ [roles-and-groups.md](roles-and-groups.md#generation-log)),
  all sharing the same `bulk_batch_id` — so "who ran this batch, and
  what did row 47 actually produce" is always answerable later, and
  the GUI's generation log viewer can group them back together.

## Permissions

All three roles can run bulk generation, but only against templates they
can already see (§ [roles-and-groups.md](roles-and-groups.md)): Config
Engineers are limited to published templates in their own groups,
Template Engineers to all templates in their groups, Admins to
everything. Bulk generation never bypasses the same visibility rules a
single Generate follows.

## GUI

The dashboard's **Bulk Generate** button (visible to every role) opens a
file picker for the CSV/XLSX, a progress indicator while it runs, and an
error summary table at the end with **Export Errors to CSV** — the same
`--errors-out` output as the CLI, one click away.
