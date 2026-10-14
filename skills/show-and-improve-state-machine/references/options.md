# Ways to close a path

A failing path has more than one fix, and the right one is a product decision, not a graph decision. Offer several, mark how sure you are of each, and let the user pick.

## The card

One card per failing path, as an entry in the judgement file described in [report.md](report.md).

- **The path.** The checker's line, as printed, goes in `problem`, with the state and the edges from the start that reach it.
- **Two to four options.** Each one has a key, one sentence on what changes, and a strength badge. In the chat, add a before and after of the edges that change, as a Mermaid fragment or a `diff` of the table rows. On the page, the diagram above the cards carries that.
- **A pick.** The option you would take first, and why, in one line.

Badges. `Strong` when the code or a document already implies the fix, say a counter that exists but is not checked, or a runbook that names the owner. `Worth exploring` when it fits the process but the user has to confirm who or how long. `Speculative` when it changes what the process means.

## The menu, per failure

Work from this list, and add what the codebase suggests.

**A trap**, from `exit` or `can-end`. A state nothing can leave, or a region that never reaches an end.
- Declare it an end, if the process is honestly allowed to stop there. Then it needs nothing else, and the diagram says so.
- Add a retry edge back into the flow, with a `bound`, and a second edge for when the bound runs out.
- Add an escalation edge to a person, with an `owner` and a `timeout`.
- Merge it with a state that already has a way out, when the two differ only in history.

**A wait nobody owns**, from `waits-owned` with "no owner". Only an outside party can move it.
- Name the person inside the process who watches it, in `owner`, and check that something tells them, such as a queue, a digest or a nudge.
- Replace the outside party's action with a system poll that reads their state, so the mover becomes `system` and the wait disappears. Only if the poll really decides.

**A wait with no end**, from `waits-owned` with "no timeout".
- Add a timeout edge to a known end, such as `no_reply_7d` to `closed_no_reply`.
- Add a timeout edge that escalates to a state a different person owns, with its own timeout.
- Mark it `open_ended` with the reason, when a person reviews the queue on a schedule that is itself written down. This is a decision, not a fix, so say so. An automated reviewer on a schedule counts only when the step it takes is mechanical or tested. One that has to decide is a wait on that agent. Write `open_ended` as a map with `kind` and `evidence` when the reason rests on a recipe or a document rather than code, so the report can list which ends ride on an agent following words.

**A loop nothing counts**, from `loops-bounded`.
- Put a `bound` on the edge that re-enters the loop, backed by a counter the code keeps, and add the edge for when it runs out.
- Give the loop a budget in time rather than attempts, as a timeout on the state the loop waits in.
- Make the event illegal after the first time, so the second `refuse` goes to `abandoned`, not back to `refused`.

**An orphan**, from `reachable` or `ends-reachable`. A state or an end nothing leads to.
- Find the writer the search missed. Most orphans are a missing row, not a missing feature.
- Delete the state, when no writer exists and no document wants it.
- Add the edge the document promises, when the document is right and the code is behind.

**An end that leaks**, from `ends-closed`.
- Take it off `ends` and model what follows.
- Keep it as an end and put the leaking edge out of scope with a `note` that says why, a manual reopen by an operator, say. Only when the edge is truly outside the process.

## When nobody can answer

A worker run, a ticket, a subagent. Nobody picks a card. Write the pick and the order you would take them in, say that nobody was asked, and stop. The table, the judgement file and the page from `report` are the deliverables. Write them in the caller's folder, or beside the table when the caller said nothing.

## The page

The page is the script's, not yours. `report` writes the same HTML every run from the table and the judgement file, see [report.md](report.md). The cards live on the page. The chat message carries the path to the page and one line per failing path. Colour only what the checker marked, in its colours, red for a trap, amber for a wait, purple for a loop, grey for an orphan and blue for a leak, so the page and the terminal say the same thing.
