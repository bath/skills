# The seven checks by hand

For a session that cannot run `scripts/every_path.py` (no interpreter, a denied command). The checks are small graph walks; do them on paper in this order and write the output in the script's shape. Put `HAND-CHECKED, NOT CHECKER OUTPUT.` as the first line, say why the script did not run, and say that the next session with an interpreter should rerun it and replace the file.

## Before the checks

- States are every name in `initial`, `ends`, `states` and the rows, in that order of first appearance. Keep that order; the script walks and prints in it.
- A row is usable when `from`, `on`, `to` and `actor` are non-empty strings, the actor is in `actors`, and each actor's kind is `system`, `human` or `external`.
- Paths: a breadth-first walk from the initial state over the rows in table order. The first time a state is reached, its path is fixed. That path is what every finding prints, in the form `(start) a --e1--> b ; b --e2--> c`.
- Ends-reach set: start from the ends and walk the rows backwards; every state you touch can still reach an end.

## The checks, in print order

| Check | What to walk | Which edges count | The line |
|---|---|---|---|
| `reachable` | the forward walk | all | `S cannot be reached from the start; nothing leads to it` for each non-end state the walk did not reach |
| `ends-reachable` | the forward walk | all | `end state S cannot be reached from the start; nothing leads to it` |
| `ends-closed` | each end's rows | all | `end state S has a way out: S --e--> T; an end that exits is not an end` |
| `exit` | each non-end state's rows | all | `S is not an end state and has no transition out of it`, with its path |
| `can-end` | the ends-reach set | all | `S can be reached but no end can be reached from it; it is trapped with {the other such states}`, for each reachable non-end state that is not in the set, a dead end included (it is then also an `exit` finding) |
| `waits-owned` | each reachable non-end state | movers are the exits with no `timeout` | see below |
| `loops-bounded` | the non-end states with the rows that carry no `bound` | rows between non-end states only | see below |

### waits-owned

A state waits when it has at least one mover and every mover's actor is `human` or `external`. For each wait:

- Owner: the state's `owner` when the key is present (`null` means nobody); else the `human` movers, joined; else none. Missing: `no owner`.
- Timeout: an exit with `timeout` whose target is in the ends-reach set. None, and the state has `open_ended`: a note `open-ended: S waits on A (kind) with no timeout because <reason>`. None, and some timeout exits exist: `no timeout that reaches an end (e leads to T, from which no end can be reached)`. None at all: `no timeout`.
- The line: `S waits on a (kind), b (kind) and has <missing, joined with " and ">`, then its path.
- A state that does not wait, whose `system` movers all carry a guard, gets a note `guarded: S is moved by the system only under a guard (e [guard]); ...`.
- The count line under the FAIL header: `N waits: a with no owner, b with no timeout`.

### loops-bounded

Drop the end states and every row with a `bound`. Group the rest into regions that can reach each other both ways (strongly connected). A region with at least one row inside it loops. For each: one example cycle, found by walking from the region's first state until a state on the walk repeats; and the closing edges, which are the rows a depth-first walk from the first state finds pointing at a state still on its walk. The line: `a loop with no bounded edge through region {states}: <cycle>; nothing counts the attempts, so it can go round for ever; closing edges: <edges>`, then the path to the cycle's first state. The count line: `N loop region(s)`.

## After the checks

End with `every path ends` when nothing failed, else `N check(s) failed`. The diagram and the table are mechanical too: write the Mermaid by hand in the script's shape only when the user asked for it; say it is hand-drawn.
