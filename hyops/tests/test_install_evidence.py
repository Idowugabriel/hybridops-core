"""Tests for installer evidence recording."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tools.install import install_evidence


class InstallEvidenceTests(unittest.TestCase):
    def test_interrupt_exits_without_traceback(self) -> None:
        with patch.object(install_evidence, "main", side_effect=KeyboardInterrupt):
            self.assertEqual(install_evidence.entrypoint(), 130)


if __name__ == "__main__":
    unittest.main()
