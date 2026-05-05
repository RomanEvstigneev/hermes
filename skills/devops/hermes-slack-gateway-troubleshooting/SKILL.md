---
name: hermes-slack-gateway-troubleshooting
description: Troubleshoot Hermes Slack gateway connection failures, especially stale token locks and Docker/runtime path mismatches.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, slack, gateway, docker, troubleshooting]
---

# Hermes Slack Gateway Troubleshooting

Use this when the user asks whether Slack is connected, Hermes is not responding in Slack, or `hermes gateway status` reports Slack/gateway problems.

## Diagnostic workflow

1. Check live processes and gateway health:
   ```bash
   date
   ps -ef | grep -E 'hermes|slack|gateway' | grep -v grep
   hermes gateway status 2>&1 || true
   hermes status --all 2>&1 || true
   ```

2. Locate config, env, and logs:
   ```bash
   hermes config path
   hermes config env-path
   tail -n 100 /opt/data/logs/gateway.log
   cat /opt/data/gateway_state.json
   ```

3. Verify Slack credentials are present without exposing secrets. Print only lengths, prefixes, or hashes. Do not print full tokens.

4. If needed, verify Slack bot token with `auth.test`, but never print token values.

## Stale Slack app-token lock fix

Symptom:

```text
Slack app token already in use (PID <pid>). Stop the other gateway first.
```

But the referenced PID is not a live gateway; for example:

```bash
ps -o pid,ppid,stat,lstart,cmd -p <pid>
# STAT includes Z, command is [hermes] <defunct>
```

This means a stale scoped lock is blocking Slack startup. Clear scoped gateway locks and restart the gateway:

```bash
HERMES_HOME=/opt/data /usr/local/lib/hermes-agent/venv/bin/python3 - <<'PY'
import sys
sys.path.insert(0, '/usr/local/lib/hermes-agent')
from gateway.status import release_all_scoped_locks, _get_lock_dir
print('Lock dir:', _get_lock_dir())
print('Released:', release_all_scoped_locks())
PY
HERMES_HOME=/opt/data /usr/local/bin/hermes gateway run

# If launching from an agent tool session, start it as a tracked background process with the terminal tool rather than using shell-level nohup/disown. Do not use the stale /opt/hermes launcher.
```

Then verify from the same modern runtime that launched the gateway, and also check cron because a stopped gateway prevents scheduled jobs from firing:

```bash
ps -ef | grep -E 'hermes.*gateway run|gateway.*run' | grep -v grep
HERMES_HOME=/opt/data /usr/local/bin/hermes gateway status 2>&1 || true
cat /opt/data/gateway_state.json
HERMES_HOME=/opt/data /usr/local/bin/hermes cron list 2>&1 || true
grep -Ei 'slack|connected|token already|gateway running' /opt/data/logs/gateway.log | tail -30 || true
```

If the user asked for an operational review or incident follow-up, append an English-only note to `/opt/data/logs/incident_log.md` with summary, root cause, actions, verification, and follow-up. Include the stale PID, whether it was zombie/defunct, the runtime used to clear locks, the new gateway PID, Slack state, and the recommendation to restart the Docker container from the host when PID 1 still has inherited old `/opt/hermes` cwd/env.

Expected state file shape:

```json
{
  "gateway_state": "running",
  "platforms": {
    "slack": {
      "state": "connected",
      "error_code": null,
      "error_message": null
    }
  }
}
```

## Roman's Docker/runtime path pitfall

Roman's container previously launched Hermes from `/opt/hermes` via `/opt/hermes/.venv/bin/hermes`, while `/usr/local/bin/hermes` used a different installed source tree. The intended post-upgrade setup is `/hermes.sh` launching `/usr/local/bin/hermes` after `cd /usr/local/lib/hermes-agent`; if cwd stays `/opt/hermes`, Python can still import stale modules because cwd is first on `sys.path`.

Observed pitfall:

- `/usr/local/bin/hermes gateway status` correctly reported the manually started gateway running.
- `/opt/hermes/.venv/bin/hermes gateway status` falsely reported stopped.
- `/opt/data/gateway_state.json` and `ps` confirmed the gateway was running and Slack was connected.

When outputs disagree, trust the combination of:

1. live `ps` process check,
2. `/opt/data/gateway_state.json`,
3. the same runtime path that launched the gateway,
4. actual Slack auth/connectivity logs.

