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
    def __init__(self, check: str, title: str, findings: List[Finding], notes: Optional[List[str]] = None) -> None:
        self.check = check
        self.title = title
        self.findings = findings
        self.notes = notes or []

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


def check_reachable(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    findings = [Finding(s, f"{s} cannot be reached from the start; nothing leads to it", None)
                for s in table.states if s not in paths and not table.is_end(s)]
    return Result("reachable", "every state can be reached from the start", findings)


def check_ends_reachable(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    findings = [Finding(s, f"end state {s} cannot be reached from the start; nothing leads to it", None)
                for s in table.ends if s not in paths]
    return Result("ends-reachable", "every declared end can be reached from the start", findings)


def check_ends_closed(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    findings = []
    for state in table.ends:
        for edge in table.out[state]:
            findings.append(Finding(state, f"end state {state} has a way out: {edge}; an end that exits is not an end", paths.get(state)))
    return Result("ends-closed", "no declared end has a transition out of it", findings)


def can_reach_end(table: Table) -> set:
    """The states from which some end is still reachable (walk the edges backwards from the ends)."""
    into: Dict[str, List[str]] = {s: [] for s in table.states}
    for edge in table.edges:
        into[edge.target].append(edge.source)
    seen = set(table.ends)
    queue = deque(table.ends)
    while queue:
        state = queue.popleft()
        for source in into[state]:
            if source not in seen:
                seen.add(source)
                queue.append(source)
    return seen


def check_can_end(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    good = can_reach_end(table)
    findings = []
    for state in table.states:
        if state in good or state not in paths or not table.out[state]:
            continue  # a state with no exit is the exit check's finding, not a trap
        region = sorted(s for s in table.states if s not in good and s in paths and table.out[s])
        findings.append(Finding(state, f"{state} can be reached but no end can be reached from it; "
                                       f"it is trapped with {{{', '.join(region)}}}", paths[state]))
    return Result("can-end", "from every reachable state some end is still reachable", findings)


def is_waiting(table: Table, state: str) -> bool:
    """A state waits when the only things that move it on are a person or an outside system."""
    if table.is_end(state):
        return False
    movers = [edge for edge in table.out[state] if not edge.timeout]
    return bool(movers) and all(table.actor_kind(edge) != "system" for edge in movers)


def wait_owner(table: Table, state: str) -> Optional[str]:
    """Who is accountable for ending the wait: the state's declared owner, else a person inside the
    process whose action ends it. An outside party (external) cannot own a wait."""
    declared = table.state_info.get(state, {}).get("owner")
    if declared:
        return str(declared)
    humans = sorted({edge.actor for edge in table.out[state] if not edge.timeout and table.actor_kind(edge) == "human"})
    return ", ".join(humans) if humans else None


def check_waits_owned(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    findings = []
    notes = []
    for state in table.states:
        if state not in paths or not is_waiting(table, state):
            continue
        info = table.state_info.get(state, {})
        movers = [edge for edge in table.out[state] if not edge.timeout]
        waits_on = ", ".join(f"{actor} ({table.actors[actor]})" for actor in sorted({e.actor for e in movers}))
        missing = []
        if wait_owner(table, state) is None:
            missing.append("no owner")
        if not any(edge.timeout for edge in table.out[state]):
            if info.get("open_ended"):
                notes.append(f"open-ended: {state} waits on {waits_on} with no timeout because {info['open_ended']}")
            else:
                missing.append("no timeout")
        if missing:
            findings.append(Finding(state, f"{state} waits on {waits_on} and has {' and '.join(missing)}", paths[state]))
    return Result("waits-owned", "every wait names who ends it and has a timeout out of it", findings, notes)


def find_cycle(table: Table, skip_bounded: bool) -> Optional[List[Edge]]:
    """One cycle through states that are not ends, ignoring bounded edges; None when there is none."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {s: WHITE for s in table.states}
    stack: List[Edge] = []

    def visit(state: str) -> Optional[List[Edge]]:
        colour[state] = GREY
        for edge in table.out[state]:
            if table.is_end(edge.target) or (skip_bounded and edge.bound):
                continue
            if colour[edge.target] == GREY:
                # The target is on the current path: the cycle is the path from it, plus this edge.
                # No edge on the path starts at the target only for a self-loop.
                start = len(stack)
                for i, on_path in enumerate(stack):
                    if on_path.source == edge.target:
                        start = i
                        break
                return stack[start:] + [edge]
            if colour[edge.target] == WHITE:
                stack.append(edge)
                found = visit(edge.target)
                if found:
                    return found
                stack.pop()
        colour[state] = BLACK
        return None

    for state in table.states:
        if colour[state] == WHITE and not table.is_end(state):
            found = visit(state)
            if found:
                return found
    return None


def check_loops_bounded(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    cycle = find_cycle(table, skip_bounded=True)
    findings = []
    if cycle:
        first = cycle[0].source
        loop = " ; ".join(str(edge) for edge in cycle)
        findings.append(Finding(first, f"a loop with no bounded edge: {loop}; nothing counts the attempts, so it can go round for ever", paths.get(first)))
    return Result("loops-bounded", "every loop that avoids the ends has an edge with a bound", findings)


CHECKS = [check_reachable, check_ends_reachable, check_ends_closed, check_exit, check_can_end, check_waits_owned, check_loops_bounded]


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
        for note in result.notes:
            lines.append(f"  note {note}")
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
