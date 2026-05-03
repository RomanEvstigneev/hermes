# Post-session knowledge audit for Slack sessions

Use this reference when adding or troubleshooting Hermes features that audit durable knowledge changes after messaging-platform sessions.

## Pattern

Implement as a built-in gateway hook when the feature needs session lifecycle context and platform delivery access.

1. Add a module under `gateway/builtin_hooks/`.
2. Capture a baseline at session start.
3. Compare the baseline to current state at session finalization/reset.
4. Send a notification only when watched durable files changed.
5. Keep Slack summaries concise and sanitized: no raw transcript, no raw diff, no secrets, no credentials.
6. Write detailed local audit logs under `$HERMES_HOME/logs/...` or `/opt/data/logs/...` depending on the active Hermes home.
7. Store runtime baseline state under `$HERMES_HOME/state/...`.
8. Add gateway lifecycle calls in `gateway/run.py` for new-session and finalization/reset paths.
9. Add tests covering changed-file notification, no-change silence, skipped users/platforms, and secret redaction.

## Roman's current deployment

Hermes data/config home is `/opt/data`. The Slack post-session audit config lives in `/opt/data/config.yaml`:

```yaml
post_session_audit:
  enabled: true
  notify_chat_id: D0B0P5BAQSF
  skip_user_ids:
  - U09NJ1H6V6K
  watched_paths:
  - memories
  - memory
  - skills
  - cron/jobs.json
  - scripts
```

The implementation files are:

- `/usr/local/lib/hermes-agent/gateway/builtin_hooks/post_session_knowledge_audit.py`
- `/usr/local/lib/hermes-agent/gateway/run.py`
- `/usr/local/lib/hermes-agent/tests/gateway/test_post_session_knowledge_audit.py`

The configured Roman DM channel ID and Slack user IDs are identifiers, not credentials. Never quote Slack tokens or app tokens.

## Review caveats

When reviewing this feature, explicitly verify these edge cases:

- `SessionStore.get_or_create_session()` can auto-reset an expired or suspended session before caller code sees the old `SessionEntry`; the gateway wrapper should pre-finalize the old audit baseline before calling it.
- If the Slack adapter is missing or a DM send fails at finalize time, keep a sanitized pending notification in state and retry it later; do not mark the audit as reported until the DM succeeds.
- Keep detailed operational event logs for every decision under `$HERMES_HOME/logs/post_session_knowledge_audit/events/YYYY-MM-DD.jsonl`.
- Overlapping Slack sessions share the same watched filesystem, so changed-file attribution is best-effort unless additional per-session attribution is added.

## Operational inspection

When asked for the latest post-session audit result in Roman's deployment, check both state and event logs; do not infer from memory alone.

Key files:

- `/opt/data/state/post_session_knowledge_audit.json` — per-session baseline/report state.
- `/opt/data/logs/post_session_knowledge_audit/events/YYYY-MM-DD.jsonl` — operational lifecycle events.
- Audit detail JSON files are written only when a watched-file diff exists and the finalizer reaches the notification path; absence of detail JSON can be normal for baseline-only or no-change sessions.

Result interpretation:

- `baseline_captured` with `reported_at: null`, `reported_reason: null`, and `last_finalized_at: null` means the audit has only captured the starting manifest; there is no final result yet.
- `reported_reason: no_changes` means the session finalized and no watched files changed; no Slack DM is sent.
- `notification_sent` / `reported_reason: sent` means a DM was delivered to the configured notify chat.
- `notification_pending` with `reported_reason: slack_adapter_missing` or `send_failed` means changes were detected but DM delivery is pending/retryable; inspect `pending_log_path`, `pending_changed_count`, and `last_error`.

Useful one-shot probe:

```bash
python - <<'PY'
import glob, json
from pathlib import Path
state = json.loads(Path('/opt/data/state/post_session_knowledge_audit.json').read_text())
rows = []
for sid, rec in state.get('sessions', {}).items():
    rows.append({k: rec.get(k) for k in [
        'session_id', 'user_id', 'user_name', 'chat_id', 'thread_id',
        'started_at', 'reported_at', 'reported_reason', 'last_finalized_at',
        'last_log_path', 'pending_changed_count', 'last_error'
    ]})
rows.sort(key=lambda r: (r.get('last_finalized_at') or r.get('reported_at') or r.get('started_at') or ''))
print(json.dumps(rows[-10:], indent=2))
for p in sorted(glob.glob('/opt/data/logs/post_session_knowledge_audit/events/*.jsonl'))[-3:]:
    lines = Path(p).read_text().splitlines()
    print('\n' + p, 'lines', len(lines))
    for line in lines[-10:]:
        print(line)
PY
```

## Verification

Preferred:

```bash
scripts/run_tests.sh tests/gateway/test_session_boundary_hooks.py tests/gateway/test_post_session_knowledge_audit.py -q
```

Fallback only if the wrapper is blocked by the local venv missing packaging tools:

```bash
./venv/bin/python -m pytest tests/gateway/test_session_boundary_hooks.py tests/gateway/test_post_session_knowledge_audit.py -q -o 'addopts='
./venv/bin/python -m py_compile gateway/builtin_hooks/post_session_knowledge_audit.py gateway/run.py
```

Treat fallback pytest as narrow verification, not CI-equivalent.

## Operational caveats

- Code/config changes do not affect the running gateway until it restarts.
- If `hermes gateway restart` is blocked by approval policy, do not retry automatically; report that the running gateway is still on old code and ask the operator to restart it manually.
- In Docker/container deployments, `hermes gateway install --system` may correctly refuse with `Service installation is not needed inside a Docker container`; systemd may be unavailable and PID 1 may be a wrapper such as `ttyd` running `/hermes.sh`. Treat the container runtime as the service manager: configure the host with `docker update --restart unless-stopped <container>` or start the container with `--restart unless-stopped`. Inside the container, restart the manual gateway process only to activate code changes.
- On Roman's current container, `/hermes.sh` exports `HERMES_HOME=/opt/data`, sets `PLAYWRIGHT_BROWSERS_PATH=/opt/data/cache/ms-playwright`, changes to `/usr/local/lib/hermes-agent`, logs to `/opt/data/logs/gateway_restarts.log`, and starts `hermes gateway run` in the background before launching the interactive CLI. Preserve those environment/path details when manually restarting the gateway.
- If the daily backup is blocked by GitHub push protection, do not push until exposed values are removed from commit history and any valid leaked token is rotated.
