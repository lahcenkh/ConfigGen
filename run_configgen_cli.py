"""PyInstaller entry point for the console-mode CLI build (§16, §19: a
relative import or package `__main__.py` fails once frozen — this is a
plain top-level script with only absolute imports, run directly by the
built exe). Wraps the same `configgen.cli:main` the `configgen`
console-script entry point uses when running from source (pyproject.toml's
`[project.scripts]`)."""

import sys

from configgen.cli import main

if __name__ == "__main__":
    sys.exit(main())
