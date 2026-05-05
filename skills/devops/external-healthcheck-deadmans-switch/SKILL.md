---
name: external-healthcheck-deadmans-switch
description: Set up and maintain an external dead-man's switch (healthchecks.io) so a process that dies gets flagged via email even when its own alert delivery channel (Slack) is also down.
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [hermes, gateway, monitoring, healthcheck, deadmans-switch, ops]
---

# External Healthcheck / Dead-Man's Switch

## Why this matters

A self-monitoring system has a fundamental blind spot: if the process that sends
alerts is the same process that died, no alert goes out. For Hermes this means:

```
gateway dead
  → cron scheduler dead (embedded in gateway)
    → sentinel script never runs
      → no Slack alert
        → Roman sees silence, not an error
```

The fix is a dead-man's switch: the gateway pings an EXTERNAL service every N minutes.
If pings stop, the external service sends an alert via an independent channel (email).

## Hermes implementation (as of 2026-05-04)

### Ping endpoint
- Service: healthchecks.io (free tier)
- Ping URL stored in config: `gateway.healthcheck_ping_url`
- Config path: `/opt/data/config.yaml`

```yaml
gateway:
  healthcheck_ping_url: "https://hc-ping.com/<uuid>"
  healthcheck_interval_ticks: 5   # every 5 cron-ticker ticks = 5 minutes
```

### Code location
`/usr/local/lib/hermes-agent/gateway/run.py` — inside `_start_cron_ticker()`.
Runs every `HEALTHCHECK_EVERY = 5` ticks using stdlib `urllib.request` (no deps).

```python
HEALTHCHECK_EVERY = 5  # ticks

if tick_count % HEALTHCHECK_EVERY == 0:
    try:
        import os as _os, urllib.request as _urllib_req
        _cfg = {}
        try:
            import yaml as _yaml
            _cfg_path = _os.path.join(_os.getenv("HERMES_HOME", "/opt/data"), "config.yaml")
            with open(_cfg_path, encoding="utf-8") as _f:
                _cfg = _yaml.safe_load(_f) or {}
        except Exception:
            pass
        _gw_cfg = _cfg.get("gateway") or {}
        _ping_url = _gw_cfg.get("healthcheck_ping_url") or _os.getenv("HERMES_HEALTHCHECK_URL", "")
        if _ping_url:
            _req = _urllib_req.Request(_ping_url, method="GET")
            _req.add_header("User-Agent", "hermes-gateway/healthcheck")
            with _urllib_req.urlopen(_req, timeout=10) as _resp:
                _status = _resp.status
            if _status != 200:
                logger.warning("Healthcheck ping returned HTTP %s", _status)
            else:
                logger.info("Healthcheck ping OK (HTTP %s)", _status)
    except Exception as _e:
        logger.warning("Healthcheck ping failed: %s", _e)
```

The URL is read fresh from config on each ping tick — config changes take effect
without a gateway restart.

Fallback: if config read fails, the code falls back to env var `HERMES_HEALTHCHECK_URL`.

### Log signal
```
INFO gateway.run: Healthcheck ping OK (HTTP 200)
```
Appears every 5 minutes in `gateway.log`. Absence of this line for >10 min is a
secondary signal that the ticker has stalled.

## Setting up healthchecks.io

1. Register at https://healthchecks.io (magic link via email, no password)
2. A default check is created — copy its ping URL (format: `https://hc-ping.com/<uuid>`)
3. Configure the check:
   - **Name**: `hermes-gateway`
   - **Period**: `10 minutes` (we ping every 5 — double the interval for safety)
   - **Grace**: `5 minutes` (buffer before alert fires)
   - Total time-to-alert after gateway dies: ~15 minutes
4. Add integration: Settings → Integrations → Email (your address)
5. Optionally add Telegram bot as second notification channel (fully independent of Hermes)

## Adding the ping URL to config

```bash
# Append to /opt/data/config.yaml
cat >> /opt/data/config.yaml << 'EOF'
gateway:
  healthcheck_ping_url: "https://hc-ping.com/<uuid>"
  healthcheck_interval_ticks: 5
EOF
```

Or use `hermes config set gateway.healthcheck_ping_url "https://hc-ping.com/<uuid>"` if
that config key is supported.

## Verification

```bash
# Manual ping test
curl -s -o /dev/null -w "%{http_code}" "https://hc-ping.com/<uuid>"
# → 200

# Confirm gateway is pinging (after 5+ minutes of uptime)
grep 'Healthcheck ping OK' /opt/data/logs/gateway.log | tail -3
# → 2026-05-04 18:49:31,718 INFO gateway.run: Healthcheck ping OK (HTTP 200)
```

## Pitfalls

- **Bash wrapper does not loop-restart** — killing the gateway Python PID means
  pings stop and no restart happens until you manually relaunch or the Docker
  container restarts. The dead-man's switch will correctly fire in this case.
- **Period must be > ping interval** — if you set Period = 5min and ping every 5min,
  any single network hiccup causes a false alarm. Use Period = 2× ping interval.
- **Grace time prevents spurious alerts on restarts** — a gateway restart takes
  ~8 seconds; with Grace = 5min no false alert fires for brief restarts.
- **healthchecks.io free tier** — supports up to 20 checks. No API key needed
  just to ping; API key is needed to query check status programmatically.
- **Do not store the ping URL as a secret** — it's not a credential, just a
  unique path. Putting it in config.yaml (not .env) is correct.

## Extending to other monitored processes

The same pattern applies to any long-running process that uses its own delivery
channel: embed a periodic stdlib HTTP GET to the ping URL in the main loop.
Use a separate check UUID per monitored process so alerts are distinct.

## References

- See `references/healthchecks-setup-2026-05-04.md` for the original setup session notes.
