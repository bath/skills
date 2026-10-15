"""The report command: one HTML page, the same every run, filled from the table and a judgement file."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "skills", "show-and-improve-state-machine")
SCRIPT = os.path.join(SKILL, "scripts", "every_path.py")
DEPLOY = os.path.join(SKILL, "examples", "deploy.json")

JUDGEMENT = {
    "title": "Deploy check",
    "eyebrow": "first run",
    "lede": "The deploy modelled from pipeline.yml and deploy.sh.",
    "source": "Model from the pipeline at <main>; checks by the machine.",
    "seen": {
        "title": "The line you saw",
        "lines": ["build #12", "red: tests failed"],
        "state": "refused",
        "text": ["In the model this is refused. Nothing leaves it."],
    },
    "cards": [
        {
            "id": "F1",
            "title": "A refused build is a trap",
            "problem": "Nothing leads out of refused.",
            "options": [
                {"key": "a", "text": "Declare refused an end & draw it red.", "strength": "Strong"},
                {"key": "b", "text": "Add a retry with a bound.", "strength": "Worth exploring"},
                {"key": "c", "text": "Drop the state.", "strength": "Speculative"},
            ],
            "pick": "a, then b",
            "picked": ["a", "b"],
        }
    ],
    "trust": ["Each row names a file:line.", "The rollback path was not seen in practice."],
}


def run(args, judgement=None):
    files = []
    if judgement is not None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(judgement, handle)
        handle.close()
        files.append(handle.name)
        args = args + ["--judgement", handle.name]
    done = subprocess.run([sys.executable, "-I", SCRIPT] + args, capture_output=True, text=True)
    for path in files:
        os.unlink(path)
    return done.returncode, done.stdout, done.stderr


class ReportFromTheTable(unittest.TestCase):
    def test_the_page_carries_the_numbers_the_checks_the_diagram_and_the_waits(self):
        code, html, err = run(["report", DEPLOY])
        self.assertEqual(code, 0, err)
        self.assertTrue(html.startswith("<!doctype html>"), html[:40])
        self.assertIn("<title>deploy</title>", html)
        # summary numbers
        self.assertIn('<span class="eyebrow">States</span><b>8</b>', html)
        self.assertIn('<span class="eyebrow">Transitions</span><b>8</b>', html)
        self.assertIn('<span class="eyebrow">Ends</span><b>2</b>', html)
        self.assertIn('<span class="eyebrow">Checks failed</span><b>5 / 7</b>', html)
        self.assertIn('<span class="eyebrow">Waits with no end</span><b>2</b>', html)
        # one line per check, plain words
        self.assertIn('<span class="tag p">PASS</span><div><span class="n">reachable</span><p>Every state that is not an end is reachable from requested.</p>', html)
        self.assertIn('<span class="tag f">FAIL</span><div><span class="n">exit</span><p><span class="st t">refused</span> is not an end and has no way out.</p>', html)
        self.assertIn('<span class="n">ends-reachable</span><p><span class="st e">abandoned</span> is an end that can never happen.</p>', html)
        self.assertIn('<span class="n">waits-owned</span><p>2 states wait on someone. 2 have no timeout that leads to an end, and 1 has no owner who is told.</p>', html)
        self.assertIn('<span class="n">loops-bounded</span><p>1 loop region, with 5 states. Nothing counts the rounds.</p>', html)
        # the diagram, from the same table
        self.assertIn('<pre class="mermaid">\nstateDiagram-v2', html)
        self.assertIn("class refused trap", html)
        # the waits table
        self.assertIn("<tr><td><span class=\"st w\">building</span></td><td>ci</td><td class=\"no\">no</td><td class=\"no\">none</td></tr>", html)
        self.assertIn("<tr><td><span class=\"st w\">awaiting_approval</span></td><td>approver</td><td>approver</td><td class=\"no\">none</td></tr>", html)
        # the loop region
        self.assertIn("<h2>Loops nothing counts</h2>", html)
        self.assertIn("closing edges", html)
        # only one pinned Mermaid file leaves the page, and the browser checks its hash
        self.assertNotIn("tailwind", html)
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertIn('src="https://cdn.jsdelivr.net/npm/mermaid@11.17.2/dist/mermaid.min.js" integrity="sha384-', html)
        self.assertEqual(1, html.count("https://"), "a second outside URL in the page")

    def test_without_a_judgement_file_the_judged_sections_are_absent(self):
        code, html, err = run(["report", DEPLOY])
        self.assertNotIn("Ways to close each gap", html)
        self.assertNotIn('class="bubble"', html)
        self.assertIn("How far to trust this", html)  # the machine's own note stays
        self.assertIn("8 of 8 rows name a file:line", html)

    def test_out_writes_the_file_and_prints_its_path(self):
        out = os.path.join(tempfile.mkdtemp(), "deploy.html")
        code, stdout, err = run(["report", DEPLOY, "--out", out])
        self.assertEqual(code, 0, err)
        self.assertEqual(stdout.strip(), out)
        with open(out, encoding="utf-8") as handle:
            self.assertIn("<title>deploy</title>", handle.read())


class ReportFromTheJudgement(unittest.TestCase):
    def test_the_cards_the_seen_example_and_the_trust_notes_come_from_the_file(self):
        code, html, err = run(["report", DEPLOY], JUDGEMENT)
        self.assertEqual(code, 0, err)
        self.assertIn("<title>Deploy check</title>", html)
        self.assertIn('<span class="eyebrow">show-and-improve-state-machine · first run</span>', html)
        self.assertIn('<div class="bubble"><span class="t">build #12</span><span>red: tests failed</span></div>', html)
        self.assertIn('<span class="st t">refused</span>', html)
        self.assertIn('<span class="id">F1</span><h3>A refused build is a trap</h3>', html)
        self.assertIn('<li class="pick"><span class="k">a</span><span>Declare refused an end &amp; draw it red.</span><span class="badge s">Strong</span></li>', html)
        self.assertIn('<li class="pick"><span class="k">b</span><span>Add a retry with a bound.</span><span class="badge w">Worth exploring</span></li>', html)
        self.assertIn('<li><span class="k">c</span><span>Drop the state.</span><span class="badge x">Speculative</span></li>', html)
        self.assertIn('<p class="pickline">Pick: <b>a, then b</b></p>', html)
        self.assertIn("<li>Each row names a file:line.</li><li>The rollback path was not seen in practice.</li>", html)

    def test_what_the_reader_sees_in_each_wait_is_a_column_when_the_judgement_gives_it(self):
        seen = json.loads(json.dumps(JUDGEMENT))
        seen["waits"] = {"awaiting_approval": "Waiting for your approval"}
        code, html, err = run(["report", DEPLOY], seen)
        self.assertEqual(code, 0, err)
        self.assertIn("<thead><tr><th>State</th><th>What the reader sees</th><th>Waits on</th><th>Owner told</th><th>Timeout</th></tr></thead>", html)
        self.assertIn('<tr><td><span class="st w">awaiting_approval</span></td><td>Waiting for your approval</td><td>approver</td><td>approver</td>', html)
        # a wait the judgement says nothing about keeps the column, empty
        self.assertIn('<tr><td><span class="st w">building</span></td><td></td><td>ci</td>', html)

    def test_without_the_waits_field_the_column_is_absent(self):
        code, html, err = run(["report", DEPLOY], JUDGEMENT)
        self.assertNotIn("What the reader sees", html)
        self.assertIn("<thead><tr><th>State</th><th>Waits on</th><th>Owner told</th><th>Timeout</th></tr></thead>", html)

    def test_a_waits_field_that_is_not_a_map_of_strings_is_refused(self):
        bad = json.loads(json.dumps(JUDGEMENT))
        bad["waits"] = ["Refused"]
        code, html, err = run(["report", DEPLOY], bad)
        self.assertEqual(code, 2)
        self.assertIn("'waits' must be a map of state name to what the reader sees", err)

    def test_an_unknown_strength_is_refused(self):
        bad = json.loads(json.dumps(JUDGEMENT))
        bad["cards"][0]["options"][0]["strength"] = "Certain"
        code, html, err = run(["report", DEPLOY], bad)
        self.assertEqual(code, 2)
        self.assertIn("strength must be one of Strong, Worth exploring, Speculative", err)

    def test_judgement_text_is_escaped(self):
        hot = json.loads(json.dumps(JUDGEMENT))
        hot["trust"] = ["<script>alert(1)</script>"]
        code, html, err = run(["report", DEPLOY], hot)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_two_loop_regions_name_the_size_of_each(self):
        data = {
            "name": "refund", "initial": "paying", "ends": ["refunded"],
            "actors": {"system": "system"},
            "transitions": [
                {"from": "paying", "on": "fail", "to": "paying", "actor": "system"},
                {"from": "paying", "on": "cancel", "to": "refunding", "actor": "system"},
                {"from": "refunding", "on": "fail", "to": "refund_failed", "actor": "system"},
                {"from": "refund_failed", "on": "retry", "to": "refunding", "actor": "system"},
                {"from": "refunding", "on": "done", "to": "refunded", "actor": "system"},
            ],
        }
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(data, handle)
        handle.close()
        code, html, err = run(["report", handle.name])
        os.unlink(handle.name)
        self.assertEqual(code, 0, err)
        self.assertIn("<p>2 loop regions, with 2 states and 1 state. Nothing counts the rounds.</p>", html)
        self.assertIn('<div class="region"><div>1 state: ', html)
        self.assertIn('<div class="region"><div>2 states: ', html)


class DiagramOptions(unittest.TestCase):
    def shared(self):
        return {
            "name": "ticket", "initial": "new", "ends": ["done"],
            "actors": {"system": "system", "agent": "human"},
            "transitions": [
                {"from": "new", "on": "pick", "to": "a", "actor": "agent", "guard": "free"},
                {"from": "a", "on": "next", "to": "b", "actor": "agent"},
                {"from": "b", "on": "next", "to": "c", "actor": "agent"},
                {"from": "c", "on": "finish", "to": "done", "actor": "agent"},
                {"from": "a", "on": "stale_14d", "to": "expired", "actor": "system", "timeout": "14d"},
                {"from": "b", "on": "stale_14d", "to": "expired", "actor": "system", "timeout": "14d"},
                {"from": "c", "on": "stale_14d", "to": "expired", "actor": "system", "timeout": "14d"},
            ],
        }

    def write(self, data):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(data, handle)
        handle.close()
        return handle.name

    def test_short_labels_show_the_event_only(self):
        path = self.write(self.shared())
        code, out, err = run(["diagram", path, "--short-labels"])
        os.unlink(path)
        self.assertIn("new --> a : pick\n", out)
        self.assertNotIn("/ agent", out)

    def test_a_timeout_shared_by_three_or_more_states_is_drawn_once(self):
        path = self.write(self.shared())
        code, out, err = run(["diagram", path, "--shared-timeouts"])
        os.unlink(path)
        self.assertEqual(out.count("--> expired"), 1, out)
        self.assertIn('state "expired (from a, b, c, after 14d)" as expired', out)

    def test_a_timeout_shared_by_many_states_names_their_count_not_their_names(self):
        data = self.shared()
        for extra in ("d", "e"):
            data["transitions"].append({"from": "c", "on": "go_" + extra, "to": extra, "actor": "agent"})
            data["transitions"].append({"from": extra, "on": "finish", "to": "done", "actor": "agent"})
            data["transitions"].append({"from": extra, "on": "stale_14d", "to": "expired", "actor": "system", "timeout": "14d"})
        path = self.write(data)
        code, out, err = run(["diagram", path, "--shared-timeouts"])
        os.unlink(path)
        self.assertIn('state "expired (from 5 states, after 14d)" as expired', out)

    def test_a_timeout_shared_by_two_states_is_drawn_twice(self):
        data = self.shared()
        data["transitions"].pop()  # c no longer expires
        path = self.write(data)
        code, out, err = run(["diagram", path, "--shared-timeouts"])
        os.unlink(path)
        self.assertEqual(out.count("--> expired"), 2, out)



class ShippedExamplePage(unittest.TestCase):
    """The page the README shows is the one the shipped example builds."""

    def test_the_deploy_example_builds_the_page_in_the_readme(self):
        judgement = os.path.join(SKILL, "examples", "deploy.judgement.json")
        proc = subprocess.run([sys.executable, "-I", SCRIPT, "report", DEPLOY, "--judgement", judgement],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        html = proc.stdout
        self.assertIn("Deploy pipeline check", html)
        self.assertIn("The message you saw", html)
        for card in ("F1", "F2", "F3", "F4", "F5"):
            self.assertIn(card, html)
        self.assertIn("What the reader sees", html)


if __name__ == "__main__":
    unittest.main()
