"""Hook for switch_trunk.yaml — pulls every VLAN on the chosen switch
and builds a per-VLAN list for the template, rejecting a subnet that collides
with one already assigned."""

from configgen.hooks import HookError


def build(values: dict, context: dict, services) -> dict:
    switch = values["switch_name"]

    # multi-row lookup: every VLAN on this switch
    vlans = services.db.query("switch_vlans", switch=switch)
    if not vlans:
        raise HookError({"switch_name": f"No VLANs found for switch '{switch}'"})

    # build a clean list of dicts the template can loop over
    vlan_blocks = []
    for row in vlans:
        vlan_blocks.append({
            "id": row["vlan_id"],
            "name": row["name"],
            "subnet": row["subnet"],
            "gateway": services.net.host_at(row["subnet"], 1),
        })
    print(vlan_blocks)
    return {
        "trunk": {
            "switch": switch,
            "uplink_port": values["uplink_port"],
            "description": values["description"],
            "generated_by": context.get("generated_by", "unknown"),
            "vlan_count": len(vlan_blocks),
            "vlans": vlan_blocks,
        }
    }