Hermes gateway in Docker: `hermes gateway install --system` refuses inside containers; auto-start via `/hermes.sh` with `hermes gateway run &` before interactive `hermes`, and run container with `--restart unless-stopped`. If Slack fails `app token already in use`, clear stale gateway locks using the active Hermes Python/source tree, then restart gateway. The hermes-agent skill is flagged DANGEROUS by security scanner — patches require confirmation and may fail silently.
§
Slack configuration: require_mention=true, auto_thread=true. Allowed users: Roman (U09NJ1H6V6K) and U0ABC4S3HC5. Gateway auto-starts via /hermes.sh in Docker.
§
Hermes: /usr/local/lib/hermes-agent v0.12.0, commit 5e9b7a981, config v23 at /opt/data/config.yaml. /hermes.sh sets PLAYWRIGHT_BROWSERS_PATH=/opt/data/cache/ms-playwright, unsets TERMINAL_CWD, cd /usr/local/lib/hermes-agent. Old v0.9.0 quarantined at /opt/hermes.old-v0.9.0-20260501; /opt/hermes is shim only.
§
Slack setup: bot monitors #founders and #hermes-home (home C0B18TP48JD); #hermes-home excluded from digest. Cron: digest 08:00 UTC, git auto-commit 00:00 UTC, health report 19:00 UTC (976c82c577dd). /opt/data/memory/ holds Slack people/channel memory and product feature log: product/axion-product-feature-log.md.
§
Slack formatting: do NOT use markdown tables in Slack responses — Slack doesn't render them. Use bullet lists, numbered lists, or plaintext formatting instead.
§
Cron job defaults: (1) deliver=slack:C0B18TP48JD always, never "local". (2) Every script writes a detailed log to /opt/data/logs/cron_runs/<job-slug>/YYYY-MM-DD.log using io.StringIO redirect-stdout; prints LOG_PATH so LLM includes it. (3) Prompts say "Do NOT call send_message — return Slack-ready summary, cron system delivers it." (4) Executive summary: bullet lists, founder-readable in 30 sec, log path at bottom. (5) config.yaml: cron.wrap_response: false — no footer.
§
Post-session knowledge audit is configured under `/opt/data/config.yaml` with `post_session_audit.enabled=true`, Roman DM Slack channel `D0B0P5BAQSF`, skip user `U09NJ1H6V6K`, and watched paths `memories/`, `memory/`, `skills/`, `cron/jobs.json`, and `scripts/`.