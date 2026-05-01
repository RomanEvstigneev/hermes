---
name: hermes-runtime-path-debugging
description: Verify which Hermes source tree and TUI implementation a live process is actually using before patching or diagnosing missing code changes.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, debugging, runtime, docker, tui]
    related_skills: [hermes-agent, systematic-debugging]
---

# Hermes Runtime Path Debugging

Use this when a Hermes code change appears correct but is not visible in the running CLI, TUI, gateway, or Docker container.

## Key lesson

Do not assume the live `hermes` process imports from the repository you edited. In Docker/custom installs, the active process may run from one tree while you patch another. For example, a container may launch `/opt/hermes/.venv/bin/hermes` with cwd `/opt/hermes`, so Python imports `/opt/hermes/cli.py` first even if edits were made under `/usr/local/lib/hermes-agent`.

Also verify which TUI is active:
- Classic prompt_toolkit TUI/status bar: `cli.py`
- Ink/ui-tui status bar: `ui-tui/src/...` with backend `tui_gateway/server.py`

## Procedure

1. Identify live Hermes processes:

```bash
ps -ef | grep -E 'hermes|tui_gateway' | grep -v grep
```

2. Check the live process working directory and command line:

```bash
pwdx <pid>
tr '\0' ' ' < /proc/<pid>/cmdline; echo
```

3. Check relevant runtime environment:

```bash
tr '\0' '\n' < /proc/<pid>/environ | grep -E 'PYTHONPATH|HERMES|PATH'
```

4. Ask Python which files it imports from the same environment/venv used by the process:

```bash
python - <<'PY'
import sys
print('sys.path first:', sys.path[:5])
try:
    import hermes_cli
    print('hermes_cli:', hermes_cli.__file__)
except Exception as e:
    print('hermes_cli import failed:', e)
try:
    import tui_gateway.server as s
    print('tui_gateway.server:', s.__file__)
except Exception as e:
    print('tui_gateway.server import failed:', e)
PY
```

Use the same interpreter as the process when possible, e.g. `/opt/hermes/.venv/bin/python`.

5. Compare import paths to the files you edited.

If they differ, either:
- patch the active tree, or
- change the launcher/entrypoint to run the intended checkout, then restart Hermes.

6. Restart the relevant process after code edits:
- CLI/TUI: exit and relaunch.
- Gateway: restart the gateway process/container.

## Common symptom pattern

A backend/API check works in a one-off script, but the UI still does not show it. Before changing logic, verify whether the current UI path is classic `cli.py` or Ink `ui-tui`, and verify the active import path.

## Verification

After patching the active path, run the smallest direct check first:

```bash
python -m py_compile path/to/changed_file.py
```

Then run targeted tests or a focused one-off script that imports the live module path and exercises the changed function.
