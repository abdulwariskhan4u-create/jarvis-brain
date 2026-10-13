"""Bounded result deltas for orchestrator notifications, backed by cycle events."""
from __future__ import annotations

import hashlib

MAX_REPORT_CHARS = 8000
MAX_RESULT_CHARS = 2000


def worker_result_state(workers: list[dict]) -> dict:
    return {w.get("agent_name", "?"): {
        "run_id": w.get("run_id"), "status": w.get("status"),
        "digest": hashlib.sha256(str(w.get("error") or w.get("result") or "").encode()).hexdigest(),
    } for w in workers}


def _cell(value) -> str:
    return str(value or "?").replace("\n", " ").replace("|", "/")[:120]


def build_worker_report(workers: list[dict], *, previous: dict | None = None,
                        meeting_warning: str = "") -> str:
    """A state snapshot is not evidence of work on the latest requirement.

Only changed outcomes are expanded. Run identity plus the result digest also
handles fresh turns in the same persistent worker. Legacy events without a
digest remain explicitly unknown, rather than inventing freshness.
"""
    header = ("⏳ **Team Status Update** — members are idle but a meeting is still open. Team is NOT done."
              if meeting_warning else
              "📋 **Team Status Update** — All members have stopped running. "
              "Idle may mean waiting for approval or input; review outcomes before declaring completion.")
    lines = [header,
             "These are state snapshots, not proof of activity on the current requirement.",
             "", "| Member | State | Run | Result freshness |", "|---|---|---|---|"]
    current = worker_result_state(workers)
    expanded = []
    for worker in workers:
        name = worker.get("agent_name", "?")
        state = current[name]
        old = (previous or {}).get(name)
        if old is None or old.get("run_id") != state["run_id"]:
            freshness = "new run"
        elif old.get("digest") is None:
            freshness = "unknown (legacy snapshot)"
        elif old == state:
            freshness = "unchanged"
        else:
            freshness = "changed result"
        lines.append(f"| {_cell(name)} | {_cell(state['status'])} | {_cell(state['run_id'])} | {freshness} |")
        if freshness in {"new run", "changed result"}:
            result = str(worker.get("error") or worker.get("result") or "No output")
            excerpt = result[:MAX_RESULT_CHARS]
            if len(result) > MAX_RESULT_CHARS:
                excerpt += "\n[result truncated; remaining content is not shown]"
            expanded.append(f"\n### New/changed result — {_cell(name)} (run {_cell(state['run_id'])})\n"
                            "Member-reported output; review evidence before accepting.\n" + excerpt)
    report = "\n".join(lines)
    for block in expanded:
        if len(report) + len(block) > MAX_REPORT_CHARS - 200:
            report += "\n[additional result excerpts truncated by report budget]"
            break
        report += block
    report += "\n" + (meeting_warning or "Review new/changed outputs and decide next actions; do not request unchanged reports again.")
    if len(report) > MAX_REPORT_CHARS:
        report = report[:MAX_REPORT_CHARS - 40] + "\n[report truncated by budget]"
    return report
