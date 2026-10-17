"""Run from backend: python -m services.cognitive.demo"""

import asyncio
import json

from . import CognitiveEngine, Criterion, Goal, Step, Strategy, Tool, ToolRouter, WorldModel


async def main() -> None:
    async def cached(arguments: dict) -> dict:
        return {"answer": "stale"}

    async def refresh(arguments: dict) -> dict:
        return {"answer": "ready", "source": "local-demo"}

    def generate(goal: Goal, world: WorldModel) -> list[Strategy]:
        return [
            Strategy("cached", (Step("read-cache", "cached"),), confidence=0.9),
            Strategy("fresh", (Step("refresh", "refresh"),), confidence=0.8),
            Strategy("unavailable", (Step("missing", "network"),)),
        ]

    engine = CognitiveEngine(ToolRouter([Tool("cached", cached), Tool("refresh", refresh)]),
                             generate)
    state = await engine.run(Goal("Find a verified ready answer",
                                  (Criterion("answer", "ready"),)),
                             WorldModel(unknowns=["answer freshness"],
                                        assumptions={"cache might be current": True}))
    print(json.dumps(state.snapshot(), indent=2))
    if state.status != "succeeded":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
