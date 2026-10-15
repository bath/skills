# Finding the lifecycle in a codebase

A state the search misses never reaches the table, and the checker cannot report it.

## Where a lifecycle hides

Look in this order and keep going until nothing new appears.

1. **The status type.** An enum, a union of string literals, a `status`, `state`, `phase` or `stage` column, a set of labels or tags. Grep the name of the type, then every one of its values.
2. **Every writer.** Every place that sets the status: `UPDATE ... SET status`, assignments, constructors, migrations that backfill it. Each writer is one or more rows. A writer with a condition in front of it is a row with a `guard`.
3. **Every mover.** Code that runs on its own and changes the status: schedulers, cron jobs, timers, retry loops, queue consumers, webhook handlers, polling loops that read an outside system. An agent misses these rows first, and they hold the timeouts and bounds, if any exist.
4. **The documents.** A spec, a runbook, a glossary, an incident report. A document can name a state the code never writes, which makes it an orphan. It can name a transition the code never makes, and then either the document or the code is wrong. Cite a document the same way as code.
5. **The last ten incidents.** An incident is a path that did not end. Read each one as a test case for the table. Can the table express what happened?

## The window between two writes

Code often writes a status and then does a second step. It marks the request approved, then creates the invite. It sets `sending`, then calls the provider, then sets `sent`. The window between the first write and the second step is a state, because the process can die there and the second step can fail there. The row then shows the first value forever, and nothing moves it.

Look for every writer that is followed by a send, a call to an outside service, or a second write, and ask what the row looks like if the process stops between the two. Give that window a state of its own, such as `invite_sending` or `approved_unsent`, with the crash or the failure as the edge into it. Then look for the way out: a job that retries, a job that sweeps old rows, or a person who is told. If there is none, the checker reports a trap, and that trap is real. These windows are easy to miss because the code around them looks finished, so read for them on purpose.

The actor on the edge into the window is the process itself when it dies, and the outside service when the call fails. Both are `external`. Nothing can rely on either.

## A view of a lifecycle is its own lifecycle

The thing you model may be a view of the object, such as a card in a chat or a row on a dashboard. Model the view when the question is about the view, as in "which cards never reach a final line". Then:

- The view's states are what it draws, not the object's fields. Fold the object's states the view draws nothing for into one, and say so in the `note`. Add the states only the view has, such as a message that failed to send or a watch that expired.
- The view's ends are where the view stops changing, which can differ from the object's ends. An object can end while its view still waits, and a view can end, at an expiry, while the object goes on. Declare the view's ends, and name in `note` the object states they match.
- Keep one table per thing. A view and its object are two tables, with a line in each `note` that maps the state to the other.

## The state is often composite

A real system rarely keeps its state in one column. The state of a piece of work can be `status` plus a label plus whether a commit hash is set plus the outcome of its last run plus the last event in a log. Treat the tuple as the state and give each distinct tuple a name.

- List the fields that together decide what happens next. Leave out fields that only describe, such as titles, timestamps and who created it.
- Enumerate the combinations the code can produce. A combination the code never writes is not a state.
- Name each combination by what the thing is waiting for or doing, `merged_awaiting_staging` rather than `closed+sha+pending`. Put the field values in the state's `note` so a reader can map it back.
- When two combinations behave the same from here on, merge them into one state. The checker looks only at what can happen next.

A state the code represents with five fields is fine. A state the code represents with one field, but that behaves two different ways depending on something else, is two states.

## A guard that depends on history

A guard such as "an earlier run left a pull request" reads the past, not the present. The checker does not read guards, so its shortest path can take the edge from a state the history never allows, and the printed path is one that cannot happen. Two ways out:

- Split the state. The history is part of the state, so `with_worker` becomes `with_worker` and `with_worker_after_refusal`. The paths are then real and the diagram shows the two lives. Prefer this.
- Keep the state and rewrite the path by hand in the report, saying that the printed one uses an edge the history forbids. This is cheaper, but the next run makes the same mistake.

## State or event

A state lasts. An event is an instant. `in_review` is a state, `review` is an event, and `reviewed` is a state again. When the code has a status value that reads as a verb, such as `submit` or `retry`, ask what the thing is doing while that value is set and name the state after that.

## Who is the actor

The actor is who causes the event. Classify by whether the process can rely on it.

| Kind | Meaning | Examples |
|---|---|---|
| `system` | the code moves it on its own, with no one to wait for | a timer firing, a job runner picking the next step, a write at the end of a function |
| `human` | a person inside the process, who can be held to it | an agent, an approver, an operator, a worker |
| `external` | a party or service outside the process, who cannot be held to it | a customer, a carrier, a CI provider, a payment gateway, a third-party API |

The classification drives the `waits-owned` check. A state that only `human` or `external` actors can move is a wait. A `human` mover owns the wait by default. An `external` mover is nobody's responsibility until the table names an `owner` on that state.

A polling loop that reads an outside system is `external`, not `system`. The loop runs, but the outside system decides when anything changes. A timer that gives up after a limit is `system` and carries `timeout`.

Two cases look like `system` and are not.

- A `system` edge whose guard can only become true through an outside action, such as `refuse` when "the check reported red", is that outside party's edge. The code runs every cycle, but it gives the same answer until the party acts, so the state waits on the party. The checker prints a `guarded:` note on a state the system leaves only under guards, so you can look again.
- The actor's own process dying, a session that exits before it reports or a worker that crashes, is the actor's event, with the actor's kind. Nothing can rely on a crash, so the state stays a wait.

Another instance of the same process, a second order that must ship first or a later merge that carries this one's commit, is an actor of kind `external`, named for what it is, such as `later_merge`. Whoever owns that other instance owns the wait it ends. Write that person in `owner`, since the checker cannot see across instances. When the order or timing between instances is the question itself, the single-instance table is at its limit, and a model checker is the next tool.

An automated agent on a timer, a patrol or a bot session with a recipe, is `human` when it has to decide what to do, and `system` only when its step is mechanical and tested. Its waits need the same owner and timeout as a person's.

## Evidence

Every row carries `evidence`: a `path:line` or `path:start-end` for code, a `path#heading` for a document. One row can carry several. Evidence lets a reviewer check a row in thirty seconds, and lets the next agent regenerate the table after the code moves. A row with no evidence is a guess. Mark it `"evidence": "assumed"` and say so in the output, so the user can confirm or strike it.

## Done when

- Every value of the status type appears in the table, as a state or inside a composite state's note.
- Every writer of the status has a row, and the row's evidence points at the write.
- Every scheduler, timer, webhook and queue consumer that touches the status has a row.
- For every state, you can say who moves it on, from the table alone.
- Every incident you read is a path through the table, or you wrote down why it is not.
