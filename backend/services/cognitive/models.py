"""Explicit intent, evidence, planning, and memory boundaries."""

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Criterion:
    key: str
    expected: Any


@dataclass(frozen=True)
class Goal:
    intent: str
    success: tuple[Criterion, ...]
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.intent.strip() or not self.success:
            raise ValueError("Intent and explicit success criteria are required")
        keys = [c.key for c in self.success]
        if any(not key.strip() for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Success criteria need unique, nonempty keys")


@dataclass
class WorldModel:
    facts: dict[str, Any] = field(default_factory=dict)
    unknowns: list[str] = field(default_factory=list)
    assumptions: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Strategy:
    id: str
    steps: tuple[Step, ...]
    confidence: float = 0.5
    cost: float = 1.0
    risk: float = 0.0
    rationale: str = ""


@dataclass
class RunState:
    goal: Goal
    world: WorldModel
    run_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = 1
    status: str = "understanding"
    strategies: list[Strategy] = field(default_factory=list)
    pruned: dict[str, list[str]] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, bool] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        """Detached, JSON-ready memory record. Host controls retention/redaction."""
        import json

        return json.loads(json.dumps(asdict(self), allow_nan=False))
