# The report page

One self-contained HTML file, the same shape every run. The checker writes it at the end of every run:

```
python3 <skill dir>/scripts/every_path.py report process.json --judgement judgement.json --out report.html [--short-labels]
```

The script fills everything that comes from the table. The summary numbers. Each check with PASS or FAIL and a plain-words line. The diagram, with short labels on request, and with a timeout that three or more states share drawn once. The waits table, with state, waits on, owner told and timeout. The loop regions. A trust note on how many rows carry evidence. Without `--out` the page goes to standard output. The template is `assets/report.html`, and the only things it loads from outside are Mermaid and the fonts. It reads at phone width and follows the system's light or dark theme.

## The judgement file

The parts that need judgement are yours to write, in one JSON file. Every field is optional. A page with no judgement file still has the numbers, the checks, the diagram, the waits and the loops.

```json
{
  "title": "Order lifecycle check",
  "eyebrow": "first run",
  "lede": "One sentence on what was modelled and what the checks found.",
  "source": "Where the table came from and which commit, and who wrote the cards.",
  "seen": {
    "title": "The line you saw",
    "lines": ["Order #4411", "Paid", "Shipped, no scan for 9 days"],
    "state": "shipped",
    "text": ["What the model says about that line, in one or two short paragraphs."]
  },
  "waits": {
    "shipped": "Shipped, no scan yet",
    "awaiting_payment": "Payment pending"
  },
  "cards": [
    {
      "id": "F1",
      "title": "A lost parcel waits forever",
      "problem": "One sentence on what hurts, with the file:line when there is one.",
      "options": [
        {"key": "a", "text": "Refund after 14 days with no scan.", "strength": "Strong"},
        {"key": "b", "text": "Ask the carrier for a trace at day 7.", "strength": "Worth exploring"},
        {"key": "c", "text": "Make shipped an end.", "strength": "Speculative"}
      ],
      "pick": "a, then b",
      "picked": ["a", "b"]
    }
  ],
  "trust": ["One path is drawn from the code and not seen in practice: a parcel lost twice."]
}
```

| Field | Meaning |
|---|---|
| `title`, `eyebrow`, `lede`, `source` | the page's head. The script appends `eyebrow` to the skill's name. Left out, the script writes them from the table |
| `seen` | an example the reader met: the lines of a message or a row, the state it is in, and what the model says. The page draws `lines[0]` bold |
| `waits` | state name to what the reader sees in that state, such as "Refused (your card)". Given, the waits table gets a "What the reader sees" column, and a wait left out gets an empty cell |
| `cards` | one per failing path, in the order to read them. `strength` is `Strong`, `Worth exploring` or `Speculative`, as options.md defines them. `picked` lists the option keys to highlight, and `pick` is the line under the card |
| `trust` | notes on how far to trust the page: what was not seen in practice, what a hand check differed on. The script adds its own two lines first |

The script escapes text on the way in, so write plain sentences, not HTML.

## Where the page goes

In an interactive run, write the page to a temp directory from `mktemp -d`, open it with `open` on macOS or `xdg-open` on Linux, and say the path in the chat. In a worker run, write the judgement file beside the table, run `report` with `--out` into the caller's folder, and name the path in the reply. Either way the chat message is short: the path, then one line per path with no end.
