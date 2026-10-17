# Initial JARVIS Cognitive Intent Engine

An opt-in, dependency-free service at `backend/services/cognitive`. It runs
without API keys, network access, fast-agent submodules, or a database. This is
an initial orchestration kernel, not an autonomous general intelligence or a
replacement for the existing Jarvis chat runtime.

## Run

From `backend`, with Python 3.13:

```sh
python -m services.cognitive.demo
python -m unittest discover -s tests -p test_cognitive_engine.py -v
```

The demo prunes an unavailable tool, tries a stale cache, fails verification,
recovers with a fresh strategy, and prints a successful JSON state.

## Components and contracts

| Responsibility | Initial implementation |
| --- | --- |
| Goal understanding | Normalize intent; require explicit structured success criteria |
| Context/world model | Caller-supplied facts, unknowns, assumptions, context, kept separate |
| Strategy generation | Injected synchronous `generate(goal, world)` callback; demo supplies alternatives |
| Critic | Reject invalid scores, missing tools, excessive steps, duplicate or cyclic dependencies |
| Ranking/pruning | Confidence minus risk minus 0.05 times cost, stable ID tie-break |
| Planner | Stable topological order of step dependencies |
| Meta-reasoner | Deterministic succeed/recover/fail/exhaust decision after verification |
| Tool router/executor | Explicit async allowlist, isolated arguments, timeout, approval gate |
| Verifier | Exact typed criterion equality against this attempt's tool evidence |
| Recovery | Next ranked strategy, bounded attempts; transient read/idempotent retries with backoff |
| Memory | Detached versioned JSON snapshot of goal, world, evidence, attempts, events |

No natural-language constraint is automatically enforced. The host must turn
constraints into concrete tool allowlists, approval decisions, and validation.
Likewise, tool evidence is a trust boundary: adapters must independently check
external results before returning evidence. Equality checks cannot establish
that an untrusted tool is truthful. Assumptions and existing facts never count
as fresh proof of success. Failed alternatives cannot pool evidence.

## Safety and lifecycle

Tools default to read-only; adapters for mutations **must** set `read_only=False`.
Writes require an async approval callback returning exactly `True`. The callback
receives the run ID, tool name, and exact arguments. Approval is scoped to that
call. Never register arbitrary shell execution or model-selected functions.
Timeouts cancel cooperative async tools; a remote side effect may still occur.
Only explicitly idempotent writes may retry transient failures. Any failed plan
containing writes stops with `needs_review`; it cannot automatically replay
completed effects in an alternative plan. `needs_approval` requires a host to
obtain approval and decide how to continue; snapshots are records, not automatic
resume tokens. Cancellation propagates to the caller.

Terminal statuses: `succeeded`, `blocked`, `failed`, `exhausted`,
`needs_approval`, `needs_review`. Exceptions from generation, invalid generator
contracts, or the event sink propagate to the host. Strategy generation must
be fast, bounded, and local; an async model adapter should generate validated
strategies before calling this engine. Tool adapters must be cooperative async
functions; synchronous blocking code defeats asyncio timeouts.

Snapshots can contain sensitive arguments and tool outputs. Persist only after
host-side redaction and consent; use the existing memory/session infrastructure
for retention and access policy. Nothing is persisted automatically. Exception
messages are omitted because provider errors may contain credentials. Credentials
belong in environment variables and existing `.env.example` templates only.

## Integrating with the existing runtime

The module is opt-in; the default chat and voice routes are unchanged. Call
`await engine.run(goal, world)` from an authenticated backend service. Register
only adapters permitted for that request, retaining the existing approval flow.
Do not expose an unauthenticated execution endpoint.

An optional async `sink(event)` receives ordered lifecycle events in real time.
Route it through existing `services/activity_stream.py` and
`services/sse_progress.py` managers for the request. No polling is required.
Events omit arguments and results; the private state retains evidence. A sink
failure stops the run instead of silently executing without progress visibility.
This change does not create runtime agents, bypass session management, or alter
fast-agent's tool loop. When adding a model-backed integration, use existing
ToolRunnerHooks and session service rather than patching framework internals.

Framework references reviewed:
[Tool Runner](https://fast-agent.ai/agents/tool_runner/),
[Prompting](https://fast-agent.ai/agents/prompting/),
[Instructions](https://fast-agent.ai/agents/instructions/).

## Validation scope

The isolated unittest suite covers verified success, evidence separation,
recovery, pruning, transient retries, timeouts, approval enforcement, write replay
prevention, cancellation, JSON snapshots, budgets, and dependency ordering.
The full Jarvis stack and real provider/MCP adapters require separate integration
testing with configured services and initialized submodules.
