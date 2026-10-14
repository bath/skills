#!/usr/bin/env python3
"""Check a transition table and draw it. Standard library only; Python 3.9 or later.

    every_path.py check   table.json [--json]             # pass or fail per property, a concrete path per failure
    every_path.py diagram table.json [--short-labels] [--shared-timeouts]
                                                          # Mermaid stateDiagram-v2 with failing states marked
    every_path.py table   table.json                      # the same table as Markdown, for a report or a PR
    every_path.py report  table.json [--judgement j.json] [--out page.html] [--short-labels]
                                                          # one self-contained HTML page, the same every run

Exit code 1 when a check fails (check only), 2 when a file cannot be read.
"""
from __future__ import annotations

import html
import json
import os
import sys
from collections import deque
from typing import Dict, List, Optional, Tuple

ACTOR_KINDS = ("system", "human", "external")
# What an open-ended wait's reason rests on: code or a timer the kernel runs, a recipe an agent follows,
# a schedule a person keeps, or a document that says so.
EVIDENCE_KINDS = ("code", "timer", "recipe", "schedule", "document")


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
        for name, info in states.items():
            if not isinstance(info, dict):
                raise TableError(f"state {name!r}: details must be a map")
            open_ended = info.get("open_ended")
            if isinstance(open_ended, dict):
                if not open_ended.get("reason"):
                    raise TableError(f"state {name!r}: open_ended needs a 'reason'")
                kind = open_ended.get("kind")
                if kind is not None and kind not in EVIDENCE_KINDS:
                    raise TableError(f"state {name!r}: open_ended kind must be one of {', '.join(EVIDENCE_KINDS)}, not {kind!r}")
            elif open_ended is not None and not isinstance(open_ended, str):
                raise TableError(f"state {name!r}: open_ended is a reason, or a map with reason, kind and evidence")
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
    def __init__(self, check: str, title: str, findings: List[Finding], notes: Optional[List[str]] = None,
                 summary: Optional[str] = None) -> None:
        self.check = check
        self.title = title
        self.findings = findings
        self.notes = notes or []
        self.summary = summary or f"{len(findings)} state(s)"

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
    return Result("reachable", "every state that is not an end can be reached from the start", findings)


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
        if state in good or state not in paths:
            continue
        # A state with no exit is also the exit check's finding; it is listed here too, so that a
        # PASS on this check means no reachable state is trapped, exits or not.
        region = sorted(s for s in table.states if s not in good and s in paths)
        findings.append(Finding(state, f"{state} can be reached but no end can be reached from it; "
                                       f"it is trapped with {{{', '.join(region)}}}", paths[state]))
    return Result("can-end", "from every reachable state some end is still reachable", findings)


def is_waiting(table: Table, state: str) -> bool:
    """A state waits when the only things that move it on are a person or an outside system."""
    if table.is_end(state):
        return False
    movers = [edge for edge in table.out[state] if not edge.timeout]
    return bool(movers) and all(table.actor_kind(edge) != "system" for edge in movers)


def open_ended_text(info: dict) -> Optional[str]:
    """The reason a wait may last, with what kind of evidence it rests on; None when the state is not open-ended."""
    value = info.get("open_ended")
    if not value:
        return None
    if isinstance(value, str):
        return f"open-ended: {value}"
    tag = ", ".join(str(v) for v in (value.get("kind"), value.get("evidence")) if v)
    return f"open-ended ({tag}): {value['reason']}" if tag else f"open-ended: {value['reason']}"


def wait_owner(table: Table, state: str) -> Optional[str]:
    """Who is accountable for ending the wait: the state's declared owner, else a person inside the
    process whose action ends it. An outside party (external) cannot own a wait."""
    info = table.state_info.get(state, {})
    if "owner" in info:
        # Declared: a name, or null to say that nobody is told, whoever could act.
        return str(info["owner"]) if info["owner"] else None
    humans = sorted({edge.actor for edge in table.out[state] if not edge.timeout and table.actor_kind(edge) == "human"})
    return ", ".join(humans) if humans else None


