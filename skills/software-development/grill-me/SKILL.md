---
name: grill-me
description: "Use when the user wants to stress-test a plan, says grill me, asks for hard questions, or needs an interactive design interview before implementation. Interviews one decision at a time, recommends answers, and resolves ambiguity before execution."
version: 1.0.0
author: Hermes Agent (adapted from Matt Pocock)
license: MIT
metadata:
  hermes:
    tags: [planning, interview, requirements, clarification, decision-making]
    related_skills: [writing-plans, grill-with-docs, plan]
---

# Grill Me

## Overview

Run an interactive alignment session before acting. The goal is shared understanding, not performance theater: force vague plans into concrete decisions, expose hidden dependencies, and make the next implementation step obvious.

This skill is intentionally conversational. Ask one question at a time, include your recommended answer, wait for the user's answer, then continue. If a question can be answered by inspecting files, code, docs, or prior conversation context, use tools instead of asking.

## When to Use

Use when the user:
- Says "grill me", "stress-test this", "ask me hard questions", or "challenge this plan".
- Presents a plan/design that is under-specified, risky, or full of implicit decisions.
- Wants to prepare a spec, PRD, implementation plan, product decision, architecture change, or launch plan.
- Needs confidence before committing time or delegating work.

Do not use when:
- The user asks for immediate execution and the path is already clear.
- The task is a simple factual lookup or mechanical edit.
- The user explicitly asks for a written critique instead of an interactive interview.

## Workflow

### 1. State the frame

Briefly restate the plan as you understand it and identify the highest-risk unknowns. Keep this short.

### 2. Ask one load-bearing question

Ask exactly one question. A load-bearing question is one where the answer changes implementation, prioritization, risk, or success criteria.

For each question include:
- **Why it matters** — the decision it affects.
- **My recommendation** — the default answer you would choose and why.
- **Question** — the precise thing the user should answer.

### 3. Prefer inspection over interrogation

Before asking, check whether the answer is retrievable:
- Existing code or tests.
- Project docs, AGENTS.md, README, architecture notes, ADRs.
- Current conversation context.
- Issue trackers or plans the user referenced.

If tools can answer it, inspect and say what you found instead of asking.

### 4. Walk the decision tree

Resolve dependencies in order:
1. Goal and non-goals.
2. Users/actors and scenarios.
3. Constraints and invariants.
4. Interfaces and integration points.
5. Failure modes and edge cases.
6. Test/verification strategy.
7. Rollout, migration, and reversibility.

Do not batch a long questionnaire. The user's answer to one question should influence the next question.

### 5. Close with a decision summary

When the important branches are resolved, provide:
- Confirmed decisions.
- Remaining open questions, if any.
- Recommended next step: plan, PRD, issues, prototype, or implementation.

## Question Template

```
Question N: <short decision name>
Why it matters: <what changes based on this answer>
My recommendation: <recommended answer and rationale>
Question: <single question for the user>
```

## Common Pitfalls

1. **Asking a questionnaire.** Ask one question at a time. The point is adaptive exploration.
2. **Asking what tools can answer.** Inspect code/docs first when possible.
3. **No recommendation.** The user should not carry all reasoning burden; provide your recommended answer.
4. **Over-grilling low-risk work.** Stop when the remaining ambiguity no longer changes the work.
5. **Turning the session into implementation.** Do not code unless the user explicitly switches from grilling to execution.

## Verification Checklist

- [ ] Each turn asked at most one question.
- [ ] Every question was load-bearing.
- [ ] Tool-retrievable answers were inspected instead of asked.
- [ ] Each question included a recommendation.
- [ ] Final summary captured decisions and next step.
