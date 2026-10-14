# The transition table

One JSON file per process. JSON, because every language reads it with nothing installed, and the checker is standard-library Python.

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
| `name` | no | what the report calls the process |
| `initial` | yes | the state a new instance starts in. A list when there are several |
| `ends` | yes | the states the process is allowed to stop in |
| `actors` | yes | actor name to kind, one of `system`, `human` or `external`. The rule for choosing is in extraction.md |
| `states` | no | extra detail per state, below. A state named only here is an orphan unless an edge reaches it |
| `transitions` | yes | the rows |

## A state's details

| Field | Meaning |
|---|---|
| `owner` | the person the code tells when the state is entered, by a mail, a queue they read or a digest. That person is accountable for ending the wait. Left out, a `human` mover is the owner. Write `null` to say that nobody is told, whoever could act. Required when only `external` actors move the state |
| `open_ended` | a reason this wait may last with no timeout. The checker lists it as a note instead of failing. A string, or a map with `reason`, `kind` and `evidence`, where `kind` is `code`, `timer`, `recipe`, `schedule` or `document`. The report then shows what the reason rests on, a timer in code or an agent following words in a recipe |
| `note` | anything a reader needs, such as the field values that make up a composite state |

## A transition

| Field | Required | Meaning |
|---|---|---|
| `from` | yes | the state before |
| `on` | yes | the event, as a short name a log line could carry |
| `to` | yes | the state after |
| `actor` | yes | who causes the event, as a key of `actors` |
| `guard` | no | the condition that must hold, in words or in the code's own expression |
| `timeout` | no | the duration after which this edge fires on its own, such as `24h` or `7d`. It marks the edge as the state's way out when nobody acts |
| `bound` | no | the counter or budget that limits how often this edge fires, such as `attempts < 3`. One bounded edge per loop is enough |
| `evidence` | no, but write it | `path:line`, `path:start-end` or `path#heading`, as a string or a list |
| `note` | no | anything else |

The states are the names that appear in `initial`, `ends`, `states` and the rows. There is no separate list to keep in step.

## Names

Use the names the codebase uses when it has them, in snake_case so they survive Mermaid. When the code has no name for a composite state, invent one that says what the thing is waiting for or doing, and put the field values in `note`.
