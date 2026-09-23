"""Tests for offline module catalog contract checks."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_module_catalog", REPO_ROOT / "tools" / "ci" / "check-module-catalog.py"
)
check_module_catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_module_catalog)
check_catalog = check_module_catalog.check_catalog


def write_module(repo: Path, *, module_ref: str, spec_text: str) -> Path:
    module_dir = repo / "modules" / module_ref
    module_dir.mkdir(parents=True)
    (module_dir / "README.md").write_text("# sample\n", encoding="utf-8")
    examples = module_dir / "examples"
    examples.mkdir()
    (examples / "inputs.min.yml").write_text("name: sample\n", encoding="utf-8")
    (module_dir / "spec.yml").write_text(spec_text, encoding="utf-8")
    return module_dir


def valid_spec(module_ref: str) -> str:
    payload = {
        "kind": "ModuleSpec",
        "module_ref": module_ref,
        "execution": {
            "driver": "iac/terragrunt",
            "profile": "example@v1",
            "pack_ref": {"id": "example/pack@v1"},
        },
    }
    return yaml.dump(payload)


class ModuleCatalogContractTests(unittest.TestCase):
    def test_valid_module_contract_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_module(repo, module_ref="platform/example", spec_text=valid_spec("platform/example"))

            failures, count = check_catalog(repo)

            self.assertEqual(failures, [])
            self.assertEqual(count, 1)

    def test_module_ref_must_match_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_module(repo, module_ref="platform/example", spec_text=valid_spec("platform/other"))

            failures, count = check_catalog(repo)

            self.assertEqual(count, 1)
            self.assertTrue(
                any(
                    "modules/platform/example/spec.yml: module_ref:" in failure
                    and "platform/example" in failure
                    and "platform/other" in failure
                    for failure in failures
                )
            )

    def test_malformed_yaml_names_the_spec_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_module(repo, module_ref="platform/example", spec_text="invalid: yaml: [\n")

            failures, count = check_catalog(repo)

            self.assertEqual(count, 1)
            self.assertTrue(
                any(
                    failure.startswith("modules/platform/example/spec.yml: spec: malformed YAML:")
                    for failure in failures
                )
            )

    def test_missing_execution_field_names_the_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            payload = yaml.safe_load(valid_spec("platform/example"))
            del payload["execution"]["driver"]
            write_module(repo, module_ref="platform/example", spec_text=yaml.dump(payload))

            failures, count = check_catalog(repo)

            self.assertEqual(count, 1)
            self.assertIn(
                "modules/platform/example/spec.yml: execution.driver: is required",
                failures,
            )


if __name__ == "__main__":
    unittest.main()