## Duplicate gateway starts — false positive in health report

The daily `cron_health_report.py` scans logs for `Another gateway instance is already running`.
This can fire legitimately when the container is restarted (Docker `--restart unless-stopped`
brings the gateway back while a stale entry lingers), but the **new gateway proceeds fine**.

Signs it's a false positive, not a real problem:
- `gateway_state.json` shows `state: running`, `slack.state: connected`
- `ps` shows exactly one `hermes gateway run` process
- The `gateway_restarts.log` shows `GATEWAY START SKIPPED | already_running_pid=<N>`
  meaning `/hermes.sh` detected an existing healthy gateway and exited cleanly

Signs it's a real problem:
- Two `hermes gateway run` processes in `ps`
- Slack delivery errors in `gateway.log`
- `gateway_state.json` shows `slack.state: error`

The sentinel (`gateway_cron_sentinel.py`) makes this distinction at the process level
rather than just log pattern matching — use its JSONL output to confirm.

## `shutdown_noise_events` — CLI-origin vs gateway-origin (critical distinction)

`errors.log` will contain lines like:
```
ERROR asyncio: unhandled exception during asyncio.run() shutdown
ERROR asyncio: Task exception was never retrieved
KeyboardInterrupt
OSError: [Errno 5] Input/output error
```

These come from two very different sources:

**CLI-origin (benign):** Interactive `hermes` sessions launched via ttyd/pts. When
a user closes a browser tab or the PTY disconnects, `cli.py _signal_handler` raises
`KeyboardInterrupt` inside asyncio — generating a traceback block that references
`cli.py` at line `_signal_handler`. These are NOT gateway problems.

**Gateway-origin (real issue):** The same exception pattern but originating from
`gateway/run.py` — indicates an unclean gateway shutdown that needs investigation.

### How to distinguish them

Look at the full traceback block for the first `errors.log` entry with a timestamp.
If any line matches `cli.py.*_signal_handler` or `_signal_handler.*cli.py` → CLI-origin, ignore.
If the traceback frames point to `gateway/run.py` → real gateway issue.

The sentinel script (`/opt/data/scripts/gateway_cron_sentinel.py`) implements this
as a block-scoped exclude filter — see `references/sentinel-cli-noise-filter.md` for
the exact implementation pattern and verification steps.

### Sentinel false-positive scenario (seen 2026-05-04)

11 `shutdown_noise` events in 20 minutes triggered a WARNING alert. Root cause:
user closed ttyd tabs repeatedly during the afternoon. Gateway PID 13581 ran
continuously without interruption; Slack stayed connected; 34/34 crons succeeded.
All 14 traceback blocks in the relevant window contained `cli.py _signal_handler` —
confirmed 0 gateway-origin hits after applying the block filter.

**Do not treat shutdown_noise count alone as a gateway health signal.** Always
cross-check with:
1. Gateway process still running (`ps`, sentinel `process.count`)
2. `gateway.log` has no disconnect/restart events in the window
3. `gateway_state.json` shows `slack.state: connected`

## Gateway restart — wrapper does NOT auto-loop

The bash wrapper process (spawned by ttyd/hermes.sh, stat `Ss`) exec's the gateway
once — it does NOT loop-restart on exit. Killing the gateway Python process (the
canonical `Sl` child) leaves the wrapper as a dead shell with no live child.

**If you kill the gateway for any reason (SIGTERM, restart after code change, etc.),
you must manually relaunch it:**

```bash
# Start as a background process (use terminal(background=True) from agent code):
cd /usr/local/lib/hermes-agent && \
  export HERMES_HOME=/opt/data PLAYWRIGHT_BROWSERS_PATH=/opt/data/cache/ms-playwright && \
  unset TERMINAL_CWD && \
  /usr/local/bin/hermes gateway run
```

Watch for `✓ slack connected` and `Cron ticker started` in gateway.log to confirm.

This is also why `--restart unless-stopped` on the Docker container is the real
auto-restart mechanism — the container restart policy re-runs the full entrypoint
(`/hermes.sh`), which launches a fresh gateway. A SIGTERM to just the gateway Python
PID does not trigger a container restart.

## Report format

Tell the user:

- whether the gateway is running,
- Slack platform state,
- root cause if found,
- what was changed,
- any caveat such as path/version mismatch.

Do not expose Slack tokens or secrets in the final response.