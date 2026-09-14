"""Interface implemented by shipped authority providers."""

from __future__ import annotations

from typing import Protocol

from .models import AuthorityContext, AuthorityDeclaration, AuthorityEvaluation


class AuthorityProvider(Protocol):
    name: str
    capabilities: frozenset[str]

    def validate_configuration(
        self,
        declaration: AuthorityDeclaration,
        context: AuthorityContext,
    ) -> None: ...

    def evaluate(
        self,
        declaration: AuthorityDeclaration,
        context: AuthorityContext,
    ) -> AuthorityEvaluation: ...
