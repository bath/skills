# The report page

One self-contained HTML file, the same shape every run, written by the checker:

```
python3 <skill dir>/scripts/every_path.py report process.json --judgement judgement.json --out report.html [--short-labels]
```

Everything that comes from the table is filled in by the script: the summary numbers, each check with PASS or FAIL and a plain-words line, the diagram (short labels on request; a timeout that three or more states share is drawn once), the waits table (state, waits on, owner told, timeout), the loop regions and a trust note on how many rows carry evidence. Without `--out` the page goes to standard output. The template is `assets/report.html`; the only things it loads from outside are Mermaid and the fonts. It reads at phone width and follows the system's light or dark theme.

## The judgement file

The parts that need judgement are yours to write, in one JSON file. Every field is optional; a page with no judgement file still has the numbers, the checks, the diagram, the waits and the loops.

```json
{
  "title": "Order lifecycle check",
  "eyebrow": "first run",
  "lede": "One sentence on what was modelled and what the checks found.",
  "source": "Where the table came from and which commit; who wrote the cards.",
  "seen": {
    "title": "The line you saw",
    "lines": ["Order #4411", "Paid", "Shipped, no scan for 9 days"],
    "state": "shipped",
    "text": ["What the model says about that line, in one or two short paragraphs."]
  },
  "cards": [
    {
      "id": "F1",
      "title": "A lost parcel waits for ever",
      "problem": "One sentence: what hurts, with the file:line when there is one.",
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
| `title`, `eyebrow`, `lede`, `source` | the page's head. `eyebrow` is appended to the skill's name. Left out, the script writes them from the table |
| `seen` | an example the reader met: the lines of a message or a row, the state it is in, and what the model says. `lines[0]` is drawn bold |
| `cards` | one per failing path, in the order to read them. `strength` is `Strong`, `Worth exploring` or `Speculative`, as options.md defines them. `picked` lists the option keys to highlight; `pick` is the line under the card |
| `trust` | notes on how far to trust the page: what was not seen in practice, what a hand check differed on. The script adds its own two lines first |

Text is escaped on the way in; write plain sentences, not HTML.

## In a worker run

Write the judgement file beside the table, run `report` with `--out` into the caller's folder, and name the path in the reply. Markdown is the chat view only: the diagram in a fence and one line per path with no end.
