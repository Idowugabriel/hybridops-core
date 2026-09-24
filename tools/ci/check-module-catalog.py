#!/usr/bin/env python3
"""Check that shipped module contracts load and include their reviewable companion files."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def _check_spec_contract(spec_path: Path, repo_root: Path, modules_root: Path) -> list[str]:
    rel_path = spec_path.relative_to(repo_root)
    expected_ref = spec_path.parent.relative_to(modules_root).as_posix()

    try:
        payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{rel_path}: spec: malformed YAML: {exc}"]

    if not isinstance(payload, dict):
        return [f"{rel_path}: spec: must be a YAML mapping"]

    failures: list[str] = []
    if payload.get("kind") != "ModuleSpec":
        failures.append(
            f"{rel_path}: kind: expected 'ModuleSpec', found {payload.get('kind')!r}"
        )

    found_ref = str(payload.get("module_ref") or "").strip()
    if found_ref != expected_ref:
        failures.append(
            f"{rel_path}: module_ref: expected {expected_ref!r}, found {found_ref!r}"
        )

    execution = payload.get("execution")
    if not isinstance(execution, dict):
        failures.append(f"{rel_path}: execution: must be a mapping")
        return failures

    if not str(execution.get("driver") or "").strip():
        failures.append(f"{rel_path}: execution.driver: is required")
    if not str(execution.get("profile") or "").strip():
        failures.append(f"{rel_path}: execution.profile: is required")

    pack_ref = execution.get("pack_ref")
    if not isinstance(pack_ref, dict):
        failures.append(f"{rel_path}: execution.pack_ref: must be a mapping")
    elif not str(pack_ref.get("id") or "").strip():
        failures.append(f"{rel_path}: execution.pack_ref.id: is required")

    return failures


def check_catalog(repo_root: Path) -> tuple[list[str], int]:
    modules_root = repo_root / "modules"
    failures: list[str] = []
    spec_paths = sorted(modules_root.rglob("spec.yml"))

    if not spec_paths:
        return ["modules: no spec.yml files found"], 0

    for spec_path in spec_paths:
        module_dir = spec_path.parent
        module_path = module_dir.relative_to(repo_root)

        failures.extend(_check_spec_contract(spec_path, repo_root, modules_root))

        if not (module_dir / "README.md").is_file():
            failures.append(f"{module_path}: missing README.md")

        examples_dir = module_dir / "examples"
        if not examples_dir.is_dir():
            failures.append(f"{module_path}: missing examples/")
        elif not any(path.is_file() for path in examples_dir.rglob("*")):
            failures.append(f"{module_path}: examples/ contains no files")

    return failures, len(spec_paths)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    failures, module_count = check_catalog(repo_root)
    if failures:
        for failure in failures:
            print(f"ERR: {failure}", file=sys.stderr)
        return 1

    print(f"module catalog: ok ({module_count} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
