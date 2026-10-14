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

ACTORS = {"system": "system", "customer": "external", "carrier": "external", "agent": "human"}


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
        self.assertIn("PASS exit", out)


class TrapCheck(unittest.TestCase):
    """A refused PR that can only be refused again, and never reaches an end."""

    def test_a_region_that_can_never_reach_an_end_is_a_trap(self):
        code, out = check(table([
            ("filed", "start", "in_review", "agent"),
            ("in_review", "approve", "merged", "system"),
            ("in_review", "refuse", "refused", "system"),
            ("refused", "re_review", "refused_again", "system"),
            ("refused_again", "refuse", "refused", "system"),
        ], initial="filed", ends=("merged",)))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL can-end", out)
        self.assertIn("refused", out)
        self.assertIn("(start) filed --start--> in_review ; in_review --refuse--> refused", out)
        # Both states exit, so the exit check is silent; the trap check is what sees this.
        self.assertIn("PASS exit", out)

    def test_a_retry_edge_back_into_the_flow_clears_the_trap(self):
        code, out = check(table([
            ("filed", "start", "in_review", "agent"),
            ("in_review", "approve", "merged", "system"),
            ("in_review", "refuse", "refused", "system"),
            ("refused", "redo", "in_review", "agent"),
        ], initial="filed", ends=("merged",)))
        self.assertIn("PASS can-end", out)


class ReachabilityChecks(unittest.TestCase):
    def test_a_state_nothing_leads_to_is_an_orphan(self):
        code, out = check(table([
            ("placed", "pay", "paid", "customer"),
            ("paid", "deliver", "delivered", "carrier"),
            ("on_hold", "release", "paid", "system"),
        ]))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL reachable", out)
        self.assertIn("on_hold", out)

    def test_an_end_nothing_leads_to_is_reported(self):
        code, out = check(table([
            ("placed", "pay", "paid", "customer"),
            ("paid", "deliver", "delivered", "carrier"),
        ], ends=("delivered", "refunded")))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL ends-reachable", out)
        self.assertIn("refunded", out)

    def test_an_end_state_with_a_way_out_is_not_an_end(self):
        code, out = check(table([
            ("placed", "pay", "paid", "customer"),
            ("paid", "deliver", "delivered", "carrier"),
            ("delivered", "reopen", "placed", "customer"),
        ]))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL ends-closed", out)
        self.assertIn("delivered --reopen--> placed", out)


class WaitCheck(unittest.TestCase):
    """A support ticket that waits on the customer: who ends the wait, and by when?"""

    FLOW = [
        ("new", "auto_assign", "working", "system"),
        ("working", "ask_customer", "waiting_customer", "agent", {"bound": "questions < 3"}),
        ("waiting_customer", "customer_replies", "working", "customer"),
        ("working", "resolve", "resolved", "agent"),
    ]
    WORKING_TIMEOUT = ("working", "stale_30d", "resolved", "system", {"timeout": "30d"})
    CUSTOMER_TIMEOUT = ("waiting_customer", "no_reply_7d", "resolved", "system", {"timeout": "7d"})

    def test_a_wait_on_an_outside_party_with_no_owner_and_no_timeout_is_reported(self):
        code, out = check(table(self.FLOW + [self.WORKING_TIMEOUT], initial="new", ends=("resolved",)))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL waits-owned", out)
        self.assertIn("waiting_customer waits on customer (external) and has no owner and no timeout", out)
        self.assertIn("(start) new --auto_assign--> working ; working --ask_customer--> waiting_customer", out)

    def test_a_wait_on_a_person_inside_the_process_has_that_person_as_owner(self):
        code, out = check(table(self.FLOW, initial="new", ends=("resolved",),
                                states={"waiting_customer": {"owner": "support lead"}}))
        self.assertEqual(code, 1, out)
        self.assertIn("working waits on agent (human) and has no timeout", out)
        self.assertNotIn("no owner", out)

    def test_a_wait_with_an_owner_and_a_timeout_edge_passes(self):
        flow = self.FLOW + [self.WORKING_TIMEOUT, self.CUSTOMER_TIMEOUT]
        code, out = check(table(flow, initial="new", ends=("resolved",),
                                states={"waiting_customer": {"owner": "support lead"}}))
        self.assertEqual(code, 0, out)
        self.assertIn("PASS waits-owned", out)

    def test_an_open_ended_wait_with_a_reason_is_listed_and_does_not_fail(self):
        flow = self.FLOW + [self.CUSTOMER_TIMEOUT]
        code, out = check(table(flow, initial="new", ends=("resolved",), states={
            "waiting_customer": {"owner": "support lead"},
            "working": {"open_ended": "the agent's queue is reviewed every morning"},
        }))
        self.assertEqual(code, 0, out)
        self.assertIn("PASS waits-owned", out)
        self.assertIn("open-ended: working", out)
        self.assertIn("reviewed every morning", out)

    def test_a_state_the_system_moves_on_its_own_is_not_a_wait(self):
        flow = [
            ("new", "auto_assign", "working", "system"),
            ("working", "auto_close", "resolved", "system"),
            ("working", "resolve", "resolved", "agent"),
        ]
        code, out = check(table(flow, initial="new", ends=("resolved",)))
        self.assertEqual(code, 0, out)


