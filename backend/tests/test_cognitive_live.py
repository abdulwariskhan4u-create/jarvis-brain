"""Behavioral contract for live dispatch; model and tool runtime are test adapters."""

import asyncio
import json
import unittest
import importlib.util
from types import SimpleNamespace
from unittest.mock import patch

from services.cognitive.live import decode_strategies, deliberate_turn
from services.cognitive.live import send_live_turn


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


@unittest.skipUnless(importlib.util.find_spec("fast_agent"), "requires backend runtime")
class LiveRuntimeContractTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, fails=False):
        from fast_agent.agents.tool_runner import ToolRunnerHooks
        original_calls = []
        async def original_hook(runner, messages):
            original_calls.append(True)
        original = ToolRunnerHooks(before_llm_call=original_hook)
        agent = SimpleNamespace(tool_runner_hooks=original)
        session = SimpleNamespace(info=SimpleNamespace(name="session-a", metadata={}))
        payload = object()  # Includes attachments in production; preserve identity.
        answers = iter([PLAN, '{"passed":true}'])
        async def generate(prompt):
            return next(answers)
        received = []
        guidance = []
        async def send(actual, agent_name=None):
            received.append(actual)
            await agent.tool_runner_hooks.before_llm_call(
                SimpleNamespace(iteration=0, append_messages=guidance.append), [])
            if fails:
                raise ValueError("dispatch failed")
            return "Completed"
        app = SimpleNamespace(send=send)
        try:
            with patch.dict("os.environ", {"JARVIS_COGNITIVE_ENABLED": "1"}), patch(
                "services.cognitive.live.build_generate", return_value=generate,
            ):
                response = await send_live_turn(app, agent, payload, "task", "Jarvis", session)
                self.assertEqual(response, "Completed")
                self.assertEqual(session.info.metadata["cognitive_last_turn"]["status"], "succeeded")
        finally:
            self.assertIs(agent.tool_runner_hooks, original)
            self.assertEqual(received, [payload])
            self.assertEqual(original_calls, [True])
            self.assertIn("not authorization", guidance[0])

    async def test_payload_and_existing_hooks_preserved(self):
        await self.exercise()

    async def test_hooks_restored_after_dispatch_error(self):
        with self.assertRaisesRegex(ValueError, "dispatch failed"):
            await self.exercise(fails=True)


if __name__ == "__main__":
    unittest.main()
