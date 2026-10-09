#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROLE = Path(__file__).resolve().parents[1]

MEMORY_LEAN_KEYS = [
    "dns.cache.size",
    "database.maxDBdays",
    "database.DBinterval",
    "dns.queryLogging",
    "misc.privacylevel",
    "webserver.threads",
]


def defaults():
    text = (ROLE / "defaults/main.yml").read_text()
    listening_mode = re.search(r"^pihole_listening_mode:\s*(\S+)", text, re.M)
    ftl_listening_mode = re.search(
        r'key:\s*"dns\.listeningMode",\s*value:\s*"([^"]+)"', text
    )
    if not (listening_mode and ftl_listening_mode):
        raise AssertionError("Could not read expected Pi-hole role defaults")
    return listening_mode.group(1), ftl_listening_mode.group(1), text


class CrossSubnetClientsValidation(unittest.TestCase):
    def test_listening_mode_default_is_all(self):
        installer, _, _ = defaults()
        self.assertEqual(installer, "all")

    def test_ftl_listening_mode_is_uppercased(self):
        _, ftl, _ = defaults()
        self.assertEqual(ftl, "{{ pihole_listening_mode | upper }}")

    def test_setup_vars_binds_listening_mode(self):
        setup_vars = (ROLE / "templates/setupVars.conf.j2").read_text()
        self.assertIn("DNSMASQ_LISTENING={{ pihole_listening_mode }}", setup_vars)
        self.assertNotIn("DNSMASQ_LISTENING=local", setup_vars)

    def test_memory_lean_profile_entries_remain(self):
        _, _, text = defaults()
        for key in MEMORY_LEAN_KEYS:
            self.assertRegex(
                text,
                r'key:\s*"' + re.escape(key) + r'",\s*value:\s*"[^"]+"',
            )


if __name__ == "__main__":
    unittest.main()
