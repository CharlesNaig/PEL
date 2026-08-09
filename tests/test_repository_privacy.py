import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryPrivacyTests(unittest.TestCase):
    def test_tracked_text_contains_no_live_philippine_numbers(self):
        tracked = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).splitlines()
        findings = []
        for relative in tracked:
            path = ROOT / relative
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if re.search(r"\+63\d{10}\b", content):
                findings.append(relative)
        self.assertEqual([], findings, f"private phone numbers found in: {findings}")

    def test_contacts_are_loaded_from_an_untracked_deployment_file(self):
        config = (ROOT / "main" / "config.py").read_text(encoding="utf-8")
        self.assertIn("PEL_CONTACTS_FILE", config)
        self.assertNotRegex(config, r'"number"\s*:\s*"\+\d+')

    def test_startup_logs_do_not_emit_contact_numbers(self):
        main = (ROOT / "main" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("c['number']", main)


if __name__ == "__main__":
    unittest.main()
