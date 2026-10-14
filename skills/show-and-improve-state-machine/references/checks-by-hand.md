# The seven checks by hand

For a session that cannot run `scripts/every_path.py`, because there is no interpreter or the command was denied. The checks are small graph walks. Do them on paper in this order and write the output in the script's shape. Put `HAND-CHECKED, NOT CHECKER OUTPUT.` on the first line, say why the script did not run, and say that the next session with an interpreter should rerun it and replace the file.

## Before the checks

- The states are every name in `initial`, `ends`, `states` and the rows, in order of first appearance. Keep that order. The script walks and prints in it.
- A row is usable when `from`, `on`, `to` and `actor` are non-empty strings, the actor is in `actors`, and each actor's kind is `system`, `human` or `external`.
- Paths come from a breadth-first walk over the rows in table order, started from every initial state in the order they are listed. The first time the walk reaches a state, its path is fixed. Every finding prints that path, in the form `(start) a --e1--> b ; b --e2--> c`. An initial state's own path is `(start) S`, with its own name.
- The ends-reach set: start from the ends and walk the rows backwards. Every state you touch can still reach an end.

## The checks, in print order

| Check | What to walk | Which edges count | The line |
|---|---|---|---|
| `reachable` | the forward walk | all | `nothing leads to S, so it cannot be reached from the start`, for each non-end state the walk did not reach |
| `ends-reachable` | the forward walk | all | `nothing leads to end state S, so it cannot be reached from the start` |
| `ends-closed` | each end's rows | all | `end state S has a way out, S --e--> T, so it is not an end` |
| `exit` | each non-end state's rows | all | `S is not an end state and has no transition out of it`, with its path |
| `can-end` | the ends-reach set | all | `S can be reached but no end can be reached from it. It is trapped with {the other such states}`, for each reachable non-end state outside the set. A dead end is one, and it is then also an `exit` finding |
| `waits-owned` | each reachable non-end state | movers are the exits with no `timeout` | see below |
| `loops-bounded` | the non-end states and the rows with no `bound` | rows between non-end states only | see below |

### waits-owned

A state waits when it has at least one mover and every mover's actor is `human` or `external`. For each wait:

- Owner. The state's `owner` when the key is present, where `null` means nobody. Otherwise the `human` movers, joined. Otherwise none. No owner and a timeout that reaches an end gives a note, `unowned: S waits on A (kind) with no owner, but e ends it after T`. No owner and no such timeout makes the finding say `no owner`.
- Timeout. An exit with `timeout` whose target is in the ends-reach set. When there is none and the state has `open_ended`, write a note instead: `open-ended: S waits on A (kind) with no timeout because <reason>`. When there is none but some timeout exits exist, the finding says `no timeout that reaches an end, because e leads to T and no end follows from there`. When there is none at all, it says `no timeout`.
- The line: `S waits on a (kind), b (kind) and has <what is missing, joined with " and ">`, then its path.
- A state that does not wait, whose `system` movers all carry a guard, gets a note: `guarded: the system moves S on only under a guard, e [guard] or f [guard]. If a guard needs an outside party to act, that party is the actor and the state is a wait`.
- The count line under the FAIL header: `N waits: a with no owner, b with no timeout`.

### loops-bounded

Drop the end states and every row with a `bound`. Group the rest into regions whose states can all reach each other, the strongly connected ones. A region with at least one row inside it loops. For each such region, find one example cycle by walking from the region's first state until a state on the walk repeats. Then find the closing edges, which are the rows a depth-first walk from the first state finds pointing at a state still on its walk. The line is `region {states} loops with no bounded edge: <cycle>. Nothing counts the rounds, so it can go round forever. Closing edges: <edges>`, then the path to the cycle's first state. The count line is `N loop regions`, or `1 loop region`.

## After the checks

End with `every path ends` when nothing failed, otherwise `N checks failed`, or `1 check failed`. The diagram and the table are mechanical too. Write the Mermaid by hand in the script's shape only when the user asked for it, and say it is hand-drawn.
