#!/usr/bin/env python3
"""Adopt existing platform VM addresses into the HybridOps NetBox IPAM authority.

purpose: Make a reviewed, conflict-safe bridge from legacy static VM state to IPAM.
maintainer: HybridOps.Tech
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
from typing import Any

from hyops.runtime.module_state import read_module_state
from hyops.runtime.root import require_runtime_selection, resolve_runtime_root


DEFAULT_MODULE_REF = "platform/onprem/platform-vm"
DEFAULT_NETWORK_REF = "core/onprem/network-sdn"


def collect_claims(
    *,
    state_dir: Path,
    module_ref: str,
    state_instances: list[str],
    zone_name: str,
) -> tuple[list[dict[str, str]], list[str]]:
    """Read fixed IPv4 interfaces from ready module state without contacting NetBox."""
    claims: list[dict[str, str]] = []
    warnings: list[str] = []

    for instance in state_instances:
        payload = read_module_state(state_dir, module_ref, state_instance=instance)
        status = str(payload.get("status") or "").strip().lower()
        if status != "ok":
            raise ValueError(
                f"state instance {module_ref}#{instance} is not ready: status={status or 'unknown'}"
            )

        outputs = payload.get("outputs")
        if not isinstance(outputs, dict) or not isinstance(outputs.get("vms"), dict):
            raise ValueError(f"state instance {module_ref}#{instance} has no published VM outputs")

        for logical_name, raw_vm in outputs["vms"].items():
            if not isinstance(raw_vm, dict):
                continue
            interfaces = raw_vm.get("interfaces_configured")
            if not isinstance(interfaces, list):
                warnings.append(f"{instance}:{logical_name}: no interfaces_configured output; skipped")
                continue
            physical_name = str(raw_vm.get("vm_name") or logical_name).strip()
            for nic_index, raw_nic in enumerate(interfaces, start=1):
                if not isinstance(raw_nic, dict):
                    continue
                bridge = str(raw_nic.get("bridge") or "").strip()
                ipv4 = raw_nic.get("ipv4")
                address = str(ipv4.get("address") or "").strip() if isinstance(ipv4, dict) else ""
                if not address or address.lower() == "dhcp":
                    continue
                try:
                    interface = ipaddress.ip_interface(address)
                except ValueError as exc:
                    raise ValueError(
                        f"{instance}:{logical_name}/interfaces[{nic_index}] has invalid IPv4 {address!r}: {exc}"
                    ) from exc
                if not isinstance(interface, ipaddress.IPv4Interface):
                    raise ValueError(
                        f"{instance}:{logical_name}/interfaces[{nic_index}] must contain an IPv4 address"
                    )
                if not bridge:
                    raise ValueError(
                        f"{instance}:{logical_name}/interfaces[{nic_index}] is missing bridge"
                    )
                claims.append(
                    {
                        "state_instance": instance,
                        "logical_vm": str(logical_name).strip(),
                        "vm_name": physical_name,
                        "nic_index": str(nic_index),
                        "bridge": bridge,
                        "address": str(interface),
                        "description": f"hyops:{zone_name}:{str(logical_name).strip()}:{bridge}:{nic_index}",
                    }
                )

    seen: dict[str, str] = {}
    for claim in claims:
        host = str(ipaddress.ip_interface(claim["address"]).ip)
        previous = seen.get(host)
        if previous and previous != claim["description"]:
            raise ValueError(
                f"duplicate address in selected HybridOps state: {host} is claimed by {previous} and {claim['description']}"
            )
        seen[host] = claim["description"]

    if not claims:
        warnings.append("no fixed IPv4 interfaces found; DHCP interfaces are intentionally ignored")
    return claims, warnings


def build_plan(client: Any, claims: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Compare claims with NetBox and return actions without writing anything."""
    from .netbox_api import find_ip_by_address, find_ip_by_description

    plan: list[dict[str, Any]] = []
    for claim in claims:
        address_record = find_ip_by_address(client, address=claim["address"])
        identity_record = find_ip_by_description(client, description=claim["description"])
        address_id = address_record.get("id") if isinstance(address_record, dict) else None
        identity_id = identity_record.get("id") if isinstance(identity_record, dict) else None

        if identity_record:
            identity_address = str(identity_record.get("address") or "").strip()
            if identity_address.split("/", 1)[0] != claim["address"].split("/", 1)[0]:
                action = "conflict"
                reason = f"identity already owns {identity_address}, not {claim['address']}"
            elif address_record and address_id != identity_id:
                action = "conflict"
                reason = "address is also present as a different NetBox record"
            else:
                action = "already_adopted"
                reason = "same identity and address already exist"
        elif address_record:
            owner = str(address_record.get("description") or "").strip()
            assigned_vm = ""
            assigned_object = address_record.get("assigned_object")
            if isinstance(assigned_object, dict):
                virtual_machine = assigned_object.get("virtual_machine")
                if isinstance(virtual_machine, dict):
                    assigned_vm = str(virtual_machine.get("name") or "").strip()
            if not owner and assigned_vm == claim["vm_name"]:
                action = "label_existing"
                reason = "address is attached to the expected VM and has no conflicting owner"
            else:
                action = "conflict"
                owner_label = owner or (f"attached to {assigned_vm}" if assigned_vm else "<unlabelled>")
                reason = f"address already exists with owner {owner_label!r}"
        else:
            action = "reserve"
            reason = "address and identity are absent from NetBox"

        plan.append(
            {
                **claim,
                "action": action,
                "reason": reason,
                "address_record_id": address_id,
                "identity_record_id": identity_id,
            }
        )
    return plan


