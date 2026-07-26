# ConfigGen

A generic, plug-and-play desktop tool for generating text configurations from a
guided form and Jinja templates. Anyone can add a config by dropping in a
schema file, a template, and (optionally) a small Python hook — no changes to
the core.

> **Status:** early scaffold (Phase 0). See `goal.md` for the full build plan.

## Quick start (from source)

```bash
pip install -e ".[dev]"
configgen --version
pytest
```

## Adding a config

1. Write a schema YAML in `resources/schemas/`.
2. Write a Jinja template in `resources/templates/`.
3. (Optional) Write a prepare hook in `src/configgen/prepare/`.

See `docs/adding-a-config.md` (coming in a later phase) for a full worked
example.

## License

MIT — see [LICENSE](LICENSE).
