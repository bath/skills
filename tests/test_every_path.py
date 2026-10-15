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
SCRIPT = os.path.join(HERE, "..", "skills", "show-and-improve-state-machine", "scripts", "every_path.py")

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


class NoPassLineIsFalse(unittest.TestCase):
    """Each PASS sentence must be true of the whole table, not only of the states the check walked."""

    def test_a_dead_end_is_a_trap_under_can_end_as_well_as_exit(self):
        code, out = check(table([
            ("placed", "pay", "paid", "customer"),
            ("paid", "deliver", "delivered", "carrier"),
            ("placed", "cancel", "cancelled", "customer"),
        ]))
        self.assertIn("FAIL exit", out)
        self.assertIn("FAIL can-end", out)
        self.assertIn("cancelled is reachable, but no end is reachable from it. It has no way out.", out)
        self.assertNotIn("PASS can-end", out)

    def test_the_reachable_sentence_says_it_leaves_the_ends_to_ends_reachable(self):
        code, out = check(table([
            ("placed", "pay", "paid", "customer"),
            ("paid", "deliver", "delivered", "carrier"),
        ], ends=("delivered", "refunded")))
        self.assertIn("PASS reachable: every state that is not an end is reachable from the start", out)
        self.assertIn("FAIL ends-reachable", out)

    def test_the_waits_sentence_admits_open_ended_waits(self):
        flow = [("new", "assign", "working", "system"), ("working", "resolve", "resolved", "agent")]
        code, out = check(table(flow, initial="new", ends=("resolved",),
                                states={"working": {"open_ended": "reviewed each morning"}}))
        self.assertIn("PASS waits-owned: every reachable wait has an owner and a timeout that reaches an end, "
                      "or a written reason to be open-ended", out)


class SeveralInitialStates(unittest.TestCase):
    def test_a_path_starts_at_the_initial_state_it_comes_from(self):
        flow = [
            ("new", "assign", "working", "system"),
            ("working", "resolve", "resolved", "agent"),
            ("working", "stale_30d", "resolved", "system", {"timeout": "30d"}),
            ("imported", "review", "working", "reviewer"),
        ]
        data = table(flow, initial="new", ends=("resolved",))
        data["initial"] = ["new", "imported"]
        data["actors"]["reviewer"] = "external"
        code, out = check(data)
        self.assertEqual(code, 1, out)
        self.assertIn("imported waits on reviewer (external) and has no owner and no timeout\n    path: (start) imported", out)
        self.assertNotIn("(start) new\n", out.split("imported waits")[1])


class TrapRegions(unittest.TestCase):
    def test_two_unrelated_dead_ends_are_two_findings_that_do_not_name_each_other(self):
        flow = [
            ("placed", "pay", "paid", "customer"),
            ("paid", "deliver", "delivered", "carrier"),
            ("placed", "cancel", "cancelled", "customer"),
            ("paid", "lose", "lost", "carrier"),
        ]
        code, out = check(table(flow))
        self.assertIn("cancelled is reachable, but no end is reachable from it. It has no way out.", out)
        self.assertIn("lost is reachable, but no end is reachable from it. It has no way out.", out)
        self.assertNotIn("trapped with", out)

    def test_states_that_only_lead_to_each_other_are_one_region(self):
        flow = [
            ("filed", "start", "in_review", "agent"),
            ("in_review", "approve", "merged", "system"),
            ("in_review", "refuse", "refused", "system"),
            ("refused", "re_review", "refused_again", "system"),
            ("refused_again", "refuse", "refused", "system"),
        ]
        code, out = check(table(flow, initial="filed", ends=("merged",)))
        self.assertIn("refused is reachable, but no end is reachable from it. It loops within {refused, refused_again} and no end follows.", out)

    def test_a_state_whose_every_way_out_is_trapped_names_what_follows(self):
        flow = [
            ("filed", "start", "checking", "system"),
            ("checking", "pass", "done", "system"),
            ("checking", "fail", "failed", "system"),
            ("failed", "notify", "notified", "system"),
        ]
        code, out = check(table(flow, initial="filed", ends=("done",)))
        self.assertIn("failed is reachable, but no end is reachable from it. Everything after it is trapped too: {notified}.", out)
        self.assertIn("notified is reachable, but no end is reachable from it. It has no way out.", out)


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
        self.assertNotIn("has no owner", out)

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
    """A deploy that is refused and redone forever unless something counts the attempts."""

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
        self.assertIn("Closing edges: b --y--> a ; c --w--> a", out)

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
        ]
        code, out = check(table(flow, initial="new", ends=("resolved",), states={"working": {"owner": None}}))
        self.assertEqual(code, 1, out)
        self.assertIn("working waits on agent (human) and has no owner and no timeout", out)


