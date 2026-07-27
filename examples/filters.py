"""Example project filters.py (§6/§12). The renderer discovers this file
automatically and makes every name in FILTERS available as a Jinja filter
— see router_base_config.j2's `| to_wildcard` for a real use."""

import ipaddress


def to_wildcard(netmask: str) -> str:
    """255.255.255.0 -> 0.0.0.255 — the inverse mask an OSPF `network`
    statement expects, derived from the real netmask instead of a value
    hardcoded for one specific prefix length."""
    mask = ipaddress.IPv4Address(netmask)
    wildcard = ipaddress.IPv4Address(int(mask) ^ 0xFFFFFFFF)
    return str(wildcard)


FILTERS = {
    "to_wildcard": to_wildcard,
}
