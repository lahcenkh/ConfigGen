import ipaddress

import pytest

from configgen.core.values import CIDRValue, IPCIDRValue, IPValue, NetworkValue


def test_ip_value_renders_as_string():
    ip = IPValue("10.0.0.5")
    assert str(ip) == "10.0.0.5"
    assert ip == "10.0.0.5"


def test_ip_value_rejects_invalid_address():
    with pytest.raises(ValueError):
        IPValue("999.0.0.1")


def test_cidr_value_normalizes_host_bits():
    cidr = CIDRValue("10.0.0.5/24")
    assert str(cidr) == "10.0.0.0/24"


def test_ip_cidr_value_exposes_parts():
    value = IPCIDRValue("10.0.0.5/24")
    assert value.ip == "10.0.0.5"
    assert value.netmask == "255.255.255.0"
    assert value.prefix == 24
    assert str(value) == "10.0.0.5/24"


def test_network_value_netmask_and_prefix():
    net = NetworkValue("10.20.30.0/24")
    assert net.netmask == "255.255.255.0"
    assert net.prefix == 24
    assert str(net) == "10.20.30.0/24"


def test_network_value_first_usable_and_nexthop():
    net = NetworkValue("10.20.30.0/24")
    assert net.first_usable == "10.20.30.1"
    assert net.nexthop == "10.20.30.2"


def test_network_value_host_at_offset_and_getitem():
    net = NetworkValue("10.20.30.0/24")
    assert net.host_at(5) == "10.20.30.5"
    assert net[5] == "10.20.30.5"
    assert net.host_at(0) == "10.20.30.0"


def test_network_value_tiny_subnet_has_no_usable_hosts():
    net = NetworkValue("10.20.30.0/31")
    # /31 point-to-point: ipaddress.hosts() yields both addresses in modern
    # Python, but first_usable/nexthop must never raise on the edge case.
    assert net.first_usable == str(ipaddress.IPv4Network("10.20.30.0/31").network_address)