class LoopCheck(unittest.TestCase):
    """A deploy that is refused and redone for ever unless something counts the attempts."""

    FLOW = [
        ("filed", "start", "in_review", "agent"),
        ("in_review", "approve", "merged", "system"),
        ("in_review", "refuse", "refused", "system"),
    ]

    def test_a_loop_that_avoids_every_end_and_has_no_bound_is_reported(self):
        flow = self.FLOW + [("refused", "redo", "in_review", "agent")]
        code, out = check(table(flow, initial="filed", ends=("merged",)))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL loops-bounded", out)
        self.assertIn("in_review --refuse--> refused ; refused --redo--> in_review", out)
        self.assertIn("PASS can-end", out)

    def test_a_loop_with_a_bounded_edge_passes(self):
        flow = self.FLOW + [("refused", "redo", "in_review", "agent", {"bound": "attempts < 3"}),
                            ("refused", "give_up", "abandoned", "system")]
        code, out = check(table(flow, initial="filed", ends=("merged", "abandoned")))
        self.assertIn("PASS loops-bounded", out)

    def test_a_self_loop_with_no_bound_is_reported(self):
        flow = self.FLOW + [("refused", "retry", "refused", "system"), ("refused", "give_up", "abandoned", "system")]
        code, out = check(table(flow, initial="filed", ends=("merged", "abandoned")))
        self.assertEqual(code, 1, out)
        self.assertIn("refused --retry--> refused", out)


class Diagram(unittest.TestCase):
    FLOW = [
        ("placed", "pay", "paid", "customer"),
        ("placed", "unpaid_24h", "cancelled", "system", {"timeout": "24h"}),
        ("paid", "ship", "shipped", "system"),
        ("shipped", "deliver", "delivered", "carrier", {"evidence": "src/orders.ts:42"}),
        ("shipped", "lose", "lost", "carrier"),
    ]

    def test_the_diagram_is_mermaid_drawn_from_the_same_table(self):
        code, out = run("diagram", table(self.FLOW, ends=("delivered", "cancelled")))
        self.assertEqual(code, 0, out)
        self.assertIn("stateDiagram-v2", out)
        self.assertIn("[*] --> placed", out)
        self.assertIn("delivered --> [*]", out)
        self.assertIn("placed --> paid : pay / customer", out)
        self.assertIn("placed --> cancelled : unpaid_24h / system, after 24h", out)

    def test_failing_states_are_marked_in_the_diagram(self):
        code, out = run("diagram", table(self.FLOW, ends=("delivered", "cancelled")))
        self.assertIn("class lost trap", out)       # no exit, no end
        self.assertIn("class shipped wait", out)    # waits on the carrier with no owner or timeout
        self.assertNotIn("class paid", out)

    def test_a_state_name_with_a_space_still_renders(self):
        flow = [("new", "start", "in review", "agent"), ("in review", "ok", "done", "system")]
        code, out = run("diagram", table(flow, initial="new", ends=("done",)))
        self.assertEqual(code, 0, out)
        self.assertIn('state "in review" as in_review', out)
        self.assertIn("new --> in_review : start / agent", out)


class MarkdownTable(unittest.TestCase):
    def test_the_table_lists_each_transition_with_its_evidence(self):
        code, out = run("table", table(Diagram.FLOW, ends=("delivered", "cancelled")))
        self.assertEqual(code, 0, out)
        self.assertIn("| From | Event | To | Actor | Guard | Timeout | Bound | Evidence |", out)
        self.assertIn("| shipped | deliver | delivered | carrier |  |  |  | src/orders.ts:42 |", out)
        self.assertIn("| placed | unpaid_24h | cancelled | system |  | 24h |  |  |", out)


class JsonResult(unittest.TestCase):
    def test_check_can_print_its_findings_as_json(self):
        data = table(Diagram.FLOW, ends=("delivered", "cancelled"))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(data, handle)
        done = subprocess.run([sys.executable, "-I", SCRIPT, "check", handle.name, "--json"], capture_output=True, text=True)
        os.unlink(handle.name)
        self.assertEqual(done.returncode, 1, done.stderr)
        result = json.loads(done.stdout)
        by_name = {r["check"]: r for r in result["results"]}
        self.assertFalse(by_name["exit"]["passed"])
        finding = by_name["exit"]["findings"][0]
        self.assertEqual(finding["state"], "lost")
        self.assertEqual([e["on"] for e in finding["path"]], ["pay", "ship", "lose"])


