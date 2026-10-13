---
name: retrospective
description: Evidence-based milestone or incident retrospective, action tracking and owner-scoped procedural memory proposals.
---

# Retrospective

Use after an accepted milestone or a significant failure/rework checkpoint. Idle is not completion. A retrospective may happen while delivery remains incomplete; it does not authorize acceptance or a Jira Done transition.

## Coordinate a focused discussion

Check existing meetings and Jira for this checkpoint before creating another. Reuse the existing retrospective and action items on retries. Invite only owners involved in the decision; avoid an all-team meeting for a single tool failure.

Use `create_meeting(agenda="Retrospective — <checkpoint>", participants="<actual agent names>", description="<evidence links, decision needed>", max_rounds=2)`.
Get actual names from the current team, not example rosters. The creator is included automatically. Present findings before issuing a separate verdict after participants have contributed or absences are explicitly recorded.

Discuss evidence, root cause, what worked, and one measurable change. Separate observed facts from hypotheses. Publish the summary in Confluence; link actionable Jira tasks with owner, acceptance criteria and measurement. Workspace notes are drafts, not durable memory.

## Learn within each agent's scope

Each owner proposes their own reusable lesson through memory_server `procedure_propose(title, steps)`. The tool binds the caller identity: never impersonate another owner or store a team observation as a user preference.

Include in `steps`:
- Trigger/context where this workflow applies.
- Evidence and root cause; limits of what was actually verified.
- Concrete steps, verification and stopping conditions.
- Jira/Confluence evidence references and review date.

Use one concise procedure per distinct lesson. Search your existing procedural memories first and reuse an equivalent lesson. Do not persist transcripts, temporary assignments, credentials, raw tool dumps or unsupported claims. Cross-agent/global promotion requires separate user review.

A returned candidate ID with pending status means proposed, not learned or applied. Approval is mandatory for procedure proposals. If memory is disabled or unavailable, record the unresolved action on Jira; do not claim persistence.

## Verify the learning loop

Record candidate IDs and approval state in the retrospective. After approval, use `memory_search` for the relevant procedure, and `memory_fetch` only when full details are needed. On the next related task or resumed session, check retrieval and apply the procedure to an observable action. Only then mark the learning action verified. A meeting verdict, file, candidate or approval alone does not prove future application.
