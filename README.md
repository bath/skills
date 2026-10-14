# show-and-improve-state-machine

An agent skill that models a process as a state machine, draws it, and proves that every path ends in a known end state, or lists the paths that do not.

The skill is in [`show-and-improve-state-machine/`](show-and-improve-state-machine/SKILL.md). Its checker is one Python file with no dependencies:

```
python3 show-and-improve-state-machine/scripts/every_path.py check show-and-improve-state-machine/examples/deploy.json
```

Tests:

```
python3 -m unittest discover -s tests
```

[`DECISIONS.md`](DECISIONS.md) lists the defaults picked to build the first version and how to reverse each one.
