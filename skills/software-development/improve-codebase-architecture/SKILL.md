---
name: improve-codebase-architecture
description: "Use when the user wants to improve architecture, find refactoring opportunities, consolidate shallow modules, make a codebase easier to test, or reduce AI navigation friction. Finds deepening opportunities using domain language, ADRs, interface depth, seams, adapters, locality, and leverage."
version: 1.0.0
author: Hermes Agent (adapted from Matt Pocock)
license: MIT
metadata:
  hermes:
    tags: [architecture, refactoring, code-quality, testability, design]
    related_skills: [grill-with-docs, test-driven-development, systematic-debugging, writing-plans, codebase-inspection]
---

# Improve Codebase Architecture

## Overview

Surface architectural friction and propose deepening opportunities: refactors that move complexity behind smaller, more useful interfaces. The goal is better locality, leverage, testability, and agent navigability.

Do not start by proposing code. First understand the domain language, relevant decisions, and where the current design causes friction.

## When to Use

Use when the user asks to:
- Improve architecture or codebase design.
- Find refactoring opportunities.
- Consolidate tangled or tightly coupled modules.
- Make code easier to test or reason about.
- Recover from a "ball of mud" created by fast agent-driven development.
- Review a subsystem before a major feature or migration.

Do not use for a single straightforward bug unless repeated fixes suggest an architectural problem; use `systematic-debugging` first.

## Vocabulary

Use these terms consistently:
- **Module** — anything with an interface and implementation: function, class, package, service, slice, or subsystem.
- **Interface** — everything callers must know: methods, types, invariants, errors, ordering, configuration, and lifecycle.
- **Implementation** — code hidden behind the interface.
- **Depth** — how much useful behavior sits behind a small interface. Deep modules are high leverage; shallow modules expose complexity without hiding much.
- **Seam** — a place where behavior can vary without editing callers.
- **Adapter** — a concrete implementation at a seam.
- **Locality** — how concentrated the knowledge and change surface are.
- **Leverage** — the value callers get from a module relative to what they must know.

Key tests:
- **Deletion test**: if deleting the module makes complexity disappear, it was likely pass-through; if complexity reappears across many callers, it was earning its keep.
- **Adapter test**: one adapter may be a hypothetical seam; two adapters often prove a real seam.
- **Test-surface test**: the best interface is often the best place to test behavior.

## Workflow

### 1. Read context and decisions

Before judging architecture, inspect:
- `CONTEXT.md` / `CONTEXT-MAP.md` for domain language.
- Relevant `docs/adr/` files.
- AGENTS.md/README/project docs.
- Existing tests around the subsystem.

Respect existing ADRs. If friction justifies reopening one, mark that explicitly instead of silently contradicting it.

### 2. Explore friction organically

Use file/search/terminal tools to map the area. Look for:
- One concept requiring jumps across many small modules.
- Shallow wrappers whose interface is almost as complex as their implementation.
- Pure functions extracted only for tests while real bugs live in orchestration.
- Tight coupling that leaks through seams.
- Repeated parameter bundles or duplicated invariants.
- Tests that mock internals because the real interface is hard to use.
- Modules with only one adapter despite an elaborate abstraction.

### 3. Present candidates, not final designs

Provide a numbered list of deepening candidates. For each:
- **Files/modules** — exact paths and names.
- **Friction** — the observed pain.
- **Deepening move** — the plain-English architectural change.
- **Benefits** — locality, leverage, testability, and future-agent navigability.
- **Risk** — migration cost, coupling, or ADR conflict.

Do not propose final interfaces yet. Ask which candidate the user wants to explore.

### 4. Grill the selected candidate

Once the user chooses one candidate, use `grill-with-docs` behavior:
- Resolve constraints and invariants one question at a time.
- Use domain vocabulary from CONTEXT.md.
- Update glossary terms when they crystallize and documentation writes are in scope.
- Offer ADRs only for durable trade-offs.

### 5. Turn architecture into work

After agreement, recommend one of:
- `writing-plans` for an implementation plan.
- `to-issues` for vertical-slice issue breakdown.
- `test-driven-development` for a narrow TDD refactor.
- `spike` if the design is uncertain and needs a throwaway experiment.

## Candidate Output Template

```
1. <Candidate title>
   Files/modules: <paths>
   Friction: <specific evidence>
   Deepening move: <plain English>
   Benefits: <locality/leverage/testability>
   Risks: <migration/ADR/confidence>
```

## Common Pitfalls

1. **Renaming as architecture.** Better names help, but deepening means hiding complexity behind a stronger interface.
2. **Creating hypothetical seams.** If there is only one adapter and no foreseeable second, the seam may be ceremony.
3. **Optimizing for tests over users.** Testability follows from good interfaces; do not fragment modules only to mock them.
4. **Ignoring domain language.** Good seams usually align with domain concepts, not arbitrary technical layers.
5. **Big-bang refactors.** Prefer thin, reversible vertical slices with tests.

## Verification Checklist

- [ ] Existing domain docs and ADRs were inspected.
- [ ] Candidates cite concrete files and observed friction.
- [ ] Benefits are stated in locality, leverage, and testability terms.
- [ ] ADR conflicts are explicit.
- [ ] User chose a candidate before final interface design.
- [ ] Next work is framed as a plan, issues, TDD refactor, or spike.
