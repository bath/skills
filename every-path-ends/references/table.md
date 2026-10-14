# The transition table

One JSON file per process. JSON because every language reads it with no extra install, and because the checker is standard-library Python.

```json
{
  "name": "order",
  "initial": "placed",
  "ends": ["delivered", "cancelled", "refunded"],
  "actors": {"system": "system", "shop": "human", "customer": "external", "carrier": "external"},
  "states": {
    "placed": {"owner": "shop", "note": "the customer has not paid yet"}
  },
  "transitions": [
    {"from": "placed", "on": "pay", "to": "paid", "actor": "customer", "evidence": "src/orders.ts:40"},
    {"from": "placed", "on": "unpaid_24h", "to": "cancelled", "actor": "system", "timeout": "24h", "evidence": "src/jobs/expire.ts:12"},
    {"from": "shipped", "on": "lost", "to": "paid", "actor": "carrier", "bound": "reships < 2", "evidence": "src/webhooks/carrier.ts:44"}
  ]
}
```

## Top level

| Field | Required | Meaning |
|---|---|---|
| `name` | no | what the process is called in the report |
| `initial` | yes | the state a new instance starts in; a list when there are several |
| `ends` | yes | the states the process is allowed to stop in |
| `actors` | yes | actor name to kind: `system`, `human` or `external` (see extraction.md for the rule) |
| `states` | no | extra detail per state (below); a state named only here is an orphan unless an edge reaches it |
| `transitions` | yes | the rows |

## A state's details

| Field | Meaning |
|---|---|
| `owner` | the person the code tells when the state is entered (a mail, a queue they read, a digest), who is then accountable for ending the wait. Left out, a `human` mover is taken as the owner; write `null` to say that nobody is told, whoever could act. Needed when only `external` actors move it |
| `open_ended` | a reason this wait may last with no timeout; the checker lists it as a note instead of failing |
| `note` | anything a reader needs, such as the field values that make up a composite state |

## A transition

| Field | Required | Meaning |
|---|---|---|
| `from` | yes | the state before |
| `on` | yes | the event; a short name a log line could carry |
| `to` | yes | the state after |
| `actor` | yes | who causes the event; a key of `actors` |
| `guard` | no | the condition that must hold, in words or in the code's own expression |
| `timeout` | no | the duration after which this edge fires on its own (`24h`, `7d`); marks the edge as the state's way out when nobody acts |
| `bound` | no | the counter or budget that limits how often this edge fires (`attempts < 3`); one bounded edge per loop is enough |
| `evidence` | no, but write it | `path:line`, `path:start-end` or `path#heading`; a string or a list |
| `note` | no | anything else |

States are named by their appearance in `initial`, `ends`, `states` and the rows; there is no separate list to keep in step.

## Names

Use the names the codebase uses when it has them, in snake_case so they survive Mermaid. When the code has no name for a composite state, invent one that says what the thing is waiting for or doing, and put the field values in `note`.
