# skills

Agent skills by Miller Bath. One so far.

| Skill | What it does | Install |
|---|---|---|
| [show-and-improve-state-machine](skills/show-and-improve-state-machine/SKILL.md) | Models a process in a codebase or a document as a state machine, draws it, proves that every path ends in a known end state or lists the paths that do not, and offers ways to close each one. | `npx skills add bath/skills@show-and-improve-state-machine` |

Each skill lives under `skills/<name>/` with its `SKILL.md`, scripts, references and examples. The first skill's checker is one Python file with no dependencies:

```
python3 skills/show-and-improve-state-machine/scripts/every_path.py check skills/show-and-improve-state-machine/examples/deploy.json
```

The tests for every skill run from the root:

```
python3 -m unittest discover -s tests
```

[`DECISIONS.md`](DECISIONS.md) records the defaults each skill was built with and how to reverse them. The licence is MIT, see [`LICENSE`](LICENSE).
