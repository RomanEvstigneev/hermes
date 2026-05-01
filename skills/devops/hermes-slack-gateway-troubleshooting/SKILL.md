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
HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python3 - <<'PY'
import sys
sys.path.insert(0, '/opt/hermes')
from gateway.status import release_all_scoped_locks, _get_lock_dir
print('lock_dir', _get_lock_dir())
print('removed_locks', release_all_scoped_locks())
PY

HERMES_HOME=/opt/data nohup /opt/hermes/.venv/bin/hermes gateway run >> /opt/data/logs/gateway.log 2>&1 &
```

Then verify:

```bash
ps -ef | grep -E 'hermes.*gateway run|gateway.*run' | grep -v grep
/usr/local/bin/hermes gateway status 2>&1 || true
cat /opt/data/gateway_state.json
```

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

Roman's container launches Hermes from `/opt/hermes` via `/opt/hermes/.venv/bin/hermes`, while `/usr/local/bin/hermes` may use a different installed source tree. Because cwd can affect `sys.path`, two `hermes gateway status` commands may disagree.

Observed pitfall:

- `/usr/local/bin/hermes gateway status` correctly reported the manually started gateway running.
- `/opt/hermes/.venv/bin/hermes gateway status` falsely reported stopped.
- `/opt/data/gateway_state.json` and `ps` confirmed the gateway was running and Slack was connected.

When outputs disagree, trust the combination of:

1. live `ps` process check,
2. `/opt/data/gateway_state.json`,
3. the same runtime path that launched the gateway,
4. actual Slack auth/connectivity logs.

## Report format

Tell the user:

- whether the gateway is running,
- Slack platform state,
- root cause if found,
- what was changed,
- any caveat such as path/version mismatch.

Do not expose Slack tokens or secrets in the final response.