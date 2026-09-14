"""Authority provider registration without product branching."""

from __future__ import annotations

from .provider import AuthorityProvider


class AuthorityProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AuthorityProvider] = {}

    def register(self, provider: AuthorityProvider) -> None:
        name = str(provider.name or "").strip().lower()
        if not name:
            raise ValueError("authority provider name is required")
        if name in self._providers:
            raise ValueError(f"authority provider already registered: {name}")
        self._providers[name] = provider

    def resolve(self, name: str) -> AuthorityProvider:
        token = str(name or "").strip().lower()
        provider = self._providers.get(token)
        if provider is None:
            available = ", ".join(sorted(self._providers)) or "none"
            raise ValueError(
                f"unknown authority provider '{token or '<empty>'}' "
                f"(registered: {available})"
            )
        return provider

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
