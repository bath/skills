---
name: show-and-improve-state-machine
license: MIT
description: Model a process in a codebase or a document as a state machine and prove that every path ends in a known end state, or list the paths that do not. Use when asked to model a lifecycle, workflow, pipeline, status flow or the life of a piece of work. Also use to find states that are stuck, trapped or unreachable, to find work that waits on nobody, to check that retries are bounded, or to draw a state diagram from code. Also use when a ticket asks "show every path that has no known end" or "where can this get stuck".
---

# Show and improve a state machine

This skill turns a process into one transition table with evidence, runs a checker over the table, and writes a page with the diagram, the checks and ways to close each gap.

A process that looks finished can hide four defects: a state nothing can leave, a wait that nobody owns and nothing times out, a loop that nothing counts, and an end state that nothing reaches. The checker finds all four and prints the path to each one. The diagram, the checks and the page all come from the table, so the diagram always shows what the checker checked.

## Steps

### 1. Find the lifecycle

Read [references/extraction.md](references/extraction.md) before you open the code. It says where a lifecycle hides, how to tell a state from an event, and what to do when the real state is spread over several fields.

You are done when every writer of the state is in the table with a `file:line`, every event that moves it has a row, and you can name who moves each state on. Timers, webhooks and queue consumers count as events.

### 2. Write the table

One JSON file, in the format [references/table.md](references/table.md) gives. A row is `from`, `on`, `to` and `actor`, plus `guard`, `timeout`, `bound` and `evidence` when they apply. Declare the `initial` state, the `ends`, and each `actor` as `system`, `human` or `external`.

Three rules decide most rows.

- A state is a condition that lasts, such as `awaiting_approval`. An event is the instant that changes it, such as `approve`. A name that reads as a verb is an event.
- The actor is who causes the event, never who writes the row. A webhook handler that writes `delivered` records the carrier's action, so the actor is `carrier` and its kind is `external`.
- An end is a state the process is allowed to stop in. `closed` is an end only if nothing reopens it. If something does, take the reopen edge out of scope with a note, or stop calling it an end.

You are done when the checker loads the file without a table error.

### 3. Run the checker

```
python3 <skill dir>/scripts/every_path.py check process.json
```

It prints PASS or FAIL for each check. Under a FAIL it prints a count line, then each failing state with the path from the start that reaches it. `--json` gives the same findings as data. When the script cannot run, because there is no interpreter or the user denied the command, apply [references/checks-by-hand.md](references/checks-by-hand.md) and mark the output hand-checked.

The checks, in the order they print:

| Check | Fails when |
|---|---|
| `reachable` | a state that is not an end has no path from the start |
| `ends-reachable` | a declared end has no path from the start |
| `ends-closed` | a declared end has a transition out of it |
| `exit` | a state that is not an end has no transition out |
| `can-end` | a reachable state can no longer reach any end. A dead end counts, and so does a group of states that only lead to each other |
| `waits-owned` | a wait has no timeout edge that reaches an end, and either no owner or no written reason to be open-ended. A wait is a reachable state that only a person or an outside party can move. An unowned wait that a clock ends in an end passes with a note |
| `loops-bounded` | a loop that avoids every end has no edge with a `bound` |

`loops-bounded` prints one finding per region of states that loop among themselves, with one example cycle. A region can hold more cycles than the example, so run the checker again after each bound. Read every failure before you fix any. One missing edge often explains three findings.

### 4. Offer ways to close each path

For each failing path, write two to four ways to close it as a card in the judgement file. Each way carries a strength badge. [references/options.md](references/options.md) has the menu per failure type, and [references/report.md](references/report.md) has the judgement file's format. Then ask which one the user wants and work through the pick with them, using the `grilling` skill when it is installed. When nobody can answer, in a worker run or from a ticket, write your pick and the order and stop. Change the table first, run the checker again, and only then change the code.

### 5. Write the report page

Every run ends here, whatever the checker found:

```
python3 <skill dir>/scripts/every_path.py report process.json --judgement judgement.json --out report.html
```

The script fills the numbers, the checks in plain words, the diagram, the waits table and the loop regions from the table. The judgement file carries what the script cannot know: an example the reader saw, what the reader sees in each wait, the fix cards with a pick, and the trust notes. In an interactive run, write the page to a temp directory from `mktemp -d`, open it with `open` on macOS or `xdg-open` on Linux, and say the path. In a worker run, write it to the caller's folder and name the path in the reply.

Keep the chat message short. Give the path to the page, then one line per path with no known end, in the checker's words. When someone asks for a chat view, `diagram` prints the Mermaid with failing states coloured and `table` prints the table as Markdown:

```
python3 <skill dir>/scripts/every_path.py diagram process.json
python3 <skill dir>/scripts/every_path.py table process.json
```

### 6. Keep it alive

A table that lives in a chat goes stale the week after. Commit it beside the code it describes and run the checker as a test, so the next state someone adds with no exit fails CI:

```
python3 path/to/every_path.py check docs/lifecycle/order.json
```

The exit code is 1 on any failure. The script needs Python 3.9 and nothing else.

## What the checker proves

The checks read the graph only. `can-end` proves that some end is still possible from every state, not that the process gets there, so a state can sit forever and still pass. `waits-owned` and `loops-bounded` close that gap, with a timeout that ends each wait and a bound that ends each loop. With all seven green, every path ends, provided the code fires the timeouts and keeps the counts the table claims. Check those two claims in the code as closely as the edges.

When several instances or actors interleave, say an item taken back while its pull request sits in the merge queue, a single-instance graph cannot see the conflict. Escalate to a model checker there, such as the `tlaplus-from-source` skill.

## Examples

[examples/order.json](examples/order.json) passes. [examples/support-ticket.json](examples/support-ticket.json) waits on a customer with no owner and loops without a bound. [examples/deploy.json](examples/deploy.json) traps a refused build and waits on an approver with no timeout. Run `check` on each to see the report shape.