def check_waits_owned(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    findings = []
    notes = []
    good = can_reach_end(table)
    for state in table.states:
        if state not in paths or table.is_end(state):
            continue
        if not is_waiting(table, state):
            system_exits = [e for e in table.out[state] if not e.timeout and table.actor_kind(e) == "system"]
            if system_exits and all(e.guard for e in system_exits):
                guards = "; ".join(f"{e.event} [{e.guard}]" for e in system_exits)
                notes.append(f"guarded: {state} is moved by the system only under a guard ({guards}); "
                             f"if a guard needs an outside party to act, that party is the actor and the state is a wait")
            continue
        info = table.state_info.get(state, {})
        movers = [edge for edge in table.out[state] if not edge.timeout]
        waits_on = ", ".join(f"{actor} ({table.actors[actor]})" for actor in sorted({e.actor for e in movers}))
        missing = []
        if wait_owner(table, state) is None:
            missing.append("no owner")
        timeouts = [edge for edge in table.out[state] if edge.timeout]
        if not any(edge.target in good for edge in timeouts):
            if info.get("open_ended"):
                label, reason = open_ended_text(info).split(": ", 1)
                notes.append(f"{label}: {state} waits on {waits_on} with no timeout because {reason}")
            elif timeouts:
                # A timer that ends the wait in a trap ends nothing: name it, so the finding is not "add a timeout".
                dead = ", ".join(f"{e.event} leads to {e.target}" for e in timeouts)
                missing.append(f"no timeout that reaches an end ({dead}, from which no end can be reached)")
            else:
                missing.append("no timeout")
        if missing:
            findings.append(Finding(state, f"{state} waits on {waits_on} and has {' and '.join(missing)}", paths[state]))
    no_owner = sum(1 for f in findings if "no owner" in f.detail)
    no_timeout = sum(1 for f in findings if "no timeout" in f.detail)
    summary = f"{len(findings)} waits: {no_owner} with no owner, {no_timeout} with no timeout"
    return Result("waits-owned", "every reachable wait has an owner and a timeout that reaches an end, "
                  "or a written reason to be open-ended", findings, notes, summary)


def strongly_connected(table: Table, nodes: List[str], edges: List[Edge]) -> List[List[str]]:
    """Tarjan's components over `nodes` with `edges`, each in the order the states were named."""
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    on_stack = set()
    stack: List[str] = []
    out: Dict[str, List[str]] = {n: [] for n in nodes}
    for edge in edges:
        out[edge.source].append(edge.target)
    components: List[List[str]] = []
    counter = [0]

    def visit(node: str) -> None:
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in out[node]:
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            component = []
            while True:
                top = stack.pop()
                on_stack.discard(top)
                component.append(top)
                if top == node:
                    break
            components.append(sorted(component, key=nodes.index))

    for node in nodes:
        if node not in index:
            visit(node)
    return components


def example_cycle(nodes: List[str], edges: List[Edge]) -> List[Edge]:
    """One cycle inside a component: a depth-first walk from its first state back to a state on the path."""
    out: Dict[str, List[Edge]] = {n: [] for n in nodes}
    for edge in edges:
        out[edge.source].append(edge)
    path: List[Edge] = []
    seen = set()

    def walk(node: str) -> Optional[List[Edge]]:
        seen.add(node)
        for edge in out[node]:
            on_path = [i for i, e in enumerate(path) if e.source == edge.target]
            if edge.target == node:
                return [edge]
            if on_path:
                return path[on_path[0]:] + [edge]
            if edge.target not in seen:
                path.append(edge)
                found = walk(edge.target)
                if found:
                    return found
                path.pop()
        return None

    return walk(nodes[0]) or []


def closing_edges(nodes: List[str], edges: List[Edge]) -> List[Edge]:
    """The edges a depth-first walk of the region finds pointing back onto its own path. Every cycle in
    the region goes through at least one of them, so a bound on each breaks every loop."""
    out: Dict[str, List[Edge]] = {n: [] for n in nodes}
    for edge in edges:
        out[edge.source].append(edge)
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in nodes}
    back: List[Edge] = []

    def walk(node: str) -> None:
        colour[node] = GREY
        for edge in out[node]:
            if colour[edge.target] == GREY:
                back.append(edge)
            elif colour[edge.target] == WHITE:
                walk(edge.target)
        colour[node] = BLACK

    for node in nodes:
        if colour[node] == WHITE:
            walk(node)
    return back


