# Decisions taken to build, each one reversible

The agent that built the first version wrote this on 2026-10-14. Each entry gives the default it picked, the alternatives, and what reversing it costs. None of these is settled until the owner says so.

## Name: `every-path-ends`, superseded below

The skill's name is the property it proves, so a user who types it knows what they asked for, and the phrase appears in the report's last line, "every path ends".

Alternatives considered:
- `lifecycle-proof` is shorter, but "proof" overstates what a graph check does.
- `prove-the-process-ends` says the same, longer, verb-first like `show-me`.
- `fsm-audit` is accurate, but "FSM" is a word for people who already know, and the skill is meant to trigger on "where does this get stuck".

Reversing it means renaming the directory and the `name` field. The script and the tests have no dependency on the name.

## Table format: JSON

JSON, because Python's standard library reads it and so does every other language's. A user on any stack can write the table and run the checker with nothing installed.

Alternatives:
- YAML is easier to write by hand, with comments. It needs PyYAML, which is not in the standard library, so the checker would stop being zero-install.
- A Markdown table parsed by the script is readable in a PR, but a hand parser is fragile, and `evidence` lists and per-state fields do not fit in a row. The `table` subcommand prints the Markdown view instead, so the PR gets the readable form and the checker keeps the strict one.

Reversing it is one function. `Table.__init__` takes a dict, so add a YAML branch when PyYAML is acceptable.

## Checker language: Python 3.9 standard library

Python, because macOS ships 3.9.6 and most Linux hosts have it, and the standard library has JSON, a deque and argument handling. The script stays on 3.9 syntax, with no `match` and no `X | Y` types at runtime, so the shipped interpreter runs it.

Alternatives:
- Node with no dependencies. Node 24 is on the build machine, but a stock macOS or Linux box does not ship it. Skill users in a JavaScript-only shop would prefer it.
- Both. Twice the tests and twice the drift.

Reversing it is a morning's work. The checks are seven small graph functions, and the tests run the script as a subprocess and read its output, so they would carry over.

## Actor kinds: system, human, external

Three kinds, because the waits check needs to know who can be held to a wait. A `human` inside the process owns the wait by default. An `external` party cannot own it, so the state must name an `owner`.

The alternative was two kinds, system and other, with an explicit `owner` on every wait. A simpler table, but then every human step needs an owner line that repeats the actor.

## A timeout is required on every wait, with `open_ended` as the escape

The handoff asked for an owner and a timeout edge on every wait. A strict rule makes most real tables fail on their human steps. That is correct, since a ticket in `new` with no SLA timer is unowned work, but it is noisy. The escape is a per-state `open_ended` reason, which the checker lists as a note rather than a failure. Writing the reason is the point. The agent has to say why the wait may last.

The alternative was to fail only on `external` waits and warn on `human` ones. Quieter, but then the handoff's second real failure, work that waits on a person for hours, would print as a warning that a CI run ignores.

## Loop check: remove bounded edges, look for a cycle among non-end states

A cycle that still exists after the bounded edges are removed is a loop nothing counts. This is the precise form of "every cycle carries a bound". One bounded edge per cycle suffices, which is also what code does with one counter on the retry.

The alternative was to enumerate every elementary cycle. Exact but exponential, and the output would repeat the same bound across many cycles.

## Report: terminal first, HTML at four or more findings, superseded below

Terminal Markdown was the default because the common case is one to three paths and a diagram. The HTML page was only written at four or more findings. Reversed on 2026-10-14. The page is written on every run.

## Not decided here

- The licence of the published skill. Nothing in the repo carried one at first.
- The publish target, a personal GitHub or a company skills repo, and how skills.sh lists it. Not verified.
- Whether the skill is model-invoked or user-invoked. It has a description, so it is model-invoked. The description costs context every turn. If it misfires, set `disable-model-invocation: true` and strip the trigger list.

## Added after the first dogfood run, 2026-10-14

### A loop finding is one per region, with its closing edges

The first checker printed the first cycle it found, one per run. The dogfood table had 29. Now `loops-bounded` prints one finding per strongly connected region of non-end states, after the bounded edges are removed, with one example cycle and the list of edges a depth-first walk finds pointing back into the region. A bound on each closing edge breaks every loop in the region, and the agent groups them by meaning.

The alternative was to enumerate every elementary cycle. Exact, exponential in the worst case, and the dogfood table shows why not. The same re-sling edge would appear in most of the 29.

### `"owner": null` says that nobody is told

The checker used to take a human mover as the owner of a wait without question. The dogfood found a state, a pull request whose check never completes, where the person who could act is never told it is stuck. Now `owner` means the person the code tells. A human mover is still the default, and an explicit `null` records that nobody is told, which fails the check.

The alternative was to require a declared owner on every wait. Honest, but it makes the agent repeat the actor on every human step.

### The checker notes a state the system leaves only under guards

A `system` edge with a guard that only an outside party can satisfy hides a wait. The checker cannot read the guard, so it prints a `guarded:` note for every state whose system exits are all guarded, and the extraction reference says how to re-attribute the edge. The alternative was a warning that fails the run. Too many honest system edges carry a guard.

## Added after the second dogfood run, the card view, 2026-10-14

### A timeout counts only when its target can still reach an end

