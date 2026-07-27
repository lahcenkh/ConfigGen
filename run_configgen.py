"""PyInstaller entry point (§16, §19: a relative import or package
`__main__.py` fails once frozen — this is a plain top-level script with
only absolute imports, run directly by the built exe)."""

import sys

from configgen.app import main

if __name__ == "__main__":
    sys.exit(main())