def check_loops_bounded(table: Table, paths: Dict[str, List[Edge]]) -> Result:
    nodes = [s for s in table.states if not table.is_end(s)]
    edges = [e for e in table.edges if not e.bound and e.source in nodes and e.target in nodes]
    findings = []
    for component in strongly_connected(table, nodes, edges):
        inside = [e for e in edges if e.source in component and e.target in component]
        if not inside:
            continue  # one state with no self-loop
        cycle = example_cycle(component, inside)
        first = cycle[0].source if cycle else component[0]
        loop = " ; ".join(str(edge) for edge in cycle)
        closing = " ; ".join(str(edge) for edge in closing_edges(component, inside))
        findings.append(Finding(first, f"a loop with no bounded edge through region {{{', '.join(component)}}}: {loop}; "
                                       f"nothing counts the attempts, so it can go round for ever; closing edges: {closing}", paths.get(first)))
    return Result("loops-bounded", "every loop that avoids the ends has an edge with a bound", findings,
                  summary=f"{len(findings)} loop region(s)")


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
        if not result.passed:
            lines.append(f"  {result.summary}")
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


def edge_json(edge: Edge) -> dict:
    return {"from": edge.source, "on": edge.event, "to": edge.target, "actor": edge.actor,
            "guard": edge.guard, "timeout": edge.timeout, "bound": edge.bound, "evidence": edge.evidence}


def results_json(table: Table, results: List[Result]) -> dict:
    return {
        "name": table.name,
        "passed": all(r.passed for r in results),
        "results": [{
            "check": r.check, "title": r.title, "passed": r.passed, "notes": r.notes,
            "findings": [{"state": f.state, "detail": f.detail,
                          "path": None if f.path is None else [edge_json(e) for e in f.path]} for f in r.findings],
        } for r in results],
    }


# ---------------------------------------------------------------- diagram and table

# How a failing state is drawn: the check that found it, and the class that colours it.
MARKS = [("exit", "trap"), ("can-end", "trap"), ("waits-owned", "wait"), ("loops-bounded", "loop"), ("reachable", "orphan"), ("ends-closed", "leak")]
STYLES = {
    "trap": "fill:#f8d7da,stroke:#b02a37,color:#000",
    "wait": "fill:#fff3cd,stroke:#997404,color:#000",
    "loop": "fill:#e2d9f3,stroke:#59359a,color:#000",
    "orphan": "fill:#e9ecef,stroke:#6c757d,color:#000,stroke-dasharray: 4 4",
    "leak": "fill:#cfe2ff,stroke:#084298,color:#000",
}


def safe_label(text: str) -> str:
    """Transition text Mermaid reads as one label: no statement separators, no second colon, one line."""
    return " ".join(text.replace(";", ",").replace(":", ".").replace('"', "'").split())


