#!/usr/bin/env python3
"""Verify approval binding against the pinned Galaxy collection."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = REPO_ROOT / "tools/setup/requirements/ansible.galaxy.yml"


def _common_pin() -> str:
    payload = yaml.safe_load(REQUIREMENTS_PATH.read_text(encoding="utf-8")) or {}
    for collection in payload.get("collections", []):
        if collection.get("name") == "hybridops.common":
            version = str(collection.get("version") or "").strip()
            if version:
                return version
    raise RuntimeError("hybridops.common is not pinned in ansible.galaxy.yml")


def _installed_common() -> tuple[Path, str]:
    search_path = os.environ.get("ANSIBLE_COLLECTIONS_PATH") or os.environ.get(
        "ANSIBLE_COLLECTIONS_PATHS", ""
    )
    for root in filter(None, search_path.split(os.pathsep)):
        collection_root = Path(root) / "ansible_collections/hybridops/common"
        manifest_path = collection_root / "MANIFEST.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = str(manifest.get("collection_info", {}).get("version") or "")
        return collection_root, version
    raise RuntimeError("installed hybridops.common collection was not found")


def _load_runtime(template: Path, placeholder: str, runtime_root: Path) -> dict:
    source = template.read_text(encoding="utf-8").replace(
        placeholder, str(runtime_root)
    )
    namespace = {"__name__": f"acceptance_{template.stem}"}
    exec(compile(source, str(template), "exec"), namespace)
    return namespace


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class ApprovalBindingAcceptance:
    def __init__(self, collection_root: Path, runtime_root: Path) -> None:
        self.requests_dir = runtime_root / "requests"
        self.approvals_dir = runtime_root / "approvals"
        self.executions_dir = runtime_root / "executions"
        self.dispatcher = _load_runtime(
            collection_root
            / "roles/decision_dispatcher/templates/decision-dispatcher.py.j2",
            "{{ decision_dispatcher_root }}",
            runtime_root / "dispatcher",
        )
        self.consumer = _load_runtime(
            collection_root
            / "roles/decision_consumer/templates/decision-consumer.py.j2",
            "{{ decision_consumer_root }}",
            runtime_root / "consumer",
        )
        self.dispatcher["REQUESTS_DIR"] = self.requests_dir

    def dispatch(self, *, requires_approval: bool = True) -> dict:
        result = self.dispatcher["_emit_dispatch_request"](
            decision={
                "decision_id": "decision-acceptance",
                "decision_type": "cutover",
                "rationale": "primary path failed validation",
                "checks": [
                    {"name": "primary_ready", "status": "failed"},
                    {"name": "alternate_ready", "status": "passed"},
                ],
            },
            route={
                "execution_plane": "runner-local",
                "target_kind": "blueprint",
                "target_ref": "dr/postgresql-ha-failover-gcp@v1",
                "target_env": "prod",
                "requires_approval": requires_approval,
            },
            config={"execution_mode": "record-only", "require_approval": True},
        )
        return json.loads(Path(result["request_file"]).read_text(encoding="utf-8"))

    def config(self) -> dict:
        return {
            "dispatch_requests_dir": str(self.requests_dir),
            "approval_dir": str(self.approvals_dir),
            "executions_dir": str(self.executions_dir),
            "execution_mode": "approval-only",
            "require_approval": True,
            "poll_seconds": 5,
        }

    def approve(self, request: dict) -> None:
        _write_json(
            self.approvals_dir / f"{request['dispatch_id']}.approved.json",
            {
                "dispatch_id": request["dispatch_id"],
                "approval_payload_version": request["approval_payload_version"],
                "approval_artifact_sha256": request["approval_artifact_sha256"],
                "approved_by": "acceptance-operator",
                "approved_at": "2026-09-12T12:00:00Z",
            },
        )

    def write_request(self, request: dict) -> None:
        _write_json(self.requests_dir / f"{request['dispatch_id']}.json", request)

    def records(self) -> list[dict]:
        if not self.executions_dir.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.executions_dir.glob("*.json"))
        ]


def _exact_approval(collection_root: Path, root: Path) -> None:
    case = ApprovalBindingAcceptance(collection_root, root)
    request = case.dispatch()
    case.approve(request)
    state = case.consumer["_process"](case.config(), {})
    records = case.records()
    _expect(state["processed_count"] == 1, "exact approval was not processed")
    _expect(len(records) == 1, "exact approval did not emit one execution record")
    _expect(records[0]["status"] == "approved-ready", "unexpected execution status")
    _expect(
        records[0]["approval_artifact_sha256"]
        == request["approval_artifact_sha256"],
        "execution record lost the approved artifact identity",
    )
    _expect(
        records[0]["approval"]["approved_by"] == "acceptance-operator",
        "execution record lost approval audit context",
    )


def _stale_then_corrected(collection_root: Path, root: Path) -> None:
    case = ApprovalBindingAcceptance(collection_root, root)
    request = case.dispatch()
    case.approve(request)
    request["target_ref"] = "dr/postgresql-ha-failover-gcp@v2"
    request["approval_artifact_sha256"] = case.consumer[
        "_approval_artifact_sha256"
    ](request)
    case.write_request(request)

    stale = case.consumer["_process"](case.config(), {})
    _expect(stale["processed_count"] == 0, "stale approval was processed")
    _expect(stale["pending_count"] == 1, "stale request was not retained")
    _expect(
        stale["reason"] == f"stale-approval:{request['dispatch_id']}",
        "stale approval did not report the expected reason",
    )
    _expect(case.records() == [], "stale approval emitted an execution record")

    case.approve(request)
    retried = case.consumer["_process"](case.config(), stale)
    _expect(retried["processed_count"] == 1, "corrected approval was not processed")
    _expect(retried["pending_count"] == 0, "corrected request remained pending")
    _expect(len(case.records()) == 1, "corrected approval did not emit one record")


def _posture_mutation(collection_root: Path, root: Path) -> None:
    case = ApprovalBindingAcceptance(collection_root, root)
    request = case.dispatch()
    case.approve(request)
    request["requires_approval"] = False
    case.write_request(request)
    state = case.consumer["_process"](case.config(), {})
    _expect(state["processed_count"] == 0, "approval posture mutation was processed")
    _expect(state["pending_count"] == 1, "mutated request was not retained")
    _expect(
        state["reason"] == f"stale-approval:{request['dispatch_id']}",
        "approval posture mutation did not fail identity validation",
    )
    _expect(case.records() == [], "approval posture mutation emitted a record")


def _no_approval_route(collection_root: Path, root: Path) -> None:
    case = ApprovalBindingAcceptance(collection_root, root)
    request = case.dispatch(requires_approval=False)
    state = case.consumer["_process"](case.config(), {})
    records = case.records()
    _expect(state["processed_count"] == 1, "no-approval route was not processed")
    _expect(len(records) == 1, "no-approval route did not emit one record")
    _expect(
        records[0]["approval"]["required"] is False,
        "no-approval route changed approval posture",
    )
    _expect(
        records[0]["approval_artifact_sha256"]
        == request["approval_artifact_sha256"],
        "no-approval route lost the artifact identity",
    )


def main() -> int:
    pin = _common_pin()
    collection_root, installed_version = _installed_common()
    if installed_version != pin:
        raise RuntimeError(
            f"hybridops.common version mismatch: pinned={pin} installed={installed_version}"
        )

    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        _exact_approval(collection_root, root / "exact")
        _stale_then_corrected(collection_root, root / "retry")
        _posture_mutation(collection_root, root / "posture")
        _no_approval_route(collection_root, root / "no-approval")

    print(f"approval-binding acceptance: ok collection=hybridops.common version={pin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