class LoopRegions(unittest.TestCase):
    """Two separate loops are two findings in one run, not one per run."""

    def test_each_loop_region_is_reported_in_the_same_run(self):
        flow = [
            ("filed", "start", "in_review", "agent"),
            ("in_review", "refuse", "refused", "system"),
            ("refused", "redo", "in_review", "agent"),
            ("in_review", "approve", "deploying", "system"),
            ("deploying", "unhealthy", "rolling_back", "system"),
            ("rolling_back", "rolled_back", "deploying", "system"),
            ("deploying", "healthy", "live", "system"),
        ]
        code, out = check(table(flow, initial="filed", ends=("live",)))
        self.assertEqual(code, 1, out)
        self.assertIn("region {in_review, refused}", out)
        self.assertIn("region {deploying, rolling_back}", out)
        self.assertIn("in_review --refuse--> refused ; refused --redo--> in_review", out)

    def test_a_region_lists_the_edges_that_close_its_loops(self):
        flow = [
            ("filed", "start", "a", "system"),
            ("a", "x", "b", "system"),
            ("b", "y", "a", "system"),
            ("a", "z", "c", "system"),
            ("c", "w", "a", "system"),
            ("a", "end", "done", "system"),
        ]
        code, out = check(table(flow, initial="filed", ends=("done",)))
        self.assertIn("closing edges: b --y--> a ; c --w--> a", out)

    def test_one_bound_inside_a_region_leaves_the_other_cycle_reported(self):
        flow = [
            ("filed", "start", "a", "system"),
            ("a", "x", "b", "system", {"bound": "n < 2"}),
            ("b", "y", "a", "system"),
            ("a", "z", "c", "system"),
            ("c", "w", "a", "system"),
            ("a", "end", "done", "system"),
        ]
        code, out = check(table(flow, initial="filed", ends=("done",)))
        self.assertEqual(code, 1, out)
        self.assertIn("region {a, c}", out)
        self.assertNotIn("region {a, b", out)


class OwnerDeclaredNull(unittest.TestCase):
    def test_owner_null_says_nobody_is_told_even_when_a_person_could_act(self):
        flow = [
            ("new", "assign", "working", "system"),
            ("working", "resolve", "resolved", "agent"),
            ("working", "stale_30d", "resolved", "system", {"timeout": "30d"}),
        ]
        code, out = check(table(flow, initial="new", ends=("resolved",), states={"working": {"owner": None}}))
        self.assertEqual(code, 1, out)
        self.assertIn("working waits on agent (human) and has no owner", out)


class GuardedSystemExit(unittest.TestCase):
    def test_a_state_the_system_leaves_only_under_a_guard_gets_a_note(self):
        flow = [
            ("new", "assign", "checking", "system"),
            ("checking", "pass", "done", "system", {"guard": "the check reported green"}),
            ("checking", "fail", "failed", "system", {"guard": "the check reported red"}),
            ("failed", "retry", "checking", "agent", {"bound": "tries < 3"}),
            ("failed", "give_up", "done", "system", {"timeout": "1d"}),
        ]
        code, out = check(table(flow, initial="new", ends=("done",)))
        self.assertIn("note guarded: checking", out)
        self.assertIn("the check reported green", out)


class DiagramLabels(unittest.TestCase):
    def test_label_text_that_would_break_mermaid_is_made_safe(self):
        flow = [("new", "start", "done", "system", {"guard": "next 00:00 UTC; or reset", "bound": "n < 3"})]
        code, out = run("diagram", table(flow, initial="new", ends=("done",)))
        self.assertEqual(code, 0, out)
        self.assertIn("new --> done : start / system [next 00.00 UTC, or reset] (n < 3)", out)


class Examples(unittest.TestCase):
    """The shipped examples show one clean table and two with the defects the skill is for."""

    EXAMPLES = os.path.join(HERE, "..", "every-path-ends", "examples")

    def run_example(self, name):
        done = subprocess.run([sys.executable, "-I", SCRIPT, "check", os.path.join(self.EXAMPLES, name)],
                              capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def test_the_order_passes_every_check(self):
        code, out = self.run_example("order.json")
        self.assertEqual(code, 0, out)

    def test_the_support_ticket_waits_on_the_customer_with_no_owner_and_loops_without_a_bound(self):
        code, out = self.run_example("support-ticket.json")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL waits-owned", out)
        self.assertIn("waiting_customer waits on customer (external) and has no owner and no timeout", out)
        self.assertIn("FAIL loops-bounded", out)
        self.assertIn("FAIL ends-reachable", out)   # closed_no_reply is declared but nothing leads there

    def test_the_deploy_traps_a_refused_build_and_waits_on_an_approver_with_no_timeout(self):
        code, out = self.run_example("deploy.json")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL exit", out)
        self.assertIn("refused is not an end state and has no transition out of it", out)
        self.assertIn("FAIL waits-owned", out)
        self.assertIn("awaiting_approval waits on approver (human) and has no timeout", out)
        self.assertIn("FAIL loops-bounded", out)   # unhealthy, rolled back, requested again, for ever


if __name__ == "__main__":
    unittest.main()
