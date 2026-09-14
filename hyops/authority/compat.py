"""Explicit translation of the legacy NetBox blueprint authority form."""

from __future__ import annotations

from typing import Any

from .models import AuthorityDeclaration, AuthorityRequirement


LEGACY_NETBOX_REF = "legacy_netbox"
INVENTORY_IPAM_CAPABILITY = "inventory_ipam"


def legacy_authority_contract(
    requirement: Any,
    policy: dict[str, Any],
) -> tuple[AuthorityRequirement, AuthorityDeclaration] | None:
    token = str(requirement or "").strip().lower()
    if token in {"", "none"}:
        return None
    if token != "netbox":
        return None

    selected = str(policy.get("ipam_authority") or "none").strip().lower()
    if selected != "netbox":
        raise ValueError(
            "contract failed: legacy requires_authority=netbox but "
            "policy.ipam_authority is not netbox"
        )
    declaration = AuthorityDeclaration(
        logical_ref=LEGACY_NETBOX_REF,
        capability=INVENTORY_IPAM_CAPABILITY,
        provider="netbox",
        config={
            "live_check": bool(policy.get("netbox_live_api_check", False)),
            "verify_tls": False,
        },
        compatibility=True,
    )
    return (
        AuthorityRequirement(
            logical_ref=LEGACY_NETBOX_REF,
            capability=INVENTORY_IPAM_CAPABILITY,
            compatibility=True,
        ),
        declaration,
    )
