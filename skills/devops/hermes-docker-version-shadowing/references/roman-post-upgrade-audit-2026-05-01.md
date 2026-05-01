# Roman Docker Hermes post-upgrade audit — 2026-05-01

Use this as a concrete reference for future Docker upgrade/deadcode reviews.

## Situation

- Active CLI resolved to `/usr/local/bin/hermes`.
- Active project was `/usr/local/lib/hermes-agent`.
- Current version was Hermes Agent v0.12.0.
- Stale old runtime still existed at `/opt/hermes` and reported Hermes Agent v0.9.0.
- `/hermes.sh` had already been fixed to reset PATH, unset `TERMINAL_CWD`, cd to `/usr/local/lib/hermes-agent`, and launch `/usr/local/bin/hermes`.

## Diagnostics that mattered

```bash
command -v hermes
which -a hermes
/usr/local/bin/hermes --version
/opt/hermes/.venv/bin/hermes --version 2>&1 || true
ps -eo pid,ppid,stat,etime,cmd | grep -E '[h]ermes|[t]tyd'
tr '\0' '\n' < /proc/1/environ | grep -E '^(PATH|HERMES_HOME|TERMINAL_CWD|PLAYWRIGHT_BROWSERS_PATH)='
nl -ba /hermes.sh | sed -n '1,80p'
HERMES_HOME=/opt/data /usr/local/bin/hermes gateway status 2>&1 || true
cat /opt/data/gateway_state.json 2>/dev/null || true
```

## Findings

- `/opt/hermes` was dead for active Python imports, but not safe to delete immediately.
- PID 1 still had `PATH=/opt/hermes/.venv/bin:...` from container startup.
- PID 1 also had `PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright`.
- `/opt/hermes/.playwright` was about 631 MB and contained browser binaries.
- Therefore cleanup should migrate browser cache/environment first, then restart the container, then quarantine `/opt/hermes`.

## Gateway stale-lock incident

Gateway state showed Slack startup failed with:

```text
Slack app token already in use (PID 12). Stop the other gateway first.
```

PID 12 was a zombie `[hermes] <defunct>`, so the lock was stale.

Fix used:

```bash
HERMES_HOME=/opt/data /usr/local/lib/hermes-agent/venv/bin/python3 - <<'PY'
import sys
sys.path.insert(0, '/usr/local/lib/hermes-agent')
from gateway.status import release_all_scoped_locks, _get_lock_dir
print('Lock dir:', _get_lock_dir())
print('Released:', release_all_scoped_locks())
PY
```

Then the gateway was restarted from the modern runtime:

```bash
HERMES_HOME=/opt/data /usr/local/bin/hermes gateway run
```

Verification showed:

- `/usr/local/bin/hermes gateway status` -> running.
- `/opt/data/gateway_state.json` -> `gateway_state=running`, Slack `state=connected`.
- Gateway process cwd -> `/usr/local/lib/hermes-agent`.
- Gateway process PATH -> no `/opt/hermes/.venv/bin`.

## Cleanup guidance

Recommended order:

1. Migrate/reinstall Playwright browsers outside `/opt/hermes` or update `PLAYWRIGHT_BROWSERS_PATH`.
2. Restart the container from the Docker host so PID 1 environment is clean.
3. Quarantine first: `mv /opt/hermes /opt/hermes.old-v0.9.0`.
4. Verify CLI, gateway, Slack, cron, and browser tools.
5. Delete the quarantine only after a safe window.

Also remove stale temp PID files when found, for example `/tmp/hermes_gateway_started.pid` pointing at a dead process.
