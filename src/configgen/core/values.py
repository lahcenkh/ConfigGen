"""Typed wrappers for address-shaped field values.

Plain fields (string/int/bool/text) render as their native Python type.
Address fields render as one of these wrappers so a template can pull
`.ip`, `.netmask`, `.first_usable`, etc. without the template author (or a
hook) redoing subnet arithmetic by hand.
"""

from __future__ import annotations

import ipaddress


class IPValue(str):
    """A validated IPv4 host address. Behaves as its string form everywhere."""

    def __new__(cls, raw: str) -> IPValue:
        addr = ipaddress.IPv4Address(raw.strip())
        return super().__new__(cls, str(addr))


class CIDRValue(str):
    """A validated `x.x.x.x/nn` network, passed through as text."""

    def __new__(cls, raw: str) -> CIDRValue:
        network = ipaddress.IPv4Network(raw.strip(), strict=False)
        return super().__new__(cls, f"{network.network_address}/{network.prefixlen}")


class IPCIDRValue(str):
    """A host address plus prefix, e.g. `10.0.0.5/24`.

    Exposes `.ip`, `.netmask`, and `.prefix` for templates that need the
    parts separately, while still rendering as the combined form by default.
    """

    def __new__(cls, raw: str) -> IPCIDRValue:
        iface = ipaddress.IPv4Interface(raw.strip())
        obj = super().__new__(cls, str(iface))
        obj._iface = iface
        return obj

    @property
    def ip(self) -> str:
        return str(self._iface.ip)

    @property
    def netmask(self) -> str:
        return str(self._iface.netmask)

    @property
    def prefix(self) -> int:
        return self._iface.network.prefixlen


class NetworkValue(str):
    """A validated subnet, with helpers for the arithmetic templates need
    most: the first usable host, the conventional next-hop (second usable
    host), the netmask, and arbitrary offsets from the network address."""

    def __new__(cls, raw: str) -> NetworkValue:
        network = ipaddress.IPv4Network(raw.strip(), strict=False)
        obj = super().__new__(cls, str(network))
        obj._network = network
        return obj

    @property
    def netmask(self) -> str:
        return str(self._network.netmask)

    @property
    def prefix(self) -> int:
        return self._network.prefixlen

    def host_at(self, offset: int) -> str:
        """The address `offset` positions past the network address.

        `offset=0` is the network address itself; on a /31 or /32 (no usable
        hosts) that is still a well-defined answer, so no special-casing is
        needed there.
        """
        return str(self._network.network_address + offset)

    def __getitem__(self, offset: int) -> str:
        return self.host_at(offset)

    @property
    def first_usable(self) -> str:
        hosts = list(self._network.hosts())
        return hosts[0].compressed if hosts else str(self._network.network_address)

    @property
    def nexthop(self) -> str:
        """The second usable host — the conventional next-hop address."""
        hosts = list(self._network.hosts())
        if len(hosts) > 1:
            return hosts[1].compressed
        if hosts:
            return hosts[0].compressed
        return str(self._network.network_address)
