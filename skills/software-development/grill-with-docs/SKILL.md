---
name: grill-with-docs
description: "Use when the user wants to stress-test a software plan against project language, existing code, and recorded decisions. Runs a one-question-at-a-time grilling session, updates CONTEXT.md/domain docs when terms crystallize, and proposes ADRs only for durable architectural decisions."
version: 1.0.0
author: Hermes Agent (adapted from Matt Pocock)
license: MIT
metadata:
  hermes:
    tags: [requirements, domain-modeling, adr, architecture, planning]
    related_skills: [grill-me, writing-plans, improve-codebase-architecture, github-issues]
---

# Grill With Docs

## Overview

Run a requirements/design grilling session that is grounded in the codebase and durable project documentation. Challenge the plan against the existing domain language, sharpen fuzzy terms, and record decisions as they crystallize.

This is the codebase-aware version of `grill-me`. It is interactive by default: ask one question at a time, include your recommended answer, and wait for the user's answer before continuing. If code or docs can answer a question, inspect them instead of asking.

## When to Use

Use when the user:
- Wants to stress-test a feature, architecture change, product behavior, or refactor against a real repo.
- Mentions domain language, project terminology, ADRs, architecture decisions, or unclear requirements.
- Needs a plan that future agents can understand without re-litigating decisions.
- Is about to create a PRD, implementation plan, issue breakdown, or architecture proposal.

Do not use for non-code brainstorming unless durable project docs are relevant; use `grill-me` instead.

## Domain Documentation Conventions

Look for these files before asking domain questions:
- `CONTEXT.md` — project/domain glossary and relationships.
- `CONTEXT-MAP.md` — map of multiple bounded contexts in a monorepo.
- `docs/adr/` — architecture decision records.
- `src/*/CONTEXT.md` and `src/*/docs/adr/` — context-scoped docs.
- `AGENTS.md`, `CLAUDE.md`, README files, and issue docs for project instructions.

Create or update documentation only when the user has asked for documentation work, when a term/decision has clearly crystallized during the session, or after explicitly confirming the write. Use English-only prose for Hermes-owned content.

## Workflow

### 1. Read before grilling

Inspect relevant docs and code paths first. Summarize only the facts that affect the next question:
- Existing glossary terms that constrain the plan.
- ADRs that already decide part of the design.
- Code behavior that confirms or contradicts the user's description.

### 2. Challenge against glossary and code

When the user uses an overloaded or conflicting term, call it out immediately:
- "CONTEXT.md defines Customer as X, but this plan seems to use it as Y. Which meaning is intended?"
- "The code currently cancels an entire Order, but the plan mentions partial cancellation. Is partial cancellation new scope?"

### 3. Ask one question at a time

Each question must include:
- Why the answer matters.
- Your recommended answer.
- The single question to answer.

Prefer concrete scenarios over abstract terminology. Invent edge cases that force boundaries to become explicit.

### 4. Update CONTEXT.md when terms crystallize

When a domain term is resolved, update the relevant `CONTEXT.md` immediately if documentation writes are in scope. Keep it domain-level, not implementation-level.

Suggested format:

```
**Term**:
Definition in domain language.
_Avoid_: ambiguous synonym, old term
```

Also capture relationships:

```
## Relationships

- A Portfolio contains many Investments.
- An Investment can have many ESG Findings.
```

Do not add generic programming terms, library names, or transient implementation details.

### 5. Propose ADRs sparingly

Offer an ADR only when all three are true:
1. The decision is hard or costly to reverse.
2. The decision would surprise a future maintainer without context.
3. The decision involved a real trade-off among alternatives.

If any condition is missing, skip the ADR. When creating one, use sequential numbering in `docs/adr/` and include status, context, decision, consequences, and alternatives considered.

### 6. Close with reusable output

End with:
- Decisions made.
- Glossary updates made or recommended.
- ADRs created or recommended.
- Remaining open questions.
- Recommended next skill: `writing-plans`, `to-issues`, `test-driven-development`, or `improve-codebase-architecture`.

## Common Pitfalls

1. **Documenting too early.** Only write docs after language or decisions have stabilized.
2. **Burying domain language in implementation details.** CONTEXT.md is for domain experts and future agents, not call graphs.
3. **Creating ADRs for everything.** ADRs are for durable trade-offs, not routine implementation choices.
4. **Ignoring existing ADRs.** Read them before proposing conflicting architecture.
5. **Batching questions.** One question at a time keeps the design tree adaptive.

## Verification Checklist

- [ ] Relevant CONTEXT/ADR/project docs were checked.
- [ ] Code was inspected where it could answer a question.
- [ ] Each question had a recommendation.
- [ ] Any docs written were durable, English-only, and scoped correctly.
- [ ] ADRs were proposed only for hard-to-reverse trade-offs.
