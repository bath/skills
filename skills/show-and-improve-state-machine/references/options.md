# Ways to close a path

A failing path has more than one fix, and the right one is a product decision, not a graph decision. Offer several, mark how sure you are, and let the user pick.

## The card

One card per failing path, as an entry in the judgement file ([report.md](report.md)):

- **The path.** The checker's line, as printed, goes in `problem` with the state and the edges from the start that reach it.
- **Two to four options.** Each one has a key, one sentence on what changes, and a strength badge. In the chat, add a before/after of the edges that change (a Mermaid fragment or a `diff` of the table rows); on the page the diagram above the cards carries that.
- **A pick.** The option you would take first, and why, in one line.

Badges: `Strong` when the code or a document already implies the fix (a counter exists but is not checked, a runbook names the owner); `Worth exploring` when it fits the process but the user has to confirm who or how long; `Speculative` when it changes what the process means.

## The menu, per failure

Work from this list, and add what the codebase suggests.

**A trap** (`exit`, `can-end`): a state nothing can leave, or a region that never reaches an end.
- Declare it an end, if the process is honestly allowed to stop there. Then it needs nothing else, and the diagram says so.
- Add a retry edge back into the flow, with a `bound`, and a second edge for when the bound runs out.
- Add an escalation edge to a person, with an `owner` and a `timeout`.
- Merge it with a state that already has a way out, when the two differ only in history.

**A wait nobody owns** (`waits-owned`, "no owner"): only an outside party can move it.
- Name the person inside the process who watches it, in `owner`, and check that something tells them (a queue, a digest, a nudge).
- Replace the outside party's action with a system poll that reads their state, so the mover becomes `system` and the wait disappears; only if the poll really decides.

**A wait with no end** (`waits-owned`, "no timeout"):
- Add a timeout edge to a known end (`no_reply_7d` to `closed_no_reply`).
- Add a timeout edge that escalates (to a state a different person owns), with its own timeout.
- Mark it `open_ended` with the reason, when a person reviews the queue on a schedule that is itself written down. This is a decision, not a fix; say so. An automated reviewer on a schedule counts only when the step it takes is mechanical or tested; one that has to decide is a wait on that agent. Write `open_ended` as a map with `kind` and `evidence` when the reason rests on a recipe or a document rather than code, so the report can list which ends ride on an agent following words.

**A loop nothing counts** (`loops-bounded`):
- Put a `bound` on the edge that re-enters the loop, backed by a counter the code keeps, and add the edge for when it runs out.
- Give the loop a budget in time rather than attempts, as a timeout on the state the loop waits in.
- Make the event illegal after the first time (the second `refuse` goes to `abandoned`, not back to `refused`).

**An orphan** (`reachable`, `ends-reachable`): a state or an end nothing leads to.
- Find the writer the search missed; most orphans are a missing row, not a missing feature.
- Delete the state, when no writer exists and no document wants it.
- Add the edge the document promises, when the document is right and the code is behind.

**An end that leaks** (`ends-closed`):
- Take it off `ends` and model what follows.
- Keep it as an end and put the leaking edge out of scope with a `note` that says why (a manual reopen by an operator, say). Only when the edge is truly outside the process.

## When nobody can answer

A worker run, a ticket, a subagent: nobody picks a card. Write the pick and the order you would take them in, say that nobody was asked, and stop. The table, the judgement file and the page from `report` are the deliverables; write them in the caller's folder, or beside the table when the caller said nothing.

## The page

The page is the script's, not yours: `report` writes the same HTML every run from the table and the judgement file, see [report.md](report.md). The cards live on the page; the chat message carries the path to the page and one line per failing path. Colour only what the checker marked, in its colours (red trap, amber wait, purple loop, grey orphan, blue leak), so the page and the terminal say the same thing.
