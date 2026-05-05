# Healthchecks.io Setup — 2026-05-04

## Account

- Service: healthchecks.io
- Email: evstigneevromanv@gmail.com
- Registration method: magic link (no password)

## Check created

- Ping URL: `https://hc-ping.com/6989d618-f27a-4391-9dfa-90aa15c202d7`
- Intended name: `hermes-gateway`

## Recommended config (set manually in the dashboard after login)

- Period: 10 minutes
- Grace: 5 minutes
- Integration: Email to evstigneevromanv@gmail.com

## Config entry added to /opt/data/config.yaml

```yaml
gateway:
  healthcheck_ping_url: "https://hc-ping.com/6989d618-f27a-4391-9dfa-90aa15c202d7"
  healthcheck_interval_ticks: 5
```

## First confirmed ping

```
2026-05-04 18:49:31,718 INFO gateway.run: Healthcheck ping OK (HTTP 200)
```

Gateway started at 18:45:30 UTC; first ping at 18:49:31 (tick 5, exactly 5 minutes later).

## Why it was created

The sentinel / cron monitoring loop is embedded inside the gateway process.
If the gateway dies, the sentinel never runs and no Slack alert is sent.
This external ping provides an independent signal via email that survives
gateway death.
