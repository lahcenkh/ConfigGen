"""Prepare hook for device_provisioning.yaml — looks up the device's vendor
in the database and derives its management IP from the submitted subnet.
Pure Python, unit-testable in isolation (see docs/prepare-hooks.md)."""

from configgen.prepare import PrepareError


def build(values: dict, context: dict, services) -> dict:
    device = services.db.query("device", name=values["device_name"])
    if not device:
        raise PrepareError({"device_name": f"Unknown device '{values['device_name']}'"})

    return {
        "cfg": {
            "name": values["device_name"],
            "mgmt_ip": services.net.host_at(values["subnet"], 1),
            "vendor": device["vendor"],
        }
    }
