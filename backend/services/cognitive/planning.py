"""Deterministic initial planner, critic, ranker, and meta-reasoner."""

import math
from collections.abc import Callable, Sequence

from .models import Goal, RunState, Step, Strategy, WorldModel

StrategyGenerator = Callable[[Goal, WorldModel], Sequence[Strategy]]


def understand(intent: str, success: tuple, constraints: tuple = ()) -> Goal:
    """Normalize wording without inventing facts or inferring success."""
    return Goal(" ".join(intent.split()), success, constraints)


def plan(strategy: Strategy) -> list[Step]:
    """Topological order with stable tie-breaking; reject invalid dependency DAGs."""
    pending = {step.id: step for step in strategy.steps}
    if not pending or len(pending) != len(strategy.steps):
        raise ValueError("Plan must contain steps with unique IDs")
    if any(not step.id.strip() or not step.tool.strip() for step in strategy.steps):
        raise ValueError("Step ID and tool must be nonempty")
    done: set[str] = set()
    ordered = []
    while pending:
        ready = [s for s in pending.values() if set(s.depends_on) <= done]
        if not ready:
            raise ValueError("Missing or cyclic step dependencies")
        for step in ready:
            ordered.append(step)
            done.add(step.id)
            del pending[step.id]
    return ordered


def critique(strategy: Strategy, tool_names: set[str], max_steps: int) -> list[str]:
    reasons = []
    if not strategy.id.strip():
        reasons.append("Strategy ID is empty")
    if (not all(math.isfinite(v) for v in
                (strategy.confidence, strategy.cost, strategy.risk))
            or not 0 <= strategy.confidence <= 1
            or not 0 <= strategy.risk <= 1 or strategy.cost < 0):
        reasons.append("Invalid ranking metrics")
    if len(strategy.steps) > max_steps:
        reasons.append("Plan exceeds step budget")
    try:
        plan(strategy)
    except ValueError as exc:
        reasons.append(str(exc))
    if any(step.tool not in tool_names for step in strategy.steps):
        reasons.append("Plan requires an unregistered tool")
    return reasons


def rank(strategies: Sequence[Strategy]) -> list[Strategy]:
    return sorted(strategies, key=lambda s: (
        -(s.confidence - s.risk - 0.05 * s.cost), s.id))


def meta_reason(state: RunState, attempts_left: int, alternatives: bool) -> str:
    """Choose the next bounded action using observed state, not model prose."""
    if state.verification and all(state.verification.values()):
        return "succeeded"
    if attempts_left <= 0:
        return "exhausted"
    return "recover" if alternatives else "failed"
