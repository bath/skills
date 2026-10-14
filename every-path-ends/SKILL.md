---
name: every-path-ends
description: Model a process in a codebase or a document as a state machine and prove that every path ends in a known end state, or list the paths that do not. Use when asked to model a lifecycle, workflow, pipeline, status flow or the life of a piece of work; to find states that are stuck, trapped or unreachable; to find work that waits on nobody; to check that retries are bounded; or to draw a state diagram from code. Also use when a ticket says "show every path that has no known end" or "where can this get stuck".
---

# Every path ends

A process is a graph of states. Four things go wrong with such a graph, and all four hide in code that looks finished: a state nothing can leave (a trap), a wait that nobody owns and nothing times out, a loop that nothing counts, and an end state that is only declared. This skill turns the process into one transition table with evidence, runs a checker that finds all four and prints a concrete path to each, and draws the diagram from the same table so the picture cannot drift from the proof.

The model is the table. Everything else is derived from it.

## Steps

### 1. Find the lifecycle

Read [references/extraction.md](references/extraction.md) before you open the code. It says where a lifecycle hides, how to tell a state from an event, and how to handle the common case where the real state is spread over several fields.

Done when every writer of the state is in the table with a `file:line`, every event that moves it has a row (timers, webhooks and queue consumers included), and you can say for each state who moves it on.

### 2. Write the table

One JSON file, the format in [references/table.md](references/table.md). A row is `from`, `on`, `to`, `actor`, plus `guard`, `timeout`, `bound` and `evidence` when they apply. Declare the `initial` state, the `ends`, and each `actor` as `system`, `human` or `external`.

Three rules decide most rows:

- A state is a condition that lasts (`awaiting_approval`); an event is the instant that changes it (`approve`). A name that reads as a verb is an event, not a state.
- The actor is who causes the event, never who writes the row. A webhook handler that writes `delivered` is the carrier's action, so the actor is `carrier` and its kind is `external`.
- An end is a state the process is allowed to stop in. `closed` is an end only if nothing reopens it; if something does, either take the reopen edge out of scope with a note, or stop calling it an end.

Done when the checker loads the file without a table error.

### 3. Run the checker

```
python3 scripts/every_path.py check process.json
```

It prints PASS or FAIL for each property and, for each failure, the state and the path from the start that reaches it. `--json` gives the same findings as data. The properties, in the order they print:

| Check | Fails when |
|---|---|
| `reachable` | a state has no path from the start |
| `ends-reachable` | a declared end has no path from the start |
| `ends-closed` | a declared end has a transition out of it |
| `exit` | a state that is not an end has no transition out |
| `can-end` | a reachable state can no longer reach any end (a trap of one or more states) |
| `waits-owned` | a state only a person or an outside party can move has no owner, or no timeout edge |
| `loops-bounded` | a loop that avoids every end has no edge with a `bound` |

Read every failure before you fix any. One missing edge often explains three findings.

### 4. Show it

```
python3 scripts/every_path.py diagram process.json   # Mermaid stateDiagram-v2, failing states coloured
python3 scripts/every_path.py table process.json     # the table as Markdown, with a wait/owner/timeout summary
```

Default output to the user: the diagram, then one line per path with no known end, in the words of the checker. Pick the smallest view that makes the point. Three findings fit in a message; more than that earns one HTML report, see [references/options.md](references/options.md).

### 5. Offer ways to close each path

For each failing path, write two to four ways to close it, each a card with a strength badge and a before/after of the edges that change. The menu per failure type is in [references/options.md](references/options.md). Then ask which one the user wants, and work through the pick with them (the `grilling` skill, when it is installed). Change the table first, run the checker again, and only then change the code.

### 6. Keep it alive

A table that lives in a chat goes stale the week after. Commit it beside the code it describes and run the checker as a test, so the next state someone adds with no exit fails CI:

```
python3 path/to/every_path.py check docs/lifecycle/order.json
```

Exit code 1 on any failure. The script has no dependencies beyond Python 3.9.

## What the checker proves

The checks are on the graph. `can-end` proves that from every state some end is still possible, not that it will be reached: a state can sit for ever and still pass. The two checks that turn possible into certain are `waits-owned` (a timeout ends the wait) and `loops-bounded` (a bound ends the loop). With all seven green, every path ends, as long as the code fires the timeouts and keeps the counts the table claims. Verify those two claims in the code with the same care as the edges.

When several instances or actors interleave (an item taken back while its pull request is in the merge queue), a single-instance graph cannot see the conflict. That is the point to escalate to a model checker; the `tlaplus-from-source` skill is built for it.

## Examples

[examples/order.json](examples/order.json) passes. [examples/support-ticket.json](examples/support-ticket.json) waits on a customer with no owner and loops without a bound. [examples/deploy.json](examples/deploy.json) traps a refused build and waits on an approver with no timeout. Run `check` on each to see the report shape.