class TimeoutCoversAMissingOwner(unittest.TestCase):
    """A clock that ends the wait in an end makes a missing owner a note, not a failure."""

    FLOW = [
        ("new", "send", "unconfirmed", "system"),
        ("unconfirmed", "confirm", "confirmed", "person"),
        ("unconfirmed", "link_expires_14d", "expired", "system", {"timeout": "14d"}),
    ]

    def with_person(self, flow, ends):
        data = table(flow, initial="new", ends=ends)
        data["actors"]["person"] = "external"
        return data

    def test_an_unowned_wait_with_a_timeout_that_reaches_an_end_passes_with_a_note(self):
        code, out = check(self.with_person(self.FLOW, ("confirmed", "expired")))
        self.assertEqual(code, 0, out)
        self.assertIn("PASS waits-owned", out)
        self.assertIn("note unowned: unconfirmed waits on person (external) with no owner, but link_expires_14d ends it after 14d", out)

    def test_a_timeout_into_a_trap_does_not_cover_the_missing_owner(self):
        flow = self.FLOW + [("expired", "archive", "archived", "system")]  # archived has no exit and is not an end
        code, out = check(self.with_person(flow, ("confirmed",)))
        self.assertEqual(code, 1, out)
        self.assertIn("unconfirmed waits on person (external) and has no owner and no timeout that reaches an end", out)


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
        self.assertIn("note guarded: the system moves checking on only under a guard, pass [the check reported green] "
                      "or fail [the check reported red]", out)


class DiagramLabels(unittest.TestCase):
    def test_label_text_that_would_break_mermaid_is_made_safe(self):
        flow = [("new", "start", "done", "system", {"guard": "next 00:00 UTC; or reset", "bound": "n < 3"})]
        code, out = run("diagram", table(flow, initial="new", ends=("done",)))
        self.assertEqual(code, 0, out)
        self.assertIn("new --> done : start / system [next 00.00 UTC, or reset] (n < 3)", out)


class TimeoutIntoATrap(unittest.TestCase):
    """A 14-day watch that leads to a state nothing leaves is not a way out of the wait."""

    FLOW = [
        ("new", "assign", "working", "system"),
        ("working", "resolve", "resolved", "agent"),
        ("working", "watch_14d", "expired", "system", {"timeout": "14d"}),
    ]

    def test_a_timeout_whose_target_cannot_reach_an_end_does_not_count(self):
        code, out = check(table(self.FLOW, initial="new", ends=("resolved",)))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL waits-owned", out)
        self.assertIn("working waits on agent (human) and has no timeout that reaches an end, "
                      "because watch_14d leads to expired and no end follows from there", out)

    def test_a_timeout_into_a_state_that_still_ends_counts(self):
        flow = self.FLOW + [("expired", "archive", "resolved", "system")]
        code, out = check(table(flow, initial="new", ends=("resolved",)))
        self.assertEqual(code, 0, out)


class SummaryLines(unittest.TestCase):
    def test_a_failed_check_prints_a_count_line_before_the_detail(self):
        flow = [
            ("new", "assign", "working", "system"),
            ("working", "ask", "waiting_customer", "agent", {"bound": "asks < 3"}),
            ("waiting_customer", "reply", "working", "customer"),
            ("working", "resolve", "resolved", "agent"),
            ("working", "stale", "resolved", "system", {"timeout": "30d"}),
            ("working", "park", "parked", "agent"),
            ("parked", "unpark", "working", "agent", {"bound": "parks < 2"}),
        ]
        code, out = check(table(flow, initial="new", ends=("resolved",)))
        self.assertIn("FAIL waits-owned: every reachable wait has an owner and a timeout that reaches an end, "
                      "or a written reason to be open-ended\n  2 waits: 1 with no owner, 2 with no timeout\n", out)

    def test_a_passed_check_has_no_count_line(self):
        code, out = check(table([("a", "go", "b", "system")], initial="a", ends=("b",)))
        self.assertIn("or a written reason to be open-ended\nPASS loops-bounded", out)


class OpenEndedWithEvidence(unittest.TestCase):
    def test_open_ended_can_say_what_kind_of_evidence_it_rests_on(self):
        flow = [
            ("new", "assign", "working", "system"),
            ("working", "resolve", "resolved", "agent"),
        ]
        code, out = check(table(flow, initial="new", ends=("resolved",), states={"working": {"open_ended": {
            "reason": "the morning patrol reads the queue",
            "kind": "recipe",
            "evidence": "recipes/patrol.toml:14",
        }}}))
        self.assertEqual(code, 0, out)
        self.assertIn("note open-ended (recipe, recipes/patrol.toml:14): working waits on agent (human) with no timeout "
                      "because the morning patrol reads the queue", out)

    def test_an_unknown_evidence_kind_is_a_table_error(self):
        flow = [("new", "go", "done", "system")]
        code, out = check(table(flow, initial="new", ends=("done",),
                                states={"new": {"open_ended": {"reason": "x", "kind": "vibes"}}}))
        self.assertEqual(code, 2, out)
        self.assertIn("kind must be one of code, timer, recipe, schedule, document", out)


class Examples(unittest.TestCase):
    """The shipped examples show one clean table and two with the defects the skill is for."""

    EXAMPLES = os.path.join(HERE, "..", "skills", "show-and-improve-state-machine", "examples")

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
        self.assertIn("FAIL loops-bounded", out)   # unhealthy, rolled back, requested again, forever


if __name__ == "__main__":
    unittest.main()
