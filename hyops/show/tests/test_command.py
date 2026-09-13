from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from hyops.cli import build_parser
from hyops.runtime.exitcodes import OK, OPERATOR_ERROR
from hyops.show.command import run_show_env_command, run_show_env_list


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class ShowEnvironmentListTests(unittest.TestCase):
    def test_parser_routes_environment_list(self) -> None:
        parsed = build_parser().parse_args(["show", "env", "list", "--json"])

        self.assertEqual(parsed.show_cmd, "env")
        self.assertEqual(parsed.action, "list")
        self.assertIs(parsed._handler, run_show_env_command)

    def test_json_lists_state_backed_environment_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            envs_root = Path(tmp) / "envs"
            alpha = envs_root / "alpha"
            beta = envs_root / "beta"
            empty = envs_root / "empty"
            empty.mkdir(parents=True)

            _write_json(
                alpha / "meta" / "gcp.ready.json",
                {"target": "gcp", "status": "ready", "run_id": "init-one"},
            )
            (alpha / "config" / "blueprints").mkdir(parents=True)
            (alpha / "config" / "blueprints" / "eve-ng.yml").write_text(
                'blueprint_ref: "gcp/eve-ng@v1"\n',
                encoding="utf-8",
            )
            _write_json(
                alpha / "state" / "modules" / "host" / "instances" / "host.json",
                {
                    "module_ref": "platform/gcp/platform-vm",
                    "state_instance": "host",
                    "status": "ok",
                    "updated_at": "2026-09-13T10:00:00Z",
                },
            )

            _write_json(
                beta / "meta" / "proxmox.ready.json",
                {"target": "proxmox", "status": "ready", "run_id": "init-two"},
            )
            _write_json(
                beta / "state" / "modules" / "host" / "instances" / "host.json",
                {
                    "module_ref": "platform/onprem/platform-vm",
                    "state_instance": "host",
                    "status": "destroyed",
                    "updated_at": "2026-09-13T11:00:00Z",
                },
            )

            stdout = io.StringIO()
            ns = SimpleNamespace(action="list", root=str(envs_root), env=None, json=True)
            with redirect_stdout(stdout):
                result = run_show_env_list(ns)

            self.assertEqual(result, OK)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["count"], 3)
            self.assertEqual(
                [item["name"] for item in payload["environments"]],
                ["alpha", "beta", "empty"],
            )
            alpha_summary = payload["environments"][0]
            self.assertEqual(alpha_summary["readiness"], "ready")
            self.assertEqual(alpha_summary["state"], "active")
            self.assertEqual(alpha_summary["targets"], ["gcp"])
            self.assertEqual(alpha_summary["blueprints"], ["gcp/eve-ng@v1"])
            self.assertTrue(alpha_summary["last_activity"].endswith("Z"))

            beta_summary = payload["environments"][1]
            self.assertEqual(beta_summary["state"], "destroyed")
            self.assertEqual(beta_summary["targets"], ["proxmox"])

            empty_summary = payload["environments"][2]
            self.assertEqual(empty_summary["readiness"], "uninitialized")
            self.assertEqual(empty_summary["state"], "empty")

    def test_text_output_is_a_compact_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            envs_root = Path(tmp) / "envs"
            environment = envs_root / "demo-lab"
            _write_json(
                environment / "meta" / "gcp.ready.json",
                {"target": "gcp", "status": "ready"},
            )

            stdout = io.StringIO()
            ns = SimpleNamespace(action="list", root=str(envs_root), env=None, json=False)
            with redirect_stdout(stdout):
                result = run_show_env_list(ns)

            self.assertEqual(result, OK)
            output = stdout.getvalue()
            self.assertIn("ENVIRONMENT", output)
            self.assertIn("READINESS", output)
            self.assertIn("demo-lab", output)
            self.assertIn("gcp", output)

    def test_invalid_records_do_not_abort_listing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            envs_root = Path(tmp) / "envs"
            environment = envs_root / "broken"
            marker = environment / "meta" / "gcp.ready.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("not-json", encoding="utf-8")
            state = environment / "state" / "modules" / "host" / "latest.json"
            state.parent.mkdir(parents=True)
            state.write_text("not-json", encoding="utf-8")
            blueprint = environment / "config" / "blueprints" / "broken.yml"
            blueprint.parent.mkdir(parents=True)
            blueprint.write_text("kind: BlueprintSpec\n", encoding="utf-8")

            stdout = io.StringIO()
            ns = SimpleNamespace(action="list", root=str(envs_root), env=None, json=True)
            with redirect_stdout(stdout):
                result = run_show_env_list(ns)

            self.assertEqual(result, OK)
            summary = json.loads(stdout.getvalue())["environments"][0]
            self.assertEqual(summary["readiness"], "invalid")
            self.assertEqual(summary["state"], "invalid")
            self.assertEqual(summary["invalid_blueprint_files"], ["broken.yml"])
            self.assertEqual(len(summary["invalid_state_files"]), 1)

    def test_missing_environments_root_is_an_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "missing"
            stdout = io.StringIO()
            ns = SimpleNamespace(action="list", root=str(root), env=None, json=False)
            with redirect_stdout(stdout):
                result = run_show_env_list(ns)

            self.assertEqual(result, OK)
            self.assertEqual(stdout.getvalue(), "environments: none\n")

    def test_list_rejects_single_environment_selector(self) -> None:
        stderr = io.StringIO()
        ns = SimpleNamespace(action="list", root=None, env="demo-lab", json=False)
        with redirect_stderr(stderr):
            result = run_show_env_list(ns)

        self.assertEqual(result, OPERATOR_ERROR)
        self.assertIn("does not accept --env", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
