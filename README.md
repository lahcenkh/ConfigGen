# ConfigGen

[![CI](https://github.com/ConfigGen/ConfigGen/actions/workflows/ci.yml/badge.svg)](https://github.com/ConfigGen/ConfigGen/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

A generic, plug-and-play desktop tool (GUI + CLI) for generating text
configurations from a guided form and Jinja2 templates. It grew out of
network configs (router/switch configs are the running example throughout
the docs), but there's nothing network-specific in the engine — anyone can
add a config by dropping in a schema file, a template, and (optionally) a
small Python hook. No changes to the core.

|  |  |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Generator](docs/screenshots/generator.png) |

Config Engineers fill in a form and get a validated, rendered config with
one click. Template Engineers write the schema + Jinja template that
*defines* that form. Admins manage users, groups, and template lifecycle —
see [docs/roles-and-groups.md](docs/roles-and-groups.md) for the full
picture. Or just run it solo, alone, with nobody else's roles or groups to
think about.

## Quick start (from source)

```bash
git clone https://github.com/ConfigGen/ConfigGen.git
cd ConfigGen
pip install -e ".[gui]"   # add the desktop GUI (PySide6/Qt)
configgen-gui              # first run bootstraps admin/admin - change it
```

CLI only, no GUI (e.g. for CI or a server)? Skip the `gui` extra:

```bash
pip install -e .
configgen list --dir examples/schemas
```

The example configs under `examples/` are self-contained (own schemas,
templates, sample database, sample CSV) — try one immediately:

```bash
configgen check examples/schemas/router_base_config.yaml
configgen generate examples/schemas/router_base_config.yaml \
  --values examples/sample_router_values.json --output /tmp/out
```

## Install

- Python 3.10+
- `pip install -e ".[gui]"` for the desktop app, `pip install -e .` for
  CLI-only (see [packaging/Dockerfile](packaging/Dockerfile) for a
  ready-made CLI-only container — `pip install .` there never pulls in
  PySide6/Qt)
- A packaged Windows exe is built via
  [packaging/ConfigGen.spec](packaging/ConfigGen.spec)
  (`pyinstaller packaging/ConfigGen.spec`). Signing it is documented in
  [packaging/sign.ps1](packaging/sign.ps1) — read that file's notes
  first: a self-signed exe still shows an "unknown publisher" warning on
  any machine that hasn't explicitly trusted the certificate
  ([packaging/deploy-cert.ps1](packaging/deploy-cert.ps1)); only a paid
  EV certificate clears that everywhere automatically. For a public,
  open-source tool, "just run from source" is the honest zero-friction
  path.

## Adding a config (the four-line pitch)

```bash
# 1. Write resources/schemas/my_thing.yaml   (fields + template name)
# 2. Write resources/templates/my_thing.j2   (the Jinja2 output)
# 3. Optional: resources/hooks/my_thing.py   (a build() hook for derived/DB-backed values)
configgen check resources/schemas/my_thing.yaml   # validates + warns on template/field mismatches
```

That's it — no core code changes, no restart of anything else. The GUI
picks it up as a new dashboard tile the next time it lists schemas. See
[docs/adding-a-config.md](docs/adding-a-config.md) for a full worked
example (form-only → multi-document → database-backed), including the
"write the template first" workflow via `configgen extract --scaffold`.

## Documentation

| Doc | What's in it |
|---|---|
| [docs/adding-a-config.md](docs/adding-a-config.md) | Worked examples: form-only, multi-document, DB-backed |
| [docs/schema-reference.md](docs/schema-reference.md) | Every field type, every schema option |
| [docs/hooks.md](docs/hooks.md) | The `build()` hook contract, `services.db`/`services.net`, custom filters |
| [docs/bulk-generation.md](docs/bulk-generation.md) | CSV/database-driven batch generation |
| [docs/roles-and-groups.md](docs/roles-and-groups.md) | The three-role model, group scoping, template lifecycle |
| [docs/troubleshooting.md](docs/troubleshooting.md) | The errors you'll actually hit, and what they mean |

## Development

```bash
pip install -e ".[dev]"   # dev extra includes the gui extra + test/lint tooling
pytest
ruff check .
black --check .
```

Screenshots above are real renders, not mockups — regenerate them after a
UI change with `python tools/screenshot.py` (uses Qt's offscreen platform,
no display needed).

## License

MIT — see [LICENSE](LICENSE).
