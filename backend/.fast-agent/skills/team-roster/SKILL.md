---
name: team-roster
description: Discover actual team identities and runtime capabilities before delegating to an owner.
---

# Team roster

Use the current session roster supplied at spawn/resume, or one `get_team_status` call when ownership is ambiguous. Names are generated per session; never address a static example name or reuse a name from another team. Reserved roles are not active members.

## Choose the owner

| Role | Ownership |
|------|-----------|
| PM | Scope, selective staffing, decision meetings, delivery and acceptance gates |
| BA | Requirements and acceptance criteria |
| SA | Architecture, interfaces and implementation review |
| Dev | Implementation within the authorized workspace |
| Designer | Art/design system, visual and interaction specifications |
| QE | Reproduction, tests and evidence against actual served build |
| DSO | CI, deployment and security review within granted permissions |

A role does not establish tool access. Inspect exposed tools and current agent configuration before declaring a capability absent or requesting another installation. Missing local CLI dependencies do not prove an already-connected MCP is unavailable. Use a harmless scoped capability probe and report its exact outcome.

## Coordinate without duplicate work

Send actionable assignments to actual display names in this session. Include checkpoint, output, owner and dependency; do not broadcast when one owner is sufficient. Team messages and status events are delivered automatically; do not poll inbox or repeatedly ask for unchanged status.

Do not reply or acknowledge FYI/no_reply messages. Report new evidence, blockers or deliverables once, linking the artifact instead of forwarding full histories. Escalate a repeated concrete failure to PM with the attempted action and exact error.

Idle means waiting, not completed. Resume a live member through its existing inbox; never start a second process for the same member. PM chooses affected participants for review/retro, and each owner proposes their own reusable lessons using the `retrospective` skill.
