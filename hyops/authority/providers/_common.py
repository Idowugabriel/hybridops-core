"""Small validation and evidence helpers shared by authority providers."""

from __future__ import annotations

from datetime import datetime, timezone
import ssl
from typing import Any, Mapping
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: Any,
        msg: Any,
        headers: Any,
        newurl: Any,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def open_no_redirect(
    request: Request,
    *,
    timeout_s: float,
    verify_tls: bool,
) -> Any:
    """Open a probe without forwarding authority credentials through redirects."""

    handlers: list[Any] = [_RejectRedirects()]
    if request.full_url.startswith("https://") and not verify_tls:
        handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
    return build_opener(*handlers).open(request, timeout=timeout_s)


def require_known_config(config: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(str(key) for key in config if str(key) not in allowed)
    if unknown:
        raise ValueError(f"unknown configuration keys: {', '.join(unknown)}")


def config_bool(config: Mapping[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"config.{key} must be a boolean")
    return value


def config_positive_number(
    config: Mapping[str, Any],
    key: str,
    default: float | None = None,
) -> float | None:
    value = config.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"config.{key} must be a positive number")
    return float(value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_text(value: datetime | None = None) -> str:
    return (value or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(raw: Any) -> datetime | None:
    token = str(raw or "").strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def enforce_state_freshness(
    state: Mapping[str, Any],
    max_age_s: float | None,
) -> dict[str, Any]:
    checked_at = utc_now()
    raw_updated = state.get("updated_at") or state.get("timestamp_utc")
    freshness: dict[str, Any] = {"checked_at": utc_text(checked_at)}
    if raw_updated:
        freshness["state_updated_at"] = str(raw_updated)
    if max_age_s is None:
        return freshness

    freshness["max_age_s"] = max_age_s
    updated_at = parse_timestamp(raw_updated)
    if updated_at is None:
        raise ValueError(
            "authority state freshness cannot be verified because its update timestamp is missing or invalid"
        )
    age_s = max(0.0, (checked_at - updated_at).total_seconds())
    freshness["age_s"] = round(age_s, 3)
    if age_s > max_age_s:
        raise ValueError(
            f"authority state is stale (age_s={round(age_s, 3)}, max_age_s={max_age_s})"
        )
    return freshness


def normalized_base_url(raw: str, *, product: str) -> str:
    token = str(raw or "").strip().rstrip("/")
    if token.endswith("/api"):
        token = token[:-4]
    parsed = urlsplit(token)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{product} endpoint must be an http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            f"{product} endpoint must not contain credentials, query parameters, or fragments"
        )
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def endpoint_identity(base_url: str) -> str:
    parsed = urlsplit(base_url)
    return f"{parsed.scheme}://{parsed.netloc}"
