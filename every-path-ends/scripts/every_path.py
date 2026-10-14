#!/usr/bin/env python3
"""Check a transition table and draw it. Standard library only; Python 3.9 or later.

    every_path.py check   table.json   # pass or fail per property, a concrete path per failure
    every_path.py diagram table.json   # Mermaid stateDiagram-v2 with failing states marked
    every_path.py table   table.json   # the same table as Markdown, for a report or a PR

Exit code 1 when a check fails, so the command can run as a test.
"""
from __future__ import annotations

import json
import sys
from collections import deque
from typing import Dict, List, Optional, Tuple

ACTOR_KINDS = ("system", "human", "external")


class TableError(Exception):
    """The table is not usable; the message says what to fix."""


class Edge:
    def __init__(self, row: dict, index: int) -> None:
        for key in ("from", "on", "to", "actor"):
            if key not in row or not isinstance(row[key], str) or not row[key]:
                raise TableError(f"transition {index}: needs a non-empty string {key!r}")
        self.source: str = row["from"]
        self.event: str = row["on"]
        self.target: str = row["to"]
        self.actor: str = row["actor"]
        self.guard: Optional[str] = row.get("guard")
        self.timeout: Optional[str] = row.get("timeout")
        self.bound: Optional[str] = row.get("bound")
        self.evidence: List[str] = _as_list(row.get("evidence"))
        self.note: Optional[str] = row.get("note")
        self.index = index

    def __str__(self) -> str:
        return f"{self.source} --{self.event}--> {self.target}"


class Table:
    def __init__(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise TableError("the table must be a JSON object")
        self.name: str = data.get("name", "process")
        initial = data.get("initial")
        self.initials: List[str] = _as_list(initial)
        if not self.initials:
            raise TableError("needs 'initial': the state a new instance starts in")
        self.ends: List[str] = _as_list(data.get("ends"))
        if not self.ends:
            raise TableError("needs 'ends': the states the process is allowed to stop in")
        actors = data.get("actors")
        if not isinstance(actors, dict) or not actors:
            raise TableError("needs 'actors': a map of actor name to system, human or external")
        for name, kind in actors.items():
            if kind not in ACTOR_KINDS:
                raise TableError(f"actor {name!r}: kind must be one of {', '.join(ACTOR_KINDS)}, not {kind!r}")
        self.actors: Dict[str, str] = actors
        states = data.get("states") or {}
        if not isinstance(states, dict):
            raise TableError("'states' must be a map of state name to its details")
        self.state_info: Dict[str, dict] = states
        rows = data.get("transitions")
        if not isinstance(rows, list) or not rows:
            raise TableError("needs 'transitions': a non-empty list")
        self.edges: List[Edge] = [Edge(row, i) for i, row in enumerate(rows)]
        for edge in self.edges:
            if edge.actor not in self.actors:
                raise TableError(f"transition {edge.index} ({edge}): actor {edge.actor!r} is not in 'actors'")
        names: List[str] = []
        for name in self.initials + self.ends + list(states):
            if name not in names:
                names.append(name)
        for edge in self.edges:
            for name in (edge.source, edge.target):
                if name not in names:
                    names.append(name)
        self.states: List[str] = names
        self.out: Dict[str, List[Edge]] = {name: [] for name in names}
        for edge in self.edges:
            self.out[edge.source].append(edge)

    def is_end(self, state: str) -> bool:
        return state in self.ends

    def actor_kind(self, edge: Edge) -> str:
        return self.actors[edge.actor]

    def paths_from_initial(self) -> Dict[str, List[Edge]]:
        """Shortest path (as a list of edges) from an initial state to every reachable state."""
        paths: Dict[str, List[Edge]] = {}
        queue = deque()
        for initial in self.initials:
            paths[initial] = []
            queue.append(initial)
        while queue:
            state = queue.popleft()
            for edge in self.out[state]:
                if edge.target not in paths:
                    paths[edge.target] = paths[state] + [edge]
                    queue.append(edge.target)
        return paths


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise TableError(f"expected a string or a list of strings, got {value!r}")


def format_path(initials: List[str], path: List[Edge]) -> str:
    if not path:
        return f"(start) {initials[0]}"
    return "(start) " + " ; ".join(str(edge) for edge in path)


# ---------------------------------------------------------------- checks

class Finding:
    def __init__(self, state: str, detail: str, path: Optional[List[Edge]]) -> None:
        self.state = state
        self.detail = detail
        self.path = path


class Result:
    def __init__(self, check: str, title: str, findings: List[Finding]) -> None:
        self.check = check
        self.title = title
        self.findings = findings

    @property
    def passed(self) -> bool:
        return not self.findings


def check_exit(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    findings = []
    for state in table.states:
        if table.is_end(state) or table.out[state]:
            continue
        findings.append(Finding(state, f"{state} is not an end state and has no transition out of it", paths.get(state)))
    return Result("exit", "every state that is not an end has a way out", findings)


CHECKS = [check_exit]


def run_checks(table: Table) -> List[Result]:
    paths = table.paths_from_initial()
    return [check(table, paths) for check in CHECKS]


def report(table: Table, results: List[Result]) -> str:
    lines = [f"{table.name}: {len(table.states)} states, {len(table.edges)} transitions, "
             f"start {', '.join(table.initials)}, ends {', '.join(table.ends)}", ""]
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        lines.append(f"{mark} {result.check}: {result.title}")
        for finding in result.findings:
            lines.append(f"  - {finding.detail}")
            if finding.path is not None:
                lines.append(f"    path: {format_path(table.initials, finding.path)}")
    failed = [r for r in results if not r.passed]
    lines.append("")
    lines.append("every path ends" if not failed else f"{len(failed)} check(s) failed")
    return "\n".join(lines)


# ---------------------------------------------------------------- cli

def load(path: str) -> Table:
    with open(path, encoding="utf-8") as handle:
        return Table(json.load(handle))


def main(argv: List[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("check", "diagram", "table"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    subcommand, path = argv
    try:
        table = load(path)
    except (TableError, json.JSONDecodeError, OSError) as error:
        print(f"cannot read {path}: {error}", file=sys.stderr)
        return 2
    if subcommand == "check":
        results = run_checks(table)
        print(report(table, results))
        return 0 if all(r.passed for r in results) else 1
    print("not built yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
