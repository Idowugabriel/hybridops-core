# Operation authority contract

HybridOps separates the authority an operation requires from the product that
supplies it. A blueprint declares a logical authority and a capability, then
binds that declaration to one of the shipped providers:

```yaml
authorities:
  primary_ipam:
    capability: inventory_ipam
    provider: netbox

steps:
  - id: dependent_operation
    module_ref: platform/onprem/platform-vm
    contracts:
      addressing_mode: ipam
      requires_authority:
        ref: primary_ipam
        capability: inventory_ipam
```

The resolver checks that the binding exists, that its declared capability
matches the operation, and that the selected registered provider supports and
admits that capability. Generic blueprint enforcement does not select products.

## Shipped bindings

Both bindings currently support only `inventory_ipam` authority enforcement.
This contract establishes whether a dependent operation may proceed; it does
not claim a general CMDB plugin ecosystem.

### NetBox

NetBox preserves the existing HybridOps behavior. It resolves the established
shared-authority root, requires `platform/onprem/netbox` state to be `ok`, and
optionally performs the existing authenticated API probe. Canonical settings
are:

```yaml
authorities:
  primary_ipam:
    capability: inventory_ipam
    provider: netbox
    config:
      live_check: true
      verify_tls: true
      timeout_s: 5
      max_state_age_s: 3600
      instance_id: shared-netbox
```

`max_state_age_s` is optional. When set, absent, invalid, or older state
timestamps fail closed. NetBox endpoint and token discovery continue to use
`NETBOX_API_URL`, `NETBOX_API_TOKEN`, `HYOPS_NETBOX_AUTHORITY_ROOT`,
`HYOPS_NETBOX_AUTHORITY_ENV`, the runtime credentials file, and the encrypted
runtime vault.

### Nautobot

Nautobot uses its documented `/health/` readiness endpoint and then makes an
authenticated read of `/api/ipam/prefixes/?limit=1`. The second check proves
that the configured token can reach the IPAM API, rather than treating a web
server response alone as authority readiness.

```yaml
authorities:
  primary_ipam:
    capability: inventory_ipam
    provider: nautobot
    config:
      endpoint_env: NAUTOBOT_API_URL
      token_env: NAUTOBOT_API_TOKEN
      api_version: "2.4"
      verify_tls: true
      timeout_s: 5
      instance_id: shared-nautobot
```

The environment-variable names are configurable, but the token value is never
accepted in the blueprint. `endpoint` may be used instead of `endpoint_env`;
URLs containing user information, query strings, or fragments are rejected.
TLS verification is enabled by default. Probes reject redirects, and the
authenticated IPAM check requires a valid paginated JSON response.

The implementation follows the official Nautobot documentation for
[health checks](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/guides/health-checks/),
[REST authentication](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/rest-api/authentication/),
and the [versioned REST API](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/rest-api/overview/).

The shipped Nautobot scope is authority configuration, live readiness,
authenticated IPAM access, and attributable receipts. It does not add Nautobot
allocation, inventory import/export, or a Nautobot deployment module; those are
separate provider lifecycle capabilities.

## Fail-closed behavior and evidence

Missing bindings, unknown providers, unsupported or mismatched capabilities,
invalid configuration, non-ready state, stale bounded state, failed health
checks, unreachable endpoints, and rejected credentials all block the
dependent operation.

An admitted operation records a secret-free authority receipt in preflight and
module execution evidence. The receipt contains the logical reference,
capability, provider, verified state, result, safe instance/endpoint identity,
and available state run ID, update information, or Nautobot `API-Version`.
Tokens and other credential values are never copied into the receipt.

## Legacy NetBox form

Existing blueprints may continue to use:

```yaml
policy:
  ipam_authority: netbox
  netbox_live_api_check: false

contracts:
  addressing_mode: ipam
  requires_authority: netbox
```

This is an explicit compatibility form. It is translated to an internal
`legacy_netbox` logical declaration with capability `inventory_ipam` and the
NetBox provider. State-root resolution, state-only defaults, optional live API
checking, and the previous live-check TLS behavior are preserved. New
blueprints should use the canonical logical form.
