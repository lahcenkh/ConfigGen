import json
import urllib.error

import pytest

from configgen.core import update_check
from configgen.core.update_check import (
    UpdateCheckError,
    _parse_version,
    check_for_update,
    is_update_available,
    latest_release_tag,
)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


# -- _parse_version / is_update_available (pure) ---------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1.2.3", (1, 2, 3)),
        ("v1.2.3", (1, 2, 3)),
        ("V2.0.0", (2, 0, 0)),
        ("1.2.3-beta", (1, 2, 3)),
        ("1.2", (1, 2)),
        ("1", (1,)),
    ],
)
def test_parse_version(text, expected):
    assert _parse_version(text) == expected


def test_is_update_available_true_when_tag_newer():
    assert is_update_available("0.1.0", "v0.2.0") is True


def test_is_update_available_false_when_tag_older_or_equal():
    assert is_update_available("0.2.0", "v0.1.0") is False
    assert is_update_available("0.1.0", "v0.1.0") is False


# -- latest_release_tag / check_for_update (network, mocked) ---------------------------------------


def test_latest_release_tag_returns_tag_name(monkeypatch):
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        lambda request, timeout=3.0: _FakeResponse({"tag_name": "v9.9.9"}),
    )
    assert latest_release_tag("acme/widget") == "v9.9.9"


def test_latest_release_tag_raises_on_missing_tag_name(monkeypatch):
    monkeypatch.setattr(
        update_check.urllib.request, "urlopen", lambda request, timeout=3.0: _FakeResponse({})
    )
    with pytest.raises(UpdateCheckError, match="tag_name"):
        latest_release_tag()


def test_latest_release_tag_wraps_network_errors(monkeypatch):
    def _raise(request, timeout=3.0):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(update_check.urllib.request, "urlopen", _raise)
    with pytest.raises(UpdateCheckError):
        latest_release_tag()


def test_check_for_update_returns_tag_when_newer(monkeypatch):
    monkeypatch.setattr(update_check, "__version__", "0.1.0")
    monkeypatch.setattr(update_check, "latest_release_tag", lambda repo, timeout=3.0: "v9.9.9")
    assert check_for_update() == "v9.9.9"


def test_check_for_update_returns_none_when_not_newer(monkeypatch):
    monkeypatch.setattr(update_check, "__version__", "9.9.9")
    monkeypatch.setattr(update_check, "latest_release_tag", lambda repo, timeout=3.0: "v0.1.0")
    assert check_for_update() is None
