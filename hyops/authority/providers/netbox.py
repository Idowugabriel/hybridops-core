"""NetBox binding for the operation authority contract."""

from __future__ import annotations

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from hyops.runtime.module_state import read_module_state
from hyops.runtime.netbox_env import (
    hydrate_netbox_env,
    infer_netbox_api_url_from_state,
    normalize_netbox_api_url,
    resolve_netbox_authority_root,
)

from ..models import AuthorityContext, AuthorityDeclaration, AuthorityEvaluation
from ._common import (
    config_bool,
    config_positive_number,
    endpoint_identity,
    enforce_state_freshness,
    normalized_base_url,
    open_no_redirect,
    require_known_config,
)


NETBOX_MODULE_REF = "platform/onprem/netbox"


class NetBoxAuthorityProvider:
    name = "netbox"
    capabilities = frozenset({"inventory_ipam"})
    _CONFIG_KEYS = {
        "instance_id",
        "live_check",
        "max_state_age_s",
        "timeout_s",
        "verify_tls",
    }

    def validate_configuration(
        self,
        declaration: AuthorityDeclaration,
        context: AuthorityContext,
    ) -> None:
        del context
        config = declaration.config
        require_known_config(config, self._CONFIG_KEYS)
        config_bool(config, "live_check", False)
        config_bool(config, "verify_tls", True)
        config_positive_number(config, "timeout_s", 5.0)
        config_positive_number(config, "max_state_age_s")
        instance_id = config.get("instance_id")
        if instance_id is not None and not str(instance_id).strip():
            raise ValueError("config.instance_id must be a non-empty string")

    def evaluate(
        self,
        declaration: AuthorityDeclaration,
        context: AuthorityContext,
    ) -> AuthorityEvaluation:
        env = {str(key): str(value) for key, value in context.env.items()}
        authority_root, authority_error = resolve_netbox_authority_root(
            env,
            context.runtime_root,
        )
        if authority_error:
            raise ValueError(f"invalid NetBox authority configuration: {authority_error}")
        authority_root = authority_root or context.runtime_root
        state_root = (authority_root / "state").resolve()

        assumed = NETBOX_MODULE_REF in context.assumed_state_ok
        state: dict[str, Any] = {}
        if assumed:
            state_status = "planned-ok"
        else:
            try:
                state = read_module_state(state_root, NETBOX_MODULE_REF)
            except Exception:
                state = {}
            state_status = str(state.get("status") or "missing").strip().lower()
            if state_status != "ok":
                return AuthorityEvaluation(
                    healthy=False,
                    state=state_status,
                    result=(
                        f"required module state is not ok "
                        f"({NETBOX_MODULE_REF}, status={state_status})"
                    ),
                    instance=str(declaration.config.get("instance_id") or authority_root.name),
                )

        max_age_s = config_positive_number(declaration.config, "max_state_age_s")
        freshness = (
            {"state": "planned"}
            if assumed
            else enforce_state_freshness(state, max_age_s)
        )
        endpoint = ""
        live_check = config_bool(declaration.config, "live_check", False)
        if live_check:
            warnings, missing = hydrate_netbox_env(env, context.runtime_root)
            if missing:
                hint = f"; {warnings[0]}" if warnings else ""
                return AuthorityEvaluation(
                    healthy=False,
                    state=state_status,
                    result=f"missing required NetBox env keys: {', '.join(missing)}{hint}",
                    instance=str(declaration.config.get("instance_id") or authority_root.name),
                    freshness=freshness,
                )
            raw_url = normalize_netbox_api_url(str(env.get("NETBOX_API_URL") or ""))
            base_url = normalized_base_url(raw_url, product="NetBox")
            endpoint = endpoint_identity(base_url)
            error = _probe_netbox_api(
                base_url=base_url,
                token=str(env.get("NETBOX_API_TOKEN") or ""),
                timeout_s=float(config_positive_number(declaration.config, "timeout_s", 5.0) or 5.0),
                verify_tls=config_bool(declaration.config, "verify_tls", True),
            )
            if error:
                return AuthorityEvaluation(
                    healthy=False,
                    state=state_status,
                    result=error,
                    instance=str(declaration.config.get("instance_id") or authority_root.name),
                    endpoint=endpoint,
                    freshness=freshness,
                )
        else:
            inferred_url = infer_netbox_api_url_from_state(authority_root)
            if inferred_url:
                try:
                    endpoint = endpoint_identity(
                        normalized_base_url(inferred_url, product="NetBox")
                    )
                except ValueError:
                    endpoint = ""

        revision = str(state.get("run_id") or state.get("updated_at") or "")
        return AuthorityEvaluation(
            healthy=True,
            state=state_status,
            result="admitted",
            instance=str(declaration.config.get("instance_id") or authority_root.name),
            endpoint=endpoint,
            revision=revision,
            freshness=freshness,
        )


def _probe_netbox_api(
    *,
    base_url: str,
    token: str,
    timeout_s: float,
    verify_tls: bool,
) -> str:
    if not token.strip():
        return "NETBOX_API_TOKEN is empty"
    probe_url = f"{base_url.rstrip('/')}/api/dcim/sites/?limit=1"
    request = Request(
        probe_url,
        headers={"Authorization": f"Token {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with open_no_redirect(
            request,
            timeout_s=timeout_s,
            verify_tls=verify_tls,
        ) as response:
            code = int(getattr(response, "status", 0) or 0)
            return "" if 200 <= code < 300 else f"unexpected HTTP status from NetBox API: {code}"
    except HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        if code in (401, 403):
            return "NETBOX_API_TOKEN is rejected by NetBox API"
        return f"NetBox API returned HTTP {code}"
    except URLError as exc:
        reason = str(getattr(exc, "reason", "") or "").strip() or "connection failed"
        return f"NetBox API unreachable ({reason})"
    except Exception:
        return "NetBox API probe failed"
