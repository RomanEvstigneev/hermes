---
name: to-issues
description: "Use when the user wants to convert a plan, spec, PRD, conversation, or parent issue into implementation issues. Breaks work into independently grabbable vertical slices, marks HITL versus AFK work, and publishes to GitHub/Linear/local trackers only after approval."
version: 1.0.0
author: Hermes Agent (adapted from Matt Pocock)
license: MIT
metadata:
  hermes:
    tags: [issues, planning, project-management, vertical-slices, delegation]
    related_skills: [writing-plans, github-issues, linear, subagent-driven-development]
---

# To Issues

## Overview

Turn an approved plan, PRD, issue, or conversation into issue-tracker work items. The output should be independently grabbable by humans or agents and should favor thin vertical slices over horizontal layer tasks.

Publishing issues is a side effect. Draft and get approval first unless the user explicitly asked you to create the issues immediately.

## When to Use

Use when the user asks to:
- Convert a plan/spec/PRD into issues.
- Break work into implementation tickets/tasks.
- Prepare work for AFK agents or delegation.
- Split a large parent issue into smaller slices.
- Create a backlog from the current conversation.

Do not use when the user wants an implementation plan document only; use `writing-plans` instead.

## Workflow

### 1. Gather source material

Read all provided context:
- Current conversation.
- Referenced files or docs.
- Parent issue URL/number/body/comments.
- PRD or implementation plan.
- Relevant `CONTEXT.md`, `AGENTS.md`, and ADRs if this is a codebase task.

Use the appropriate issue skill/tool for tracker operations: GitHub, Linear, local markdown, GitLab, or the user's stated tracker.

### 2. Explore enough code to slice correctly

If the issue breakdown depends on architecture, inspect the codebase enough to identify layers, seams, tests, and existing patterns. Titles and descriptions should use project domain language, not only implementation jargon.

### 3. Draft vertical slices

A good slice:
- Cuts through every required layer for a narrow behavior path.
- Is demoable or verifiable on its own.
- Has clear acceptance criteria.
- Can be picked up by one human or one agent with minimal extra context.
- Has explicit blockers if it cannot start immediately.

Avoid horizontal slices like "add database schema", "build API", "build UI" unless that task is independently valuable and verifiable.

Mark each slice:
- **AFK** — an agent can execute from the issue alone with no human context.
- **HITL** — human input/review/decision is required.

Prefer AFK slices where safe, but do not fake autonomy when product/design/security decisions remain open.

### 4. Ask for approval

Present the draft before publishing:

```
1. <Title>
   Type: AFK | HITL
   Blocked by: <none or issue title>
   Covers: <user story / behavior>
   Why this slice: <vertical path>
```

Ask:
- Is the granularity right?
- Are blockers correct?
- Should any slices be merged or split?
- Are the HITL/AFK labels correct?

Iterate until approved.

### 5. Publish in dependency order

After approval, create issues in blocker-first order so dependent issues can reference real IDs.

Use this body template:

```
## Parent

<Parent issue/spec reference, if any>

## What to build

<Concise end-to-end behavior. Describe the vertical slice, not separate layer chores.>

## Acceptance criteria

- [ ] <Observable criterion>
- [ ] <Observable criterion>
- [ ] <Test/verification criterion>

## Blocked by

<None - can start immediately, or issue references>

## Implementation notes

<Relevant files, domain terms, ADRs, test commands, or constraints.>

## Agent readiness

AFK | HITL — <why>
```

Apply the user's triage labels if known, typically `needs-triage` or `ready-for-agent`. Do not close or modify the parent issue unless explicitly asked.

## Local Markdown Fallback

If no remote issue tracker is configured, create issue files under a user-approved directory such as `.scratch/issues/` or `docs/issues/`. Use kebab-case filenames with numeric prefixes if order matters.

## Common Pitfalls

1. **Layer tickets.** "Build backend" and "build frontend" are usually not independently valuable.
2. **Publishing before approval.** Issue creation is a side effect; draft first.
3. **Missing blockers.** If order matters, encode it explicitly.
4. **AFK overconfidence.** Mark HITL when product, security, architecture, or UX decisions are unresolved.
5. **Thin but not complete.** A vertical slice is narrow, but it still reaches a verifiable outcome.

## Verification Checklist

- [ ] Source material and parent issue were fully read.
- [ ] Code/docs were inspected where needed.
- [ ] Draft slices are vertical, demoable, and independently grabbable.
- [ ] User approved before publishing.
- [ ] Issues were created in dependency order.
- [ ] Parent issue was not modified unless requested.