def mermaid_id(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    return cleaned if cleaned and not cleaned[0].isdigit() else f"s_{cleaned}"


SHARED_TIMEOUT_MIN = 3


def shared_timeouts(table: Table) -> Dict[int, Tuple[str, List[str], str]]:
    """Timeout edges that three or more states share (same event, target and timeout), as edge index
    to (target, sources, timeout). Drawn once, they keep a busy diagram readable."""
    groups: Dict[Tuple[str, str, str], List[Edge]] = {}
    for edge in table.edges:
        if edge.timeout:
            groups.setdefault((edge.event, edge.target, edge.timeout), []).append(edge)
    shared = {}
    for (event, target, timeout), edges in groups.items():
        if len(edges) >= SHARED_TIMEOUT_MIN:
            for edge in edges:
                shared[edge.index] = (target, [e.source for e in edges], timeout)
    return shared


def diagram(table: Table, results: List[Result], short_labels: bool = False, fold_timeouts: bool = False) -> str:
    lines = ["stateDiagram-v2"]
    ids = {name: mermaid_id(name) for name in table.states}
    display = {name: name for name in table.states}
    shared = shared_timeouts(table) if fold_timeouts else {}
    drawn_shared = set()
    for target, sources, timeout in shared.values():
        origin = ", ".join(sources) if len(sources) <= 4 else f"{len(sources)} states"
        display[target] = f"{target} (from {origin}, after {timeout})"
    for name, ident in ids.items():
        if display[name] != ident:
            lines.append(f'    state "{safe_label(display[name])}" as {ident}')
    for initial in table.initials:
        lines.append(f"    [*] --> {ids[initial]}")
    for edge in table.edges:
        if edge.index in shared:
            key = (edge.event, edge.target, edge.timeout)
            if key in drawn_shared:
                continue
            drawn_shared.add(key)
        if short_labels:
            label = edge.event
        else:
            label = f"{edge.event} / {edge.actor}"
            if edge.timeout:
                label += f", after {edge.timeout}"
            if edge.guard:
                label += f" [{edge.guard}]"
            if edge.bound:
                label += f" ({edge.bound})"
        lines.append(f"    {ids[edge.source]} --> {ids[edge.target]} : {safe_label(label)}")
    for end in table.ends:
        lines.append(f"    {ids[end]} --> [*]")
    marked = marks(results)
    if marked:
        lines.append("")
        for style in sorted(set(marked.values())):
            lines.append(f"    classDef {style} {STYLES[style]}")
        for name, style in marked.items():
            lines.append(f"    class {ids[name]} {style}")
        lines.append("    %% " + "; ".join(LEGEND[s] for s in sorted(set(marked.values()))))
    return "\n".join(lines)


LEGEND = {"trap": "red: no end can follow", "wait": "amber: a wait with no owner or no timeout",
          "loop": "purple: starts a loop nothing bounds", "orphan": "grey: nothing leads here", "leak": "blue: an end with a way out"}


def marks(results: List[Result]) -> Dict[str, str]:
    """State to the class that colours it, the first mark in MARKS order winning."""
    marked: Dict[str, str] = {}
    by_check = {r.check: r for r in results}
    for check, style in MARKS:
        for finding in by_check[check].findings:
            marked.setdefault(finding.state, style)
    return marked


def markdown_table(table: Table) -> str:
    def cell(value) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return "; ".join(value)
        return str(value).replace("|", "\\|")
    lines = [f"**{table.name}**: starts in {', '.join(table.initials)}; ends in {', '.join(table.ends)}.", "",
             "| From | Event | To | Actor | Guard | Timeout | Bound | Evidence |", "|---|---|---|---|---|---|---|---|"]
    for edge in table.edges:
        lines.append("| " + " | ".join(cell(v) for v in (edge.source, edge.event, edge.target, edge.actor, edge.guard,
                                                        edge.timeout, edge.bound, edge.evidence)) + " |")
    waits = [s for s in table.states if is_waiting(table, s)]
    if waits:
        lines += ["", "| Wait | Owner | Timeout |", "|---|---|---|"]
        for state in waits:
            timeouts = ", ".join(f"{e.event} after {e.timeout}" for e in table.out[state] if e.timeout)
            info = table.state_info.get(state, {})
            if not timeouts and info.get("open_ended"):
                timeouts = open_ended_text(info)
            lines.append(f"| {state} | {cell(wait_owner(table, state))} | {cell(timeouts)} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- report

STRENGTHS = {"Strong": "s", "Worth exploring": "w", "Speculative": "x"}
SKILL_NAME = "show-and-improve-state-machine"
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "report.html")


class JudgementError(Exception):
    """The judgement file is not usable; the message says what to fix."""


def load_judgement(path: Optional[str]) -> dict:
    if path is None:
        return {}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise JudgementError("the judgement must be a JSON object")
    for card in data.get("cards") or []:
        for key in ("id", "title", "problem", "options"):
            if key not in card:
                raise JudgementError(f"card {card.get('id', '?')}: needs {key!r}")
        for option in card["options"]:
            for key in ("key", "text", "strength"):
                if key not in option:
                    raise JudgementError(f"card {card['id']} option {option.get('key', '?')}: needs {key!r}")
            if option["strength"] not in STRENGTHS:
                raise JudgementError(f"card {card['id']} option {option['key']}: strength must be one of "
                                     f"{', '.join(STRENGTHS)}, not {option['strength']!r}")
    seen = data.get("seen")
    if seen is not None and not isinstance(seen, dict):
        raise JudgementError("'seen' must be an object with title, lines, state and text")
    return data


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def chip(state: str, marked: Dict[str, str], table: Table) -> str:
    cls = {"trap": "t", "wait": "w", "loop": "l", "orphan": "o", "leak": "e"}.get(marked.get(state, ""), "")
    if not cls and table.is_end(state):
        cls = "e"
    return f'<span class="st {cls}">{esc(state)}</span>' if cls else f"<code>{esc(state)}</code>"


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def plain_words(table: Table, result: Result, marked: Dict[str, str]) -> str:
    """One sentence per check that a reader with no graph vocabulary can follow."""
    chips = lambda states: ", ".join(chip(s, marked, table) for s in states)  # noqa: E731
    states = [f.state for f in result.findings]
    n = len(states)
    if result.check == "reachable":
        return (f"Every state that is not an end can be reached from {esc(', '.join(table.initials))}." if result.passed
                else f"Nothing leads to {chips(states)}.")
    if result.check == "ends-reachable":
        return (f"Each of the {len(table.ends)} ends can happen." if result.passed
                else f"{chips(states)} {plural(n, 'is', 'are')} declared an end and can never happen.")
    if result.check == "ends-closed":
        return ("No end moves on again." if result.passed
                else f"{chips(states)} {plural(n, 'moves', 'move')} on again, so {plural(n, 'it is', 'they are')} not an end.")
    if result.check == "exit":
        return ("Every state that is not an end has a way out." if result.passed
                else f"{chips(states)} {plural(n, 'is', 'are')} not an end and {plural(n, 'has', 'have')} no way out.")
    if result.check == "can-end":
        return ("From every reachable state, an end can still follow." if result.passed
                else f"From {chips(states)}, no end can follow: a trap.")
    if result.check == "waits-owned":
        if result.passed:
            return "Every wait has an owner who is told and a timeout that leads to an end, or a written reason to be open-ended."
        no_timeout = sum(1 for f in result.findings if "no timeout" in f.detail)
        no_owner = sum(1 for f in result.findings if "no owner" in f.detail)
        return (f"{n} {plural(n, 'state waits', 'states wait')} on someone. {no_timeout} {plural(no_timeout, 'has', 'have')} no timeout "
                f"that leads to an end, and {no_owner} {plural(no_owner, 'has', 'have')} no owner who is told.")
    if result.check == "loops-bounded":
        if result.passed:
            return "Every loop that avoids the ends has a bound."
        sizes = [len(region_states(f)) for f in result.findings]
        if n == 1:
            return f"1 loop region covers {sizes[0]} states. Nothing counts the rounds."
        return f"{n} loop regions cover {', '.join(str(x) for x in sizes)} states. Nothing counts the rounds."
    return result.title


def region_states(finding: Finding) -> List[str]:
    """The states of a loop region, read back from the finding's own text."""
    inside = finding.detail.split("region {", 1)[1].split("}", 1)[0]
    return [x.strip() for x in inside.split(",") if x.strip()]


def wait_rows(table: Table, results: List[Result], marked: Dict[str, str]) -> str:
    good = can_reach_end(table)
    rows = []
    for finding in next(r for r in results if r.check == "waits-owned").findings:
        state = finding.state
        movers = sorted({e.actor for e in table.out[state] if not e.timeout})
        owner = wait_owner(table, state)
        timeouts = [e for e in table.out[state] if e.timeout]
        live = [e for e in timeouts if e.target in good]
        if live:
            timeout = esc(", ".join(f"{e.event} after {e.timeout}" for e in live))
            timeout_cell = f"<td>{timeout}</td>"
        elif timeouts:
            dead = esc(", ".join(f"{e.event} after {e.timeout}, into a trap" for e in timeouts))
            timeout_cell = f'<td class="no">{dead}</td>'
        else:
            timeout_cell = '<td class="no">none</td>'
        owner_cell = f"<td>{esc(owner)}</td>" if owner else '<td class="no">no</td>'
        rows.append(f"<tr><td>{chip(state, marked, table)}</td><td>{esc(', '.join(movers))}</td>{owner_cell}{timeout_cell}</tr>")
    return "\n      ".join(rows)


def loops_section(table: Table, results: List[Result], marked: Dict[str, str]) -> str:
    result = next(r for r in results if r.check == "loops-bounded")
    if result.passed:
        return ""
    blocks = []
    for finding in result.findings:
        states = region_states(finding)
        cycle = finding.detail.split("}: ", 1)[1].split("; nothing counts", 1)[0]
        closing = finding.detail.split("closing edges: ", 1)[1] if "closing edges: " in finding.detail else ""
        blocks.append(
            f'<div class="region"><div>{len(states)} states: {" ".join(chip(x, marked, table) for x in states)}</div>'
            f"<div>Example: <code>{esc(cycle)}</code></div>"
            f'<div class="edges">closing edges (a bound on each breaks every loop here): {esc(closing)}</div></div>')
    return ('<section>\n  <h2>Loops nothing counts</h2>\n  <p>A loop that avoids every end goes round until something counts the rounds. '
            'Each region below is one such loop, with the edges that close it.</p>\n  <div class="regions">' + "".join(blocks) + "</div>\n</section>")


def seen_section(seen: Optional[dict], marked: Dict[str, str], table: Table) -> str:
    if not seen:
        return ""
    lines = [esc(x) for x in seen.get("lines") or []]
    bubble = ""
    if lines:
        bubble = '<div class="bubble"><span class="t">' + lines[0] + "</span>" + "".join(f"<span>{x}</span>" for x in lines[1:]) + "</div>"
    paras = []
    if seen.get("state"):
        paras.append(f"<p>In the model, this is {chip(seen['state'], marked, table)}.</p>")
    paras += [f"<p>{esc(x)}</p>" for x in seen.get("text") or []]
    return (f'<section>\n  <h2>{esc(seen.get("title") or "What the reader saw")}</h2>\n  <div class="chatrow">\n    {bubble}\n'
            f'    <div style="display:grid;gap:10px">{"".join(paras)}</div>\n  </div>\n</section>')


def cards_section(cards: List[dict]) -> str:
    if not cards:
        return ""
    articles = []
    for card in cards:
        picked = set(card.get("picked") or [])
        items = []
        for option in card["options"]:
            cls = ' class="pick"' if option["key"] in picked else ""
            items.append(f'<li{cls}><span class="k">{esc(option["key"])}</span><span>{esc(option["text"])}</span>'
                         f'<span class="badge {STRENGTHS[option["strength"]]}">{esc(option["strength"])}</span></li>')
        pick = f'<p class="pickline">Pick: <b>{esc(card["pick"])}</b></p>' if card.get("pick") else ""
        articles.append(f'<article class="card"><header><span class="id">{esc(card["id"])}</span><h3>{esc(card["title"])}</h3></header>'
                        f'<p>{esc(card["problem"])}</p><ul class="opts">{"".join(items)}</ul>{pick}</article>')
    return ('<section>\n  <h2>Ways to close each gap</h2>\n  <p>For each failing path, several fixes, each with a strength. Strong means the code or a '
            'document already points to it. Worth exploring means someone must confirm who acts or how long to wait. Speculative changes what the '
            'process means. The highlighted line is the pick. Nothing is changed yet.</p>\n  <div class="cards">\n' + "\n".join(articles) + "\n  </div>\n</section>")


def build_report(table: Table, results: List[Result], judgement: dict, short_labels: bool) -> str:
    with open(TEMPLATE, encoding="utf-8") as handle:
        template = handle.read()
    marked = marks(results)
    failed = [r for r in results if not r.passed]
    waits = next(r for r in results if r.check == "waits-owned").findings
    checks = "\n".join(
        f'    <div class="chk"><span class="tag {"p" if r.passed else "f"}">{"PASS" if r.passed else "FAIL"}</span>'
        f'<div><span class="n">{r.check}</span><p>{plain_words(table, r, marked)}</p></div></div>' for r in results)
    legend = {"wait": ('w', "a wait with no owner or no timeout"), "trap": ('t', "a trap: no end can follow"),
              "loop": ('l', "where a loop that nothing counts starts"), "orphan": ('o', "nothing leads here"), "leak": ('e', "an end with a way out")}
    legend_html = " ".join(f'<span><span class="st {legend[m][0]}">{ {"w": "amber", "t": "red", "l": "purple", "o": "grey", "e": "blue"}[legend[m][0]] }</span> {legend[m][1]}</span>'
                           for m in ("wait", "trap", "loop", "orphan", "leak") if m in set(marked.values()))
    shared = shared_timeouts(table)
    note = "The checker draws this from the same table it checks."
    if short_labels:
        note += " Labels show the event only; the full diagram also carries the actor, the guard and the bound."
    if shared:
        target, sources, timeout = next(iter(shared.values()))
        note += f" After {esc(timeout)}, {len(sources)} states go to {esc(target)}; one arrow stands for all of them here."
    with_evidence = sum(1 for e in table.edges if e.evidence and e.evidence != ["assumed"])
    trust = [f"The table is a reading of the code. {with_evidence} of {len(table.edges)} rows name a file:line, so each one can be checked.",
             "The checks are the machine's: every number and line above the cards comes from the table alone."]
    trust += [esc(x) for x in judgement.get("trust") or []]
    waits_html = ""
    if waits:
        waits_html = (f'<section>\n  <h2>The {len(waits)} {plural(len(waits), "wait", "waits")}</h2>\n  <p>Each state waits on a person or an outside system. '
                      'Owner told is who the code tells when the state is entered. Timeout is the way out when nobody acts.</p>\n  <div class="tbl"><table>\n'
                      '    <thead><tr><th>State</th><th>Waits on</th><th>Owner told</th><th>Timeout</th></tr></thead>\n    <tbody>\n      '
                      + wait_rows(table, results, marked) + "\n    </tbody>\n  </table></div>\n</section>")
    title = judgement.get("title") or table.name
    verdict = f"{len(failed)} of {len(results)} checks fail." if failed else "Every path ends."
    default_lede = f"The {table.name} process as one table of states and transitions, drawn and checked. {verdict}"
    fields = {
        "title": esc(title),
        "description": esc(judgement.get("lede") or f"Every path of {table.name}, checked."),
        "eyebrow": esc(f"{SKILL_NAME} · {judgement['eyebrow']}" if judgement.get("eyebrow") else f"{SKILL_NAME} · report"),
        "lede": esc(judgement.get("lede") or default_lede),
        "source": esc(judgement.get("source") or f"Model: {len(table.states)} states and {len(table.edges)} transitions from the table. Checks: the checker that drew this page."),
        "n_states": str(len(table.states)), "n_transitions": str(len(table.edges)), "n_ends": str(len(table.ends)),
        "n_failed": str(len(failed)), "n_checks": str(len(results)), "failed_class": "bad" if failed else "",
        "n_waits": str(len(waits)), "waits_class": "bad" if waits else "",
        "seen_section": seen_section(judgement.get("seen"), marked, table),
        "checks": checks,
        "diagram_note": note,
        "legend": legend_html,
        "diagram": diagram(table, results, short_labels=short_labels, fold_timeouts=True),
        "waits_section": waits_html,
        "loops_section": loops_section(table, results, marked),
        "cards_section": cards_section(judgement.get("cards") or []),
        "trust": "".join(f"<li>{x}</li>" for x in trust),
    }
    page = template
    for key, value in fields.items():
        page = page.replace("{{" + key + "}}", value)
    return page


# ---------------------------------------------------------------- cli

def load(path: str) -> Table:
    with open(path, encoding="utf-8") as handle:
        return Table(json.load(handle))


def take_flag(argv: List[str], flag: str) -> bool:
    if flag in argv:
        argv.remove(flag)
        return True
    return False


def take_value(argv: List[str], flag: str) -> Optional[str]:
    if flag not in argv:
        return None
    at = argv.index(flag)
    if at + 1 >= len(argv):
        raise TableError(f"{flag} needs a value")
    value = argv[at + 1]
    del argv[at:at + 2]
    return value


def main(argv: List[str]) -> int:
    argv = list(argv)
    try:
        as_json = take_flag(argv, "--json")
        short_labels = take_flag(argv, "--short-labels")
        fold = take_flag(argv, "--shared-timeouts")
        judgement_path = take_value(argv, "--judgement")
        out = take_value(argv, "--out")
    except TableError as error:
        print(str(error), file=sys.stderr)
        return 2
    if len(argv) != 2 or argv[0] not in ("check", "diagram", "table", "report"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    subcommand, path = argv
    try:
        table = load(path)
        judgement = load_judgement(judgement_path) if subcommand == "report" else {}
    except (TableError, JudgementError, json.JSONDecodeError, OSError) as error:
        print(f"cannot read {judgement_path if isinstance(error, JudgementError) else path}: {error}", file=sys.stderr)
        return 2
    results = run_checks(table)
    if subcommand == "check":
        print(json.dumps(results_json(table, results), indent=2) if as_json else report(table, results))
        return 0 if all(r.passed for r in results) else 1
    if subcommand == "diagram":
        print(diagram(table, results, short_labels=short_labels, fold_timeouts=fold))
    elif subcommand == "table":
        print(markdown_table(table))
    else:
        page = build_report(table, results, judgement, short_labels)
        if out:
            with open(out, "w", encoding="utf-8") as handle:
                handle.write(page)
            print(out)
        else:
            print(page, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
