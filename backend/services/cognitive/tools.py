"""Allowlisted async tools with explicit approval and retry semantics."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


class ApprovalRequired(Exception):
    pass


class TransientToolError(Exception):
    """Adapter-classified transient error; eligible for bounded retry."""


@dataclass(frozen=True)
class Tool:
    name: str
    execute: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    read_only: bool = True
    idempotent: bool = False
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if not self.name.strip() or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Tool needs a name and finite positive timeout")


class ToolRouter:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("Duplicate tool names")

    @property
    def names(self) -> set[str]:
        return set(self._tools)

    def resolve(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ValueError(f"Unregistered tool: {name}") from None

    async def call(self, name: str, arguments: dict[str, Any], *,
                   approved: bool = False) -> dict[str, Any]:
        import json

        tool = self.resolve(name)
        if not tool.read_only and not approved:
            raise ApprovalRequired(name)
        # Defend caller-owned plan data against mutations by adapters.
        arguments = json.loads(json.dumps(arguments, allow_nan=False))
        result = await asyncio.wait_for(tool.execute(arguments), tool.timeout)
        if not isinstance(result, dict) or any(not isinstance(k, str) for k in result):
            raise ValueError("Tool evidence must be an object with string keys")
        return json.loads(json.dumps(result, allow_nan=False))