A watch that stops drawing a view after 14 days led every wait to one state nothing leaves. Every wait then passed `waits-owned`, and only `exit` named the trap. Now a timeout edge satisfies the check only when its target is in the set of states that can reach an end. The finding names a timeout into a trap, "no timeout that reaches an end, because watch_14d leads to card_expired and no end follows from there", so the fix reads as "give the trap an exit", not "add a timeout".

The alternative was a separate check, "timeout leads to a trap". It would print the same states twice, once under `exit` or `can-end` and once under the new check, and leave `waits-owned` green, which is the misleading part.

### `open_ended` can be a map with `kind` and `evidence`

An open-ended reason that rests on recipe text, an agent following words, is weaker than one that rests on a timer in code. The string form stays. The map form adds `kind`, one of code, timer, recipe, schedule or document, and `evidence`, and the note and the table view print them.

The alternative was a top-level `evidence_kind` on every row. Heavier, and the row's `evidence` path already says what it is for a transition. The distinction only matters for a wait that is excused.

### Hand checks are a reference file, not a mode of the script

A session that cannot run the script applies `references/checks-by-hand.md` and marks the output hand-checked. The file mirrors the script's walks and line shapes, so a hand result and a machine result can be diffed. The alternative, a JavaScript port for sessions with Node and no Python, was not taken. The second run's problem was a denied command, not a missing interpreter.

### A PASS sentence is true of the whole table

`can-end` used to skip a state with no exit, because `exit` already named it, and then print "from every reachable state some end is still reachable" while a dead end sat in the table. Now `can-end` lists every reachable state that cannot reach an end, exits or not, and a dead end appears under both checks. One duplicated line is the price of a PASS that means "nothing is trapped".

The audit of the other six sentences changed two. `reachable` now says "every state that is not an end", because an orphan end is `ends-reachable`'s finding. `waits-owned` now says "every reachable wait ... or a written reason to be open-ended", because an unreachable wait is `reachable`'s and an excused wait is a note. `ends-reachable`, `ends-closed`, `exit` and `loops-bounded` test what they say.

The alternative for `can-end` was to keep the skip and weaken the sentence to "every reachable state that has a way out". Rejected. A reader then needs two lines to know whether anything is trapped, and the first dogfood run showed that one green line is what gets read.

## Renamed to `show-and-improve-state-machine`, 2026-10-14

The working name was `every-path-ends`, the property the checker proves. The published name says what the skill does for the reader. "Show" is the report, the diagram, the checks and the waits. "Improve" is the option cards with a pick. The Agent Skills specification requires `name` to match the folder, so the folder, the frontmatter, the tests, the eval file and every path changed together. The description still opens with the proof claim, so a search for "prove", "stuck" or "end state" finds it. The report's last line still says "every path ends".

## Laid out as a catalog, `skills/<name>/`, 2026-10-14

The `npx skills` CLI finds a skill at the repo root or under fixed folders such as `skills/<name>/SKILL.md`. The future public repo is a catalog, `bath/skills`, so the skill moved to `skills/show-and-improve-state-machine/`, and the tests, evals, README, DECISIONS.md and LICENSE stay at the root. The licence is MIT, in the frontmatter and in `LICENSE`, copyright Miller Bath 2026. The alternative, one repo per skill, was not taken. The owner wants more skills in one place.

## The report page is the script's, 2026-10-14

The HTML report used to be described in one paragraph, and the agent wrote it fresh each run, so no two pages looked alike. Now `report` fills a shipped template, `assets/report.html`, from the table, and a small judgement JSON carries the parts that need an agent: the example the reader saw, the fix cards with a pick, the trust notes. The template loads only Mermaid and the fonts, uses colour tokens with a dark theme, and reads at phone width.

Two alternatives were rejected. Keeping the page in prose, because the owner saw one page and wants that page every time. Putting the judgement inside the table file, because the table is the model and should stay checkable without opinions in it.

## The page is written on every run, 2026-10-14

The four-findings threshold is gone. Every run ends with `report`. An interactive run writes the page to a temp directory, opens it and says the path. A worker run writes it to the caller's folder. The chat message is the path and one line per failing path. The owner saw the page and reads it before the terminal, so a threshold only decided when to withhold the thing he wanted.

The judgement file gained one optional field, `waits`, a map of state name to what the reader sees in that state. Given, the waits table shows a "What the reader sees" column. The table cannot carry it. What a reader sees is a reading of the view, not a fact of the graph.

## A clock that ends the wait covers a missing owner (2026-10-14)

Two test runs had to overrule the checker on the same point. A wait that nobody is told about, but that a timeout takes to an end, failed `waits-owned` for "no owner". The runs marked those states low severity by hand, because the path has a known end. Now such a wait passes, with a note that says nobody is told and which clock ends it. A missing owner fails only when no clock reaches an end from the state.

The reason for the rule is what the owner is for. The owner is the person who ends a wait that would otherwise last. When a clock ends it, there is no such person to name. The note stays, because a reader may still want someone told before the clock runs out.

The alternative was to keep the failure and let the agent mark the state open-ended. That puts a false reason in the table, since the wait is not open-ended at all.

## A trap finding names its own region (2026-10-14)

`can-end` used to list every trapped state in one set, so two dead ends that had nothing to do with each other read as if they formed a cycle together. Now each finding ends in one of three ways. A dead end has no way out. A state in a cycle loops within its own region, which is the set of states that reach each other. A state whose every way out leads into a trap names what follows it. Two unrelated dead ends are two findings, and neither names the other.
