# On-Prem Authoritative Foundation

Bring up the day-1 on-prem foundation where NetBox-backed state gates IPAM-driven platform VM expansion.

Outcome: subsequent platform services provision from authoritative NetBox-backed intent.

This blueprint uses the canonical operation authority contract. Its steps require
the logical `primary_ipam` authority and the `inventory_ipam` capability; the
top-level binding selects NetBox. The dependent steps do not select NetBox or
repeat its module-state gate.

## Chain

```text
core/onprem/network-sdn
  -> platform/onprem/netbox
  -> platform/onprem/platform-vm
  -> platform/onprem/postgresql-core
  -> platform/onprem/platform-vm
```

See [blueprint.yml](blueprint.yml) for the full contract.

## Usage

```bash
hyops blueprint validate --ref onprem/authoritative-foundation@v1 --blueprints-root blueprints
hyops blueprint preflight --env <env> --ref onprem/authoritative-foundation@v1 --blueprints-root blueprints
hyops blueprint deploy --env <env> --ref onprem/authoritative-foundation@v1 --blueprints-root blueprints --execute
```
