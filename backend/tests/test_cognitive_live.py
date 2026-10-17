"""Behavioral contract for live dispatch; model and tool runtime are test adapters."""

import asyncio
import json
import unittest

from services.cognitive.live import decode_strategies, deliberate_turn


PLAN = json.dumps({"strategies": [
    {"guidance": "Check available evidence; state unknowns", "confidence": 0.9,
     "cost": 1, "risk": 0.1},
    {"guidance": "Ask for missing details", "confidence": 0.5,
     "cost": 1, "risk": 0.2},
]})


class LiveTurnTests(unittest.IsolatedAsyncioTestCase):
    async def run_turn(self, outputs, response="Ready", error=None):
        calls, events, prompts = [], [], []
        async def generate(prompt):
            prompts.append(prompt)
            item = outputs.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        async def send(guidance):
            calls.append(guidance)
            if error:
                raise error
            return response
        async def emit(event):
            events.append(event)
        result = await deliberate_turn(message="Do the task", generate=generate,
                                       send=send, emit=emit, timeout=0.1)
        return result, calls, events, prompts

    async def test_ranked_plan_executes_once_and_reviews(self):
        (response, summary), calls, events, prompts = await self.run_turn(
            [PLAN, '{"passed":true}'])
        self.assertEqual(response, "Ready")
        self.assertEqual(len(calls), 1)
        self.assertIn("Check available evidence", calls[0])
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["review"], "advisory")
        self.assertEqual(len(prompts), 2)
        self.assertNotIn("Do the task", json.dumps(summary))

    async def test_failed_review_never_replays(self):
        (_, summary), calls, _, _ = await self.run_turn([PLAN, '{"passed":false}'])
        self.assertNotEqual(summary["status"], "succeeded")
        self.assertEqual(len(calls), 1)

    async def test_review_provider_error_retains_response(self):
        (response, summary), calls, _, _ = await self.run_turn([PLAN, TimeoutError()])
        self.assertEqual(response, "Ready")
        self.assertNotEqual(summary["status"], "succeeded")
        self.assertEqual(len(calls), 1)

    async def test_invalid_plan_falls_back_once(self):
        (_, summary), calls, _, _ = await self.run_turn(['not JSON'])
        self.assertEqual(calls, [""])
        self.assertEqual(summary["status"], "planning_unavailable")

    async def test_all_plans_pruned_falls_back_once(self):
        invalid = PLAN.replace('"confidence": 0.9', '"confidence": 3').replace(
            '"confidence": 0.5', '"confidence": 3')
        (_, summary), calls, _, _ = await self.run_turn([invalid])
        self.assertEqual(calls, [""])
        self.assertEqual(summary["status"], "blocked")

    async def test_original_dispatch_exception_propagates(self):
        with self.assertRaisesRegex(ValueError, "original failure"):
            await self.run_turn([PLAN], error=ValueError("original failure"))

    async def test_truthy_review_is_not_accepted(self):
        (_, summary), calls, _, _ = await self.run_turn([PLAN, '{"passed":"yes"}'])
        self.assertNotEqual(summary["status"], "succeeded")
        self.assertEqual(len(calls), 1)

    async def test_cancellation_before_execution(self):
        started = asyncio.Event()
        calls = []
        async def generate(prompt):
            started.set()
            await asyncio.sleep(10)
        async def send(guidance):
            calls.append(guidance)
        async def emit(event):
            pass
        task = asyncio.create_task(deliberate_turn(
            message="task", send=send, generate=generate, emit=emit))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(calls, [])

    def test_model_cannot_select_tools(self):
        strategies = decode_strategies(PLAN)
        self.assertTrue(all(s.steps[0].tool == "agent_turn" for s in strategies))
        with self.assertRaises(ValueError):
            decode_strategies('{"strategies":[]}')


if __name__ == "__main__":
    unittest.main()
