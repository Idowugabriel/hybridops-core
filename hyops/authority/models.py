"""Typed values shared by authority providers and their resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class AuthorityDeclaration:
    """A logical authority bound to a configured provider."""

    logical_ref: str
    capability: str
    provider: str
    config: Mapping[str, Any] = field(default_factory=dict)
    compatibility: bool = False


@dataclass(frozen=True)
class AuthorityRequirement:
    """The logical authority and capability required by one operation."""

    logical_ref: str
    capability: str
    compatibility: bool = False


@dataclass(frozen=True)
class AuthorityContext:
    """Runtime inputs available to every authority provider."""

    runtime_root: Path
    state_root: Path
    env: Mapping[str, str]
    assumed_state_ok: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AuthorityEvaluation:
    """Secret-free provider evaluation returned to the generic resolver."""

    healthy: bool
    state: str
    result: str
    instance: str = ""
    endpoint: str = ""
    revision: str = ""
    freshness: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorityReceipt:
    """Attributable evidence that an operation authority was admitted."""

    logical_ref: str
    capability: str
    provider: str
    state: str
    result: str
    instance: str = ""
    endpoint: str = ""
    revision: str = ""
    freshness: Mapping[str, Any] = field(default_factory=dict)

    def to_evidence(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "logical_authority": self.logical_ref,
            "capability": self.capability,
            "provider": self.provider,
            "verified_state": self.state,
            "result": self.result,
        }
        if self.instance:
            payload["instance"] = self.instance
        if self.endpoint:
            payload["endpoint"] = self.endpoint
        if self.revision:
            payload["revision"] = self.revision
        if self.freshness:
            payload["freshness"] = dict(self.freshness)
        return payload
