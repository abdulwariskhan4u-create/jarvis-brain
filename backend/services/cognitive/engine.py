"""Bounded plan/act/verify/recover orchestration with memory-ready state."""

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from .models import Goal, RunState, Strategy, WorldModel
from .planning import StrategyGenerator, critique, meta_reason, plan, rank
from .tools import ApprovalRequired, ToolRouter, TransientToolError

EventSink = Callable[[dict[str, Any]], Awaitable[None]]
Approval = Callable[[str, str, dict[str, Any]], Awaitable[bool]]


class CognitiveEngine:
    def __init__(self, router: ToolRouter, generate: StrategyGenerator, *,
                 max_attempts: int = 3, retries: int = 1, max_steps: int = 20,
                 max_candidates: int = 20, retry_delay: float = 0.1,
                 sink: EventSink | None = None,
                 approval: Approval | None = None) -> None:
        import math

        if (any(type(v) is not int for v in
                (max_attempts, retries, max_steps, max_candidates))
                or min(max_attempts, max_steps, max_candidates) < 1 or retries < 0
                or not math.isfinite(retry_delay) or retry_delay < 0):
            raise ValueError("Invalid execution budgets")
        self.router, self.generate = router, generate
        self.max_attempts, self.retries = max_attempts, retries
        self.max_steps, self.max_candidates = max_steps, max_candidates
        self.retry_delay = retry_delay
        self.sink, self.approval = sink, approval

    async def _event(self, state: RunState, phase: str, **data: Any) -> None:
        event = {"run_id": state.run_id, "sequence": len(state.events),
                 "phase": phase, **data}
        state.events.append(event)
        if self.sink:
            # Delivery failure terminates execution; never act without observability.
            await self.sink(deepcopy(event))

    @staticmethod
    def verify(goal: Goal, evidence: dict[str, Any]) -> dict[str, bool]:
        return {c.key: c.key in evidence and type(evidence[c.key]) is type(c.expected)
                and evidence[c.key] == c.expected for c in goal.success}

    async def run(self, goal: Goal, world: WorldModel | None = None) -> RunState:
        state = RunState(deepcopy(goal), deepcopy(world or WorldModel()))
        await self._event(state, "understanding")
        # Facts/assumptions never count as fresh execution evidence.
        candidates = list(self.generate(deepcopy(goal), deepcopy(state.world)))
        if len(candidates) > self.max_candidates:
            raise ValueError("Strategy generator exceeded candidate budget")
        ids = [s.id for s in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate strategy IDs")
        valid: list[Strategy] = []
        for candidate in candidates:
            reasons = critique(candidate, self.router.names, self.max_steps)
            if reasons:
                state.pruned[candidate.id] = reasons
            else:
                valid.append(candidate)
        state.strategies = rank(valid)
        await self._event(state, "ranked", accepted=len(valid), pruned=state.pruned)
        if not valid:
            state.status = "blocked"
            await self._event(state, "blocked")
            return state
        for index, strategy in enumerate(state.strategies[:self.max_attempts]):
            state.status = "executing"
            state.evidence = {}  # Do not mix evidence from failed alternatives.
            attempt: dict[str, Any] = {"strategy": strategy.id, "steps": []}
            state.attempts.append(attempt)
            await self._event(state, "planned", strategy=strategy.id,
                              steps=[s.id for s in plan(strategy)])
            try:
                for step in plan(strategy):
                    tool = self.router.resolve(step.tool)
                    approved = tool.read_only
                    if not approved and self.approval:
                        approved = await self.approval(
                            state.run_id, step.tool, deepcopy(step.arguments)) is True
                    for retry in range(self.retries + 1):
                        await self._event(state, "tool_started", step=step.id, retry=retry)
                        try:
                            evidence = await self.router.call(
                                step.tool, step.arguments, approved=approved)
                            break
                        except (TransientToolError, TimeoutError):
                            # A timed-out write may already have happened remotely.
                            if (not tool.read_only and not tool.idempotent
                                    or retry == self.retries):
                                raise
                            await self._event(state, "retry", step=step.id)
                            await asyncio.sleep(self.retry_delay * 2 ** retry)
                    state.evidence.update(evidence)
                    attempt["steps"].append({"id": step.id, "evidence": evidence})
                    await self._event(state, "tool_finished", step=step.id)
            except asyncio.CancelledError:
                state.status = "cancelled"
                await self._event(state, "cancelled")
                raise
            except ApprovalRequired:
                state.status = "needs_approval"
                await self._event(state, "needs_approval")
                return state
            except Exception as exc:
                # Exception text can contain credentials; retain only the type.
                attempt["error"] = type(exc).__name__
                await self._event(state, "tool_failed", error=type(exc).__name__)
                # After any write, its remote outcome is uncertain. Never replan
                # automatically into a second write or repeat completed effects.
                if any(not self.router.resolve(s.tool).read_only
                       for s in plan(strategy)):
                    state.status = "needs_review"
                    await self._event(state, "needs_review")
                    return state
            state.verification = self.verify(goal, state.evidence)
            if "error" in attempt:
                state.verification = {c.key: False for c in goal.success}
            await self._event(state, "verified", checks=state.verification)
            state.status = meta_reason(state, self.max_attempts - index - 1,
                                       index + 1 < len(state.strategies))
            if state.status != "recover":
                break
            if any(not self.router.resolve(s.tool).read_only for s in strategy.steps):
                state.status = "needs_review"
                break
            await self._event(state, "recover", strategy=strategy.id)
        await self._event(state, state.status)
        return state
