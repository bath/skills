# Finding the lifecycle in a codebase

The table is only as good as the search that fed it. This file is the search.

## Where a lifecycle hides

Look in this order and keep going until nothing new appears:

1. **The status type.** An enum, a union of string literals, a `status`, `state`, `phase` or `stage` column, a set of labels or tags. Grep the name of the type, then every one of its values.
2. **Every writer.** Every place the status is set: `UPDATE ... SET status`, assignments, constructors, migrations that backfill it. Each writer is one or more rows. A writer with a condition in front of it is a row with a `guard`.
3. **Every mover.** Code that runs on its own and changes the status: schedulers, cron jobs, timers, retry loops, queue consumers, webhook handlers, polling loops that read an outside system. These are the rows an agent misses first, and they are where the timeouts and bounds live, when they exist.
4. **The documents.** A spec, a runbook, a glossary, an incident report. A document can name a state the code never writes (then it is an orphan) or a transition the code never makes (then the document is wrong or the code is). Cite the document the same way as code.
5. **The last ten incidents.** An incident is a path that did not end. Read it as a test case for the table: can the table express what happened?

## The state is often composite

A real system rarely keeps its state in one column. The state of a piece of work can be `status` plus a label plus whether a commit hash is set plus the outcome of its last run plus the last event in a log. Treat the tuple as the state and give each distinct tuple a name.

Do it this way:

- List the fields that together decide what happens next. Leave out fields that only describe (titles, timestamps, who created it).
- Enumerate the combinations the code can actually produce. Not every combination exists; the ones the code never writes are not states.
- Name each combination by what the thing is waiting for or doing (`merged_awaiting_staging`, not `closed+sha+pending`). Put the field values in the state's `note` so a reader can map it back.
- When two combinations behave the same from here on, merge them into one state. The checker does not care about history, only about what can happen next.

A state in the table that the code represents with five fields is fine. A state that the code represents with one field but that behaves two different ways depending on something else is two states.

## State or event

A state lasts. An event is an instant. `in_review` is a state; `review` is an event; `reviewed` is a state again. When the code has a status value that reads as a verb (`submit`, `retry`), ask what the thing is doing while that value is set and name the state after that.

## Who is the actor

The actor is who causes the event. Classify by what can be relied on:

| Kind | Meaning | Examples |
|---|---|---|
| `system` | the code moves it on its own, with no one to wait for | a timer firing, a job runner picking the next step, a write at the end of a function |
| `human` | a person inside the process, who can be held to it | an agent, an approver, an operator, a worker |
| `external` | a party or service outside the process, who cannot be held to it | a customer, a carrier, a CI provider, a payment gateway, a third-party API |

The classification drives the `waits-owned` check: a state that only `human` or `external` actors can move is a wait. A `human` mover is the wait's owner by default. An `external` mover is nobody's responsibility until the table names an `owner` on that state.

A polling loop that reads an outside system is `external`, not `system`: the loop runs, but the outside system decides when anything changes. A timer that gives up after a limit is `system` and carries `timeout`.

Two cases that look like `system` and are not:

- A `system` edge whose guard can only become true by an outside action (`refuse` when "the check reported red") is that outside party's edge. The code runs every cycle, but it gives the same answer until the party acts, so the state waits on the party. The checker prints a `guarded:` note on a state the system leaves only under guards, so you can look again.
- The actor's own process dying (a session that exits before it reports, a worker that crashes) is the actor's event, with the actor's kind. Nothing can rely on a crash, so the state stays a wait.

An automated agent on a timer (a patrol, a bot session with a recipe) is `human` when it has to decide what to do, and `system` only when its step is mechanical and tested. Its waits need the same owner and timeout as a person's.

## Evidence

Every row carries `evidence`: a `path:line` or `path:start-end` for code, a `path#heading` for a document. One row can carry several. Evidence is what lets a reviewer check a row in thirty seconds, and what lets the next agent regenerate the table after the code moves. A row with no evidence is a guess; mark it `"evidence": "assumed"` and say so in the output, so the user can confirm or strike it.

## Done when

- Every value of the status type appears in the table, as a state or inside a composite state's note.
- Every writer of the status has a row, and the row's evidence points at the write.
- Every scheduler, timer, webhook and queue consumer that touches the status has a row.
- For every state, you can say who moves it on, from the table alone.
- Every incident you read can be traced as a path through the table, or you have written down why it cannot.
