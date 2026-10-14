"""Behaviour tests for the checker: a small table with one known defect per test.

Each table is written the way an agent would write it after reading a codebase.
The assertions read the checker's report, never its internals.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "every-path-ends", "scripts", "every_path.py")

ACTORS = {"system": "system", "customer": "human", "carrier": "external", "agent": "human"}


def table(transitions, initial="placed", ends=("delivered",), states=None):
    return {
        "name": "order",
        "initial": initial,
        "ends": list(ends),
        "actors": ACTORS,
        "states": states or {},
        "transitions": [
            {"from": f, "on": on, "to": t, "actor": actor, **extra}
            for (f, on, t, actor, *rest) in transitions
            for extra in [rest[0] if rest else {}]
        ],
    }


def run(subcommand, data):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(data, handle)
        path = handle.name
    try:
        done = subprocess.run(
            [sys.executable, "-I", SCRIPT, subcommand, path], capture_output=True, text=True
        )
    finally:
        os.unlink(path)
    return done.returncode, done.stdout + done.stderr


def check(data):
    return run("check", data)


class ExitCheck(unittest.TestCase):
    def test_a_state_with_no_exit_is_reported_with_the_path_to_it(self):
        code, out = check(table([
            ("placed", "pay", "paid", "customer"),
            ("paid", "ship", "shipped", "system"),
            ("shipped", "deliver", "delivered", "carrier"),
            ("placed", "cancel", "cancelled", "customer"),
        ]))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL exit", out)
        self.assertIn("cancelled", out)
        self.assertIn("placed --cancel--> cancelled", out)

    def test_a_table_where_every_state_exits_or_ends_passes(self):
        code, out = check(table([
            ("placed", "pay", "paid", "customer"),
            ("paid", "ship", "shipped", "system"),
            ("shipped", "deliver", "delivered", "carrier"),
        ]))
        self.assertEqual(code, 0, out)
        self.assertIn("PASS exit", out)


if __name__ == "__main__":
    unittest.main()
