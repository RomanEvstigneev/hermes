---
name: tdd
description: "Use when the user invokes TDD, asks for red-green-refactor, wants test-first development, or asks to build or fix behavior one vertical slice at a time. Loads the Hermes test-driven-development discipline with additional interface, mocking, deep-module, and slice guidance."
version: 1.0.0
author: Hermes Agent (adapted from Matt Pocock)
license: MIT
metadata:
  hermes:
    tags: [tdd, testing, red-green-refactor, testability, vertical-slices]
    related_skills: [test-driven-development, systematic-debugging, improve-codebase-architecture]
---

# TDD

## Overview

This is the short-name entrypoint for Hermes test-driven development. Follow `test-driven-development` strictly: write a failing test first, watch it fail for the expected reason, write minimal code to pass, then refactor while green.

This skill adds the Matt Pocock-style emphasis on vertical slices, interface design, deep modules, and behavior-focused tests.

## When to Use

Use when the user says:
- `tdd`
- "red-green-refactor"
- "test-first"
- "build this with tests first"
- "fix this with a regression test"
- "one vertical slice at a time"

For bugs, combine with `systematic-debugging`: understand the root cause, encode it as a failing regression test, then fix.

## Workflow

### 1. Plan the next behavior only

Do not design the whole test suite in bulk. Pick one externally observable behavior for the next vertical slice.

Confirm or infer:
- Interface to exercise.
- Behavior to prove.
- Expected output or externally visible effect.
- Existing test style and command.

### 2. RED

Write one failing test through the public interface. Run only the focused test and confirm it fails for the expected reason.

### 3. GREEN

Write only enough production code to pass the current test. Do not anticipate future tests.

### 4. REFACTOR

While tests are green:
- Remove duplication.
- Simplify names and interfaces.
- Move complexity behind deeper modules.
- Keep behavior unchanged.

Run the focused test after each refactor step, then the relevant broader suite.

## Good Test Rules

Good tests:
- Test observable behavior that users or callers care about.
- Use public interfaces.
- Survive internal refactors.
- Describe what the system does, not how internals collaborate.
- Prefer real collaborators when practical.

Bad tests:
- Mock internal collaborators just to assert call counts.
- Test private methods or implementation structure.
- Pass while the user-visible behavior is broken.
- Fail when internals are refactored without behavior change.

## Interface Design for Testability

If the test is hard to write, listen to it. Hard-to-test code is often hard-to-use code.

Prefer:
- Small public interfaces with meaningful behavior behind them.
- Dependency injection at real seams.
- Adapters for I/O boundaries.
- Tests at the interface that owns the behavior.

Avoid:
- Extracting shallow pure functions only to make mocking easy.
- Passing many flags/config objects that expose implementation complexity.
- Creating abstractions with only one adapter and no real variation.

## Deep Module Heuristic

A deep module has a small interface and a substantial implementation hidden behind it. A shallow module has a large interface and little implementation.

When refactoring during TDD, ask:
- Can this interface have fewer methods?
- Can parameters become simpler or more domain-shaped?
- Can invariants move behind the interface?
- Can tests verify behavior through this interface instead of reaching inside?

## Verification Checklist

- [ ] A failing test was written before production code.
- [ ] The failure reason was expected and meaningful.
- [ ] The implementation was minimal for the current behavior.
- [ ] Tests verify public behavior, not internals.
- [ ] Refactoring happened only while green.
- [ ] Final focused and relevant broader tests passed.
