"""Dependency-free behavioral tests: python -m unittest discover -s tests -p test_cognitive_engine.py"""

import asyncio
import json
import unittest

from services.cognitive import (
    CognitiveEngine, Criterion, Goal, Step, Strategy, Tool, ToolRouter, WorldModel,
)
from services.cognitive.planning import plan, understand
from services.cognitive.tools import TransientToolError


class CognitiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.goal = Goal("Get a verified answer", (Criterion("answer", 42),))

    def engine(self, tools, strategies, **kwargs):
        return CognitiveEngine(ToolRouter(tools), lambda goal, world: strategies,
                               retry_delay=0, **kwargs)

    async def test_success_and_detached_memory(self):
        async def answer(args):
            return {"answer": 42}
        events = []
        async def sink(event):
            events.append(event)
        state = await self.engine([Tool("answer", answer)],
                                 [Strategy("direct", (Step("one", "answer"),))],
                                 sink=sink).run(self.goal)
        self.assertEqual(state.status, "succeeded")
        self.assertTrue(state.verification["answer"])
        snapshot = json.loads(json.dumps(state.snapshot()))
        snapshot["evidence"]["answer"] = 0
        self.assertEqual(state.evidence["answer"], 42)
        self.assertEqual([e["sequence"] for e in events], list(range(len(events))))

    async def test_assumptions_and_facts_do_not_prove_success(self):
        async def empty(args):
            return {}
        world = WorldModel(facts={"answer": 42}, assumptions={"answer": 42})
        state = await self.engine([Tool("empty", empty)],
                                 [Strategy("empty", (Step("one", "empty"),))]).run(
                                     self.goal, world)
        self.assertEqual(state.status, "failed")
        self.assertFalse(state.verification["answer"])

    async def test_pruning_and_recovery(self):
        async def stale(args):
            return {"answer": 0}
        async def fresh(args):
            return {"answer": 42}
        strategies = [Strategy("bad", (Step("bad", "missing"),)),
                      Strategy("stale", (Step("one", "stale"),), confidence=1),
                      Strategy("fresh", (Step("one", "fresh"),), confidence=0.5)]
        state = await self.engine([Tool("stale", stale), Tool("fresh", fresh)],
                                 strategies).run(self.goal)
        self.assertEqual(state.status, "succeeded")
        self.assertIn("bad", state.pruned)
        self.assertEqual(len(state.attempts), 2)
        self.assertIn("recover", [e["phase"] for e in state.events])

    async def test_retry_transient_read(self):
        calls = 0
        async def flaky(args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TransientToolError()
            return {"answer": 42}
        state = await self.engine([Tool("flaky", flaky)],
                                 [Strategy("read", (Step("one", "flaky"),))]).run(self.goal)
        self.assertEqual((state.status, calls), ("succeeded", 2))

    async def test_writes_need_approval_and_are_not_replayed(self):
        calls = 0
        async def write(args):
            nonlocal calls
            calls += 1
            raise TransientToolError("sensitive error text")
        strategies = [Strategy("a", (Step("one", "write"),)),
                      Strategy("b", (Step("one", "write"),))]
        tools = [Tool("write", write, read_only=False)]
        state = await self.engine(tools, strategies).run(self.goal)
        self.assertEqual((state.status, calls), ("needs_approval", 0))
        async def approve(run_id, name, arguments):
            return True
        state = await self.engine(tools, strategies, approval=approve).run(self.goal)
        self.assertEqual((state.status, calls), ("needs_review", 1))
        self.assertNotIn("sensitive error text", json.dumps(state.snapshot()))

    async def test_no_evidence_leaks_between_strategies(self):
        async def first(args):
            return {"answer": 42}
        async def second(args):
            return {"other": True}
        goal = Goal("Both", (Criterion("answer", 42), Criterion("other", True)))
        state = await self.engine([Tool("a", first), Tool("b", second)], [
            Strategy("a", (Step("a", "a"),)),
            Strategy("b", (Step("b", "b"),)),
        ]).run(goal)
        self.assertEqual(state.status, "failed")
        self.assertNotIn("answer", state.evidence)

    async def test_timeout_and_budget(self):
        calls = 0
        async def slow(args):
            nonlocal calls
            calls += 1
            await asyncio.sleep(10)
            return {"answer": 42}
        state = await self.engine([Tool("slow", slow, timeout=0.001)],
                                 [Strategy("a", (Step("one", "slow"),))],
                                 max_attempts=1).run(self.goal)
        self.assertEqual(state.status, "exhausted")
        self.assertEqual(calls, 2)

    async def test_cancellation_propagates(self):
        started = asyncio.Event()
        async def wait(args):
            started.set()
            await asyncio.sleep(10)
            return {}
        engine = self.engine([Tool("wait", wait)],
                             [Strategy("a", (Step("a", "wait"),))])
        task = asyncio.create_task(engine.run(self.goal))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_invalid_candidates_block_before_tools(self):
        async def unused(args):
            self.fail("Invalid plan executed")
        strategies = [Strategy("cycle", (Step("a", "tool", depends_on=("a",)),)),
                      Strategy("metrics", (Step("a", "tool"),), risk=float("nan"))]
        state = await self.engine([Tool("tool", unused)], strategies).run(self.goal)
        self.assertEqual(state.status, "blocked")
        self.assertEqual(len(state.pruned), 2)

    def test_validation_and_dependency_order(self):
        with self.assertRaises(ValueError):
            Goal("", ())
        with self.assertRaises(ValueError):
            CognitiveEngine(ToolRouter([]), lambda g, w: [], max_attempts=0)
        self.assertEqual(understand("  get   answer ", self.goal.success).intent, "get answer")
        strategy = Strategy("ordered", (Step("b", "t", depends_on=("a",)), Step("a", "t")))
        self.assertEqual([s.id for s in plan(strategy)], ["a", "b"])
        self.assertFalse(CognitiveEngine.verify(self.goal, {"answer": 42.0})["answer"])


if __name__ == "__main__":
    unittest.main()