def apply_plan(client: Any, plan: list[dict[str, Any]]) -> None:
    from .netbox_api import reserve_ip, set_ip_description

    conflicts = [row for row in plan if row.get("action") == "conflict"]
    if conflicts:
        raise RuntimeError("refusing to apply an adoption plan containing conflicts")
    for row in plan:
        action = row.get("action")
        if action == "reserve":
            reserve_ip(
                client,
                address=str(row["address"]),
                description=str(row["description"]),
                status="reserved",
            )
        elif action == "label_existing":
            ip_id = row.get("address_record_id")
            if not isinstance(ip_id, int) or ip_id <= 0:
                raise RuntimeError(f"missing NetBox IP record ID for {row.get('description')}")
            set_ip_description(
                client,
                ip_id=ip_id,
                description=str(row["description"]),
            )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hyops inventory adopt-ipam",
        description="Review or adopt fixed addresses from HybridOps VM state into NetBox IPAM.",
    )
    parser.add_argument("--root", default=None, help="Runtime root override.")
    parser.add_argument("--env", default=None, help="Runtime environment containing the VM state.")
    parser.add_argument("--module-ref", default=DEFAULT_MODULE_REF)
    parser.add_argument(
        "--state-instance",
        action="append",
        required=True,
        help="Managed platform-vm state instance to adopt; repeat for multiple instances.",
    )
    parser.add_argument(
        "--network-env",
        default="shared",
        help="Environment holding the network_sdn authority used to derive zone_name (default: shared).",
    )
    parser.add_argument("--zone", default=None, help="Override the zone name (normally read from network_sdn state).")
    parser.add_argument("--apply", action="store_true", help="Write reservations after all conflicts pass.")
    parser.add_argument("--output", default=None, help="Write the JSON plan to this path as well as stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        require_runtime_selection(args.root, args.env, command_label="inventory adopt-ipam")
        runtime_root = resolve_runtime_root(args.root, args.env)
        network_root = resolve_runtime_root(None, args.network_env)
        network_state = read_module_state(network_root / "state", DEFAULT_NETWORK_REF)
        if str(network_state.get("status") or "").strip().lower() != "ok":
            raise ValueError("network_sdn authority is not ready")
        zone_name = str(args.zone or (network_state.get("outputs") or {}).get("zone_name") or "").strip()
        if not zone_name:
            raise ValueError("network_sdn state does not publish zone_name; supply --zone explicitly")

        claims, warnings = collect_claims(
            state_dir=runtime_root / "state",
            module_ref=args.module_ref,
            state_instances=[str(v).strip() for v in args.state_instance if str(v).strip()],
            zone_name=zone_name,
        )

        from hyops.runtime.netbox_env import hydrate_netbox_env

        hydrate_warnings, missing = hydrate_netbox_env(os.environ, runtime_root)
        warnings.extend(hydrate_warnings)
        if missing:
            raise ValueError("missing NetBox runtime values: " + ", ".join(missing))

        from .netbox_api import client_from

        base_url = str(os.environ.get("NETBOX_API_URL") or "").strip()
        token = str(os.environ.get("NETBOX_API_TOKEN") or "").strip()
        client = client_from(base_url=base_url, token=token, dry_run=not args.apply)
        plan = build_plan(client, claims)
        conflicts = [row for row in plan if row.get("action") == "conflict"]
        if args.apply:
            if conflicts:
                raise RuntimeError("conflicts found; no NetBox changes were made")
            apply_plan(client, plan)

        result = {
            "status": "conflict" if conflicts else ("applied" if args.apply else "ready"),
            "runtime_root": str(runtime_root),
            "module_ref": args.module_ref,
            "state_instances": args.state_instance,
            "zone_name": zone_name,
            "warnings": warnings,
            "claims": plan,
        }
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        print(rendered, end="")
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        return 2 if conflicts else 0
    except Exception as exc:
        print(f"ERR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
