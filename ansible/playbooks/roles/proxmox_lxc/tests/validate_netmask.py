#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]

VARS_FILE = REPO_ROOT / "ansible/vars/memex-pihole-lxc.yml"
DEFAULTS_FILE = REPO_ROOT / "ansible/playbooks/roles/proxmox_lxc/defaults/main.yml"


def read(path):
    return path.read_text()


class NetmaskValidation(unittest.TestCase):
    def test_vars_file_uses_slash_8(self):
        text = read(VARS_FILE)
        self.assertTrue(re.search(r"^ip_address:\s*10\.0\.0\.10/8[ \t]*$", text, re.M))
        self.assertNotRegex(text, r"10\.0\.0\.10/24")

    def test_role_defaults_use_slash_8(self):
        text = read(DEFAULTS_FILE)
        self.assertTrue(re.search(r"^ip_address:\s*10\.0\.0\.10/8[ \t]*$", text, re.M))
        self.assertNotRegex(text, r"10\.0\.0\.10/24")

    def test_gateway_unchanged_in_vars_file(self):
        text = read(VARS_FILE)
        self.assertTrue(re.search(r"^gateway:\s*10\.0\.0\.1[ \t]*$", text, re.M))

    def test_gateway_unchanged_in_role_defaults(self):
        text = read(DEFAULTS_FILE)
        self.assertTrue(re.search(r"^gateway:\s*10\.0\.0\.1[ \t]*$", text, re.M))


if __name__ == "__main__":
    unittest.main()
