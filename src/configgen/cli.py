"""Headless entry point. Subcommands (list / check / generate / extract / bulk /
diff / history / plugins) land phase by phase; only --version exists so far."""

import argparse
import sys

from configgen.appinfo import APP_NAME, __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="configgen", description=f"{APP_NAME} CLI")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
