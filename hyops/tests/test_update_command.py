"""Tests for update installation confirmation through the public CLI."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from hyops.cli import main
from hyops.update.checker import UpdateStatus


class UpdateInstallConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        # Keep CLI confirmation tests independent of the shared plugin registries.
        self.enterContext(patch("hyops.cli._register_drivers"))
        self.enterContext(patch("hyops.cli._register_validators"))
        self.status = UpdateStatus(
            state="update_available",
            installed="0.1.3",
            latest="0.1.4",
            release_url="https://github.com/hybridops-tech/hybridops-core/releases/tag/v0.1.4",
        )
        self.check = self.enterContext(
            patch("hyops.update.command.check_for_update", return_value=self.status)
        )
        self.install = self.enterContext(
            patch("hyops.update.command.install_release", return_value=0)
        )
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(redirect_stdout(self.stdout))
        self.enterContext(redirect_stderr(self.stderr))

    def _run(self, stdin: str, *args: str) -> int:
        with patch("sys.stdin", io.StringIO(stdin)):
            return main(["update", "install", *args])

    def test_eof_reports_error_without_starting_installer(self) -> None:
        for state in ("update_available", "unsupported"):
            with self.subTest(state=state):
                self.stderr.seek(0)
                self.stderr.truncate()
                self.check.return_value = UpdateStatus(
                    state=state,
                    installed=self.status.installed,
                    latest=self.status.latest,
                    release_url=self.status.release_url,
                )
                self.assertEqual(self._run(""), 2)
                self.install.assert_not_called()
                self.assertIn("ERR:", self.stderr.getvalue())
                self.assertIn("confirmation", self.stderr.getvalue())
                self.assertIn("--yes", self.stderr.getvalue())

    def test_declined_or_blank_confirmation_cancels_installation(self) -> None:
        for answer in ("n\n", "\n"):
            with self.subTest(answer=answer):
                self.assertEqual(self._run(answer), 2)
                self.install.assert_not_called()
        self.assertIn("Update cancelled.", self.stdout.getvalue())
        self.assertEqual(self.stderr.getvalue(), "")

    def test_explicit_confirmation_starts_installer(self) -> None:
        for answer in ("y\n", " YES \n"):
            with self.subTest(answer=answer):
                self.install.reset_mock()
                self.assertEqual(self._run(answer), 0)
                self.install.assert_called_once_with(self.status.latest, self.status.release_url)
        self.assertEqual(self.stderr.getvalue(), "")

    def test_yes_flag_allows_installation_with_empty_stdin(self) -> None:
        self.assertEqual(self._run("", "--yes"), 0)
        self.install.assert_called_once_with(self.status.latest, self.status.release_url)
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertEqual(self.stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
