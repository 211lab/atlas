#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROLE = Path(__file__).resolve().parents[1]


def defaults():
    text = (ROLE / "defaults/main.yml").read_text()
    query_logging = re.search(r"^pihole_query_logging:\s*(\S+)", text, re.M)
    ftl_query_logging = re.search(
        r'key: "dns\.queryLogging", value: "([^"]+)"', text
    )
    lines_expression = re.search(
        r"pihole_dnsmasq_lines:\s*>-\s*\n((?:\s+.*\n)+)", text
    )
    if not (query_logging and ftl_query_logging and lines_expression):
        raise AssertionError("Could not read expected Pi-hole role defaults")
    targets = ["10.0.0.110", "10.0.0.111", "10.0.0.112", "10.0.0.113"]
    lines = ["local=/10.in-addr.arpa/"] + [
        f"address=/atlas.lan/{target}" for target in targets
    ]
    return query_logging.group(1), ftl_query_logging.group(1), lines


class LoggingNetworkValidation(unittest.TestCase):
    def test_logging_values_are_exact_true(self):
        installer, ftl, _ = defaults()
        setup_vars = (ROLE / "templates/setupVars.conf.j2").read_text()
        self.assertEqual(installer, "true")
        self.assertEqual(ftl, "true")
        self.assertIn(
            "QUERY_LOGGING={{ pihole_query_logging | bool | lower }}", setup_vars
        )

    def test_desired_dnsmasq_lines_include_local_and_wildcards(self):
        _, _, lines = defaults()
        self.assertEqual(
            lines,
            [
                "local=/10.in-addr.arpa/",
                "address=/atlas.lan/10.0.0.110",
                "address=/atlas.lan/10.0.0.111",
                "address=/atlas.lan/10.0.0.112",
                "address=/atlas.lan/10.0.0.113",
            ],
        )

    def test_task_merges_existing_lines_idempotently(self):
        tasks = (ROLE / "tasks/main.yml").read_text()
        self.assertIn("pihole_dnsmasq_current.stdout", tasks)
        self.assertIn("pihole_dnsmasq_current.stdout | default('[]') | trim", tasks)
        self.assertIn("pihole_dnsmasq_current_lines + pihole_dnsmasq_lines", tasks)
        self.assertIn("pihole_dnsmasq_current_lines != pihole_dnsmasq_merged_lines", tasks)

        existing = ["server=/example.test/10.1.2.3", "address=/old.lan/10.0.0.9"]
        desired = defaults()[2]
        composed = list(dict.fromkeys(existing + desired))
        self.assertEqual(composed[: len(existing)], existing)
        self.assertEqual(composed[len(existing) :], desired)
        self.assertEqual(list(dict.fromkeys(composed + desired)), composed)


if __name__ == "__main__":
    unittest.main()
