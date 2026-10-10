#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROLE = Path(__file__).resolve().parents[1]

MEMORY_LEAN_KEYS = [
    "dns.cache.size",
    "database.maxDBdays",
    "database.DBinterval",
    "webserver.threads",
]


def defaults():
    text = (ROLE / "defaults/main.yml").read_text()
    privacy = re.search(
        r'key:\s*"misc\.privacylevel",\s*value:\s*"([^"]+)"', text
    )
    query_logging = re.search(
        r'key:\s*"dns\.queryLogging",\s*value:\s*"([^"]+)"', text
    )
    if not (privacy and query_logging):
        raise AssertionError("Could not read expected Pi-hole role defaults")
    return privacy.group(1), query_logging.group(1), text


class FullQueryLoggingValidation(unittest.TestCase):
    def test_privacy_level_is_zero(self):
        privacy, _, _ = defaults()
        self.assertEqual(privacy, "0")

    def test_query_logging_is_true(self):
        _, query_logging, _ = defaults()
        self.assertEqual(query_logging, "true")

    def test_memory_lean_profile_entries_remain(self):
        _, _, text = defaults()
        for key in MEMORY_LEAN_KEYS:
            self.assertRegex(
                text,
                r'key:\s*"' + re.escape(key) + r'",\s*value:\s*"[^"]+"',
            )

    def test_tasks_assert_critical_ftl_settings(self):
        tasks = (ROLE / "tasks/main.yml").read_text()
        self.assertIn("Assert critical Pi-hole FTL settings took effect", tasks)
        self.assertIn("dns.listeningMode", tasks)
        self.assertIn("misc.privacylevel", tasks)


if __name__ == "__main__":
    unittest.main()
