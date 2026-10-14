# Decisions taken to build, each one reversible

Written 2026-10-14 by the agent that built the first version. Each entry is the default it picked, the alternatives, and what reversing it costs. None of these is settled until the owner says so.

## Name: `every-path-ends`

The skill's name is the property it proves, so a user who types it knows what they asked for, and the phrase appears in the report's last line ("every path ends").

Alternatives considered:
- `lifecycle-proof`: shorter, but "proof" overstates what a graph check does.
- `prove-the-process-ends`: says the same, longer, verb-first like `show-me`.
- `fsm-audit`: accurate, but "FSM" is a word for people who already know, and the skill is meant to trigger on "where does this get stuck".

Reversing: rename the directory and the `name` field; the script and the tests have no dependency on the name.

## Table format: JSON

JSON because Python's standard library reads it and so does every other language's, so a user on any stack can write the table and run the checker with nothing installed.

Alternatives:
- YAML: easier to write by hand, with comments. Needs PyYAML, which is not in the standard library, so the checker would stop being zero-install.
- A Markdown table parsed by the script: readable in a PR, but a hand parser is fragile, and `evidence` lists and per-state fields do not fit in a row. The `table` subcommand prints the Markdown view instead, so the PR gets the readable form and the checker keeps the strict one.

Reversing: a loader is one function (`Table.__init__` takes a dict); add a YAML branch when PyYAML is acceptable.

## Checker language: Python 3.9 standard library

Python because it is already on macOS (3.9.6 ships) and on most Linux hosts, and the standard library has JSON, a deque and argument handling. The script stays on 3.9 syntax (no `match`, no `X | Y` types at runtime) so the shipped interpreter runs it.

Alternatives:
- Node with no dependencies: Node 24 is on the build machine, but a stock macOS or Linux box does not ship it. Skill users in a JavaScript-only shop would prefer it.
- Both: twice the tests and twice the drift.

Reversing: the checks are seven small graph functions; a port is a morning's work. The tests run the script as a subprocess and read its output, so they would carry over.

## Actor kinds: system, human, external

Three kinds, because the waits check needs to know who can be held to a wait. A `human` inside the process owns the wait by default; an `external` party cannot own it, so the state must name an `owner`.

Alternative: two kinds (system and other) with an explicit `owner` on every wait. Simpler table, but then every human step needs an owner line that repeats the actor.

## A timeout is required on every wait, with `open_ended` as the escape

The handoff asked for "owner and a timeout edge" on every wait. A strict rule makes most real tables fail on their human steps, which is correct (a ticket in `new` with no SLA timer is unowned work) but noisy. The escape is a per-state `open_ended` reason, which the checker lists as a note rather than a failure. Writing the reason is the point: the agent has to say why the wait may last.

Alternative: fail only on `external` waits and warn on `human` ones. Quieter, but then the handoff's second real failure (waits on a person for hours) would print as a warning that a CI run ignores.

## Loop check: remove bounded edges, look for a cycle among non-end states

A cycle that still exists after bounded edges are removed is a loop nothing counts. This is the precise form of "every cycle carries a bound": one bounded edge per cycle suffices, which is also what code does (one counter on the retry). The checker prints the first such cycle it finds, not all of them, so one run fixes one loop; rerun for the next.

Alternative: enumerate every elementary cycle. Exact but exponential, and the output would repeat the same bound across many cycles.

## Report: terminal first, HTML at four or more findings

Terminal Markdown is the default because the common case is one to three paths and a diagram, and the diagram is the model. An HTML report follows the pattern of a cards-and-badges review and is only worth a file when there are enough cards to scroll.

## Not decided here

- Licence of the published skill. Nothing in the repo carries one yet.
- Publish target (personal GitHub or a company skills repo) and how skills.sh lists it. Not verified.
- Whether the skill is model-invoked (it has a description, so it is) or user-invoked. The description costs context every turn; if it misfires, set `disable-model-invocation: true` and strip the trigger list.
