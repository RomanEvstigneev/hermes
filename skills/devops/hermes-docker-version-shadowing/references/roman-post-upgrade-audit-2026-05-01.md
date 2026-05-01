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
2. If PID 1 still has old inherited environment and cannot be restarted immediately, keep `/opt/hermes` as a compatibility shim rather than removing the path entirely. Example:

```bash
TS=$(date -u +%Y%m%d-%H%M%S)
NEW=/opt/data/cache/ms-playwright
mkdir -p "$NEW"
rsync -a /opt/hermes/.playwright/ "$NEW"/ 2>/dev/null || cp -a /opt/hermes/.playwright/. "$NEW"/
QUAR=/opt/hermes.old-v0.9.0-$TS
mv /opt/hermes "$QUAR"
mkdir -p /opt/hermes
ln -s "$NEW" /opt/hermes/.playwright
cat > /opt/hermes/README.txt <<EOF
Compatibility shim after Hermes migration. Old runtime moved to: $QUAR
Only .playwright remains as a symlink to $NEW until the container is restarted.
EOF
```

3. Update `/hermes.sh` for future starts:

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/data/cache/ms-playwright
```

4. Restart the container from the Docker host so PID 1 environment is clean.
5. Verify CLI, gateway, Slack, cron, and browser tools. Use a browser smoke test if Playwright was moved.
6. Delete the quarantine only after a safe window.

Also remove stale temp PID files when found, for example `/tmp/hermes_gateway_started.pid` pointing at a dead process.

## Data repo backup pitfall

If `/opt/data` is version-controlled, do not let migration artifacts or browser caches enter the repo. Moving Playwright to `/opt/data/cache/ms-playwright` and keeping upgrade bundles under `/opt/data/backups` can accidentally create a huge commit and make `git push` fail with HTTP/RPC errors. Ensure `.gitignore` and any daily backup script exclude at least:

```gitignore
cache/
backups/
kanban.db
gateway.pid
gateway_state.json
processes.json
channel_directory.json
pastes/
__pycache__/
*.pyc
```

If a huge accidental commit is created before push, use `git reset --mixed HEAD~1`, fix ignores, then recommit only the meaningful config/skill/memory changes.

## Follow-up audit result later the same day

A later read-only audit found the migration stable:

- `/usr/local/bin/hermes --version` and bare `hermes --version` both reported Hermes Agent v0.12.0 with project `/usr/local/lib/hermes-agent`.
- Live gateway and CLI processes had cwd `/usr/local/lib/hermes-agent` and command lines under `/usr/local/bin/hermes` / `/usr/local/lib/hermes-agent/venv/bin/python3`.
- `/hermes.sh` set `HERMES_HOME=/opt/data`, reset PATH, set `PLAYWRIGHT_BROWSERS_PATH=/opt/data/cache/ms-playwright`, unset `TERMINAL_CWD`, cd'd to `/usr/local/lib/hermes-agent`, and launched `/usr/local/bin/hermes` explicitly.
- PID 1 still had inherited old values (`PATH` containing `/opt/hermes/.venv/bin` and `PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright`), so the tiny `/opt/hermes` compatibility shim was still worth keeping until a container restart.
- `/opt/hermes` contained only `README.txt` and `.playwright -> /opt/data/cache/ms-playwright`; no Python shadow files remained there.
- `/opt/hermes.old-v0.9.0-20260501-070339` remained as a 1.6 GB quarantine and was safe to delete after a safe window because no active process used it.
- Gateway state showed Slack connected on PID 12; old `Slack app token already in use` log lines were historical, not current health failures.
- Config version was 23; `hermes config check`, `hermes doctor`, `hermes status --all`, `hermes gateway status`, and `hermes cron list` were healthy enough for normal operation.
- Bare `python` was not available in this container, and system `python3` lacked `yaml`; use `/usr/local/lib/hermes-agent/venv/bin/python3` for Python inspection scripts that depend on Hermes environment packages.