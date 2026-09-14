"""Resolve logical operation requirements through registered providers."""

from __future__ import annotations

from collections.abc import Mapping

from .models import (
    AuthorityContext,
    AuthorityDeclaration,
    AuthorityReceipt,
    AuthorityRequirement,
)
from .registry import AuthorityProviderRegistry


class AuthorityResolver:
    def __init__(self, registry: AuthorityProviderRegistry) -> None:
        self._registry = registry

    def enforce(
        self,
        requirement: AuthorityRequirement,
        declarations: Mapping[str, AuthorityDeclaration],
        context: AuthorityContext,
    ) -> AuthorityReceipt:
        declaration = declarations.get(requirement.logical_ref)
        if declaration is None:
            raise ValueError(
                "contract failed: missing authority binding "
                f"'{requirement.logical_ref}' for capability '{requirement.capability}'"
            )
        if declaration.capability != requirement.capability:
            raise ValueError(
                "contract failed: authority capability mismatch "
                f"('{requirement.logical_ref}' declares '{declaration.capability}', "
                f"operation requires '{requirement.capability}')"
            )

        try:
            provider = self._registry.resolve(declaration.provider)
        except ValueError as exc:
            raise ValueError(f"contract failed: {exc}") from exc
        if requirement.capability not in provider.capabilities:
            raise ValueError(
                "contract failed: authority provider capability mismatch "
                f"('{provider.name}' does not support '{requirement.capability}')"
            )

        try:
            provider.validate_configuration(declaration, context)
            evaluation = provider.evaluate(declaration, context)
        except ValueError as exc:
            raise ValueError(
                f"contract failed: authority '{requirement.logical_ref}' "
                f"provider '{provider.name}': {exc}"
            ) from exc
        if not evaluation.healthy:
            detail = evaluation.result or "authority is not ready"
            raise ValueError(
                f"contract failed: authority '{requirement.logical_ref}' "
                f"provider '{provider.name}' is not ready "
                f"(state={evaluation.state or 'unknown'}): {detail}"
            )

        return AuthorityReceipt(
            logical_ref=requirement.logical_ref,
            capability=requirement.capability,
            provider=provider.name,
            state=evaluation.state,
            result=evaluation.result or "admitted",
            instance=evaluation.instance,
            endpoint=evaluation.endpoint,
            revision=evaluation.revision,
            freshness=evaluation.freshness,
        )


_DEFAULT_REGISTRY: AuthorityProviderRegistry | None = None


def default_authority_registry() -> AuthorityProviderRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from .providers.nautobot import NautobotAuthorityProvider
        from .providers.netbox import NetBoxAuthorityProvider

        registry = AuthorityProviderRegistry()
        registry.register(NetBoxAuthorityProvider())
        registry.register(NautobotAuthorityProvider())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY
