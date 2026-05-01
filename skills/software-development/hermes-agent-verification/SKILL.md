---
name: hermes-agent-verification
description: Verify Hermes Agent code edits, especially TUI/backend changes, using the repo's preferred Python and frontend checks.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, testing, verification, tui, code-review]
    related_skills: [hermes-agent]
---

# Hermes Agent Verification

Use this when reviewing or validating edits in the Hermes Agent repository, especially changes touching `tui_gateway/`, `agent/`, `ui-tui/`, or tests.

## Procedure

1. Start with git context:
   ```bash
   git status --short
   git diff --stat
   git diff --check
   git diff -- <relevant files>
   ```

2. For Python checks, prefer the repo virtualenv. Some deployments do not have `python` on PATH, and system `python3` may not have pytest installed.
   ```bash
   if [ -x .venv/bin/python ]; then PY=.venv/bin/python; elif [ -x venv/bin/python ]; then PY=venv/bin/python; else PY=python3; fi
   $PY -m py_compile path/to/file.py other/file.py
   $PY -m pytest relevant/test_file.py -q -o 'addopts='
   ```

3. For TUI frontend checks:
   ```bash
   cd ui-tui
   npm run type-check
   npm run build
   ```

4. Lint is useful, but existing unrelated lint failures can appear. If `npm run lint -- --quiet` fails, inspect whether failures are in touched files before treating them as blockers.

5. For TUI usage/status-bar changes, verify the data path end-to-end:
   - Backend method returns fields from `tui_gateway/server.py` usage payload.
   - TypeScript response and UI state interfaces include the new fields.
   - Event/RPC handlers preserve existing usage fields when merging.
   - The status bar component renders compact data and does not break when fields are absent.
   - Slash command output, such as `/usage`, includes detailed lines when applicable.

## Pitfalls

- `python -m pytest` may fail with `python: command not found`; use `.venv/bin/python` or `python3`.
- System `python3` may not have pytest; use the repo venv for tests.
- Lockfile diffs can be large and unrelated. Flag unexpected `package-lock.json` churn separately from feature logic.
- `git diff --check` only catches whitespace/conflict-marker problems; still run syntax/type/build checks.
