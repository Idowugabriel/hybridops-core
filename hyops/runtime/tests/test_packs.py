"""Pack root resolution contracts."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hyops.runtime.packs import (
    PackInvalidError,
    PackNotFoundError,
    resolve_pack_stack,
    resolve_packs_root,
)


class PackRootResolutionTests(unittest.TestCase):
    def test_explicit_root_keeps_highest_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = root / "explicit"
            environment = root / "environment"
            core = root / "core"
            for path in (explicit, environment, core / "packs"):
                path.mkdir(parents=True)

            with patch.dict(
                os.environ,
                {
                    "HYOPS_PACKS_ROOT": str(environment),
                    "HYOPS_CORE_ROOT": str(core),
                },
            ):
                self.assertEqual(resolve_packs_root(str(explicit)), explicit.resolve())

    def test_installed_venv_finds_sibling_app_packs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = Path(tmp) / "core"
            venv = install_root / "venv"
            packs = install_root / "app" / "packs"
            venv.mkdir(parents=True)
            packs.mkdir(parents=True)

            with (
                patch.dict(
                    os.environ,
                    {"HYOPS_PACKS_ROOT": "", "HYOPS_CORE_ROOT": ""},
                ),
                patch("hyops.runtime.packs.sys.prefix", str(venv)),
                patch("hyops.runtime.packs._find_packs_root_from_here", return_value=None),
            ):
                self.assertEqual(resolve_packs_root(), packs.resolve())

    def test_invalid_explicit_root_does_not_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"

            with self.assertRaisesRegex(PackNotFoundError, "packs root not found"):
                resolve_packs_root(str(missing))


class PackStackTraversalTests(unittest.TestCase):
    def test_rejects_dotdot_pack_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config" / "ansible" / "linux" / "stack").mkdir(parents=True)

            with self.assertRaisesRegex(PackInvalidError, "pack_id"):
                resolve_pack_stack(
                    driver_ref="config/ansible",
                    pack_id="../linux",
                    packs_root=str(root),
                )

    def test_rejects_dot_segment_in_driver_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config" / "ansible" / "linux" / "stack").mkdir(parents=True)

            with self.assertRaisesRegex(PackInvalidError, "driver_ref"):
                resolve_pack_stack(
                    driver_ref="config/./ansible",
                    pack_id="linux",
                    packs_root=str(root),
                )

    def test_keeps_valid_nested_pack_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config" / "ansible" / "linux" / "nested" / "stack").mkdir(parents=True)

            resolved = resolve_pack_stack(
                driver_ref="config/ansible",
                pack_id="linux/nested",
                packs_root=str(root),
            )
            self.assertEqual(resolved.pack_id, "linux/nested")
            self.assertEqual(resolved.driver_ref, "config/ansible")


if __name__ == "__main__":
    unittest.main()
