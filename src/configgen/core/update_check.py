"""Auto-update check (§16) — compares the running version against the
latest GitHub release tag. Stdlib-only (`urllib`), so a lean CLI/Docker
install never needs an HTTP client dependency just for this.

Nothing here runs at import time or on a schedule; a caller (the GUI's
startup check, or a future CLI flag) decides when to call
`check_for_update()`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from configgen.appinfo import __version__

DEFAULT_REPO = "lahcenkh/ConfigGen"
_API_URL = "https://api.github.com/repos/{repo}/releases/latest"


class UpdateCheckError(Exception):
    """The check couldn't complete (network/API failure) — never means
    "no update available," which callers must not conflate with this."""


def _parse_version(text: str) -> tuple[int, ...]:
    """ "v1.2.3" / "1.2.3" -> (1, 2, 3); a non-numeric trailing suffix like
    "1.2.3-beta" is truncated at the first non-digit run per component,
    which is good enough for simple newer-than comparison."""
    text = text.strip().lstrip("vV")
    parts = []
    for chunk in text.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_update_available(current_version: str, latest_tag: str) -> bool:
    return _parse_version(latest_tag) > _parse_version(current_version)


def latest_release_tag(repo: str = DEFAULT_REPO, *, timeout: float = 3.0) -> str:
    url = _API_URL.format(repo=repo)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ConfigGen-update-check",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise UpdateCheckError(str(exc)) from exc

    tag = payload.get("tag_name")
    if not tag:
        raise UpdateCheckError("GitHub API response had no 'tag_name'")
    return tag


def check_for_update(repo: str = DEFAULT_REPO, *, timeout: float = 3.0) -> str | None:
    """Returns the latest release tag if it's newer than this build, else
    None. Raises UpdateCheckError if the check itself failed — a caller
    that wants "silently do nothing on failure" should catch that."""
    latest_tag = latest_release_tag(repo, timeout=timeout)
    if is_update_available(__version__, latest_tag):
        return latest_tag
    return None
