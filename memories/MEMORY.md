Hermes gateway in Docker: `hermes gateway install --system` refuses inside containers; auto-start via `/hermes.sh` with `hermes gateway run &` before interactive `hermes`, and run container with `--restart unless-stopped`. If Slack fails `app token already in use`, clear stale gateway locks using the active Hermes Python/source tree, then restart gateway. The hermes-agent skill is flagged DANGEROUS by security scanner — patches require confirmation and may fail silently.
§
Slack configuration: require_mention=true, auto_thread=true. Allowed users: Roman (U09NJ1H6V6K) and U0ABC4S3HC5. Gateway auto-starts via /hermes.sh in Docker.
§
Hermes upgrade state: `/usr/local/lib/hermes-agent` is Hermes 0.12.0 at local commit `5e9b7a981` rebased on `origin/main` as of 2026-05-01; `/opt/data/config.yaml` is config v23. `/hermes.sh` launches `/usr/local/bin/hermes`, sets `PLAYWRIGHT_BROWSERS_PATH=/opt/data/cache/ms-playwright`, unsets `TERMINAL_CWD`, and `cd`s to `/usr/local/lib/hermes-agent`. Old `/opt/hermes` v0.9.0 is quarantined at `/opt/hermes.old-v0.9.0-20260501-070339`; `/opt/hermes` is only a shim with `.playwright` symlink.
§
Slack setup: bot monitors #founders and #hermes-home (home C0B18TP48JD). Cron: Slack digest 08:00 UTC, git auto-commit 00:00 UTC, Daily Cron Health Report 19:00 UTC (job_id 976c82c577dd, script /opt/data/scripts/cron_health_report.py, reports in /opt/data/logs/cron_health_reports/). Roman wants /opt/data/memory/ channel+people system with daily enrichment, weekly review, monthly deep clean; manual @hermes remember/forget overrides protected from auto-deletion.
§
Slack formatting: do NOT use markdown tables in Slack responses — Slack doesn't render them. Use bullet lists, numbered lists, or plaintext formatting instead.
§
Cron Slack reports: set `cron.wrap_response: false`; Roman wants no “To stop or manage this job...” footer, only the report body.