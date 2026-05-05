# Cron health audit troubleshooting

Use this reference when a Daily Cron Health Report says `Runs observed: 0` or `0 successful` while per-job status shows `OK`.

## Key distinction

The Daily Cron Health Report may combine two evidence sources:

- Structured JSONL audit records under `$HERMES_HOME/logs/cron_runs/YYYY-MM-DD.jsonl`
- Cron job state and outputs under `$HERMES_HOME/cron/jobs.json` and `$HERMES_HOME/cron/output/<job_id>/...md`

If the report counts runs only from JSONL audit records, `0 successful` can mean the audit trail is missing, not that jobs failed.

## Diagnostic workflow

1. Read the report JSON:
   ```bash
   jq '.audit_log_active, .summary.runs_in_window, .summary.successful_runs, .runs | length' \
     /opt/data/logs/cron_health_reports/YYYY-MM-DD.json
   ```
2. Check whether the referenced JSONL audit file exists:
   ```bash
   ls -l /opt/data/logs/cron_runs/YYYY-MM-DD.jsonl
   ```
3. Check real job state:
   ```bash
   jq '.jobs[] | {id,name,last_run_at,last_status,last_error,last_delivery_error,next_run_at}' \
     /opt/data/cron/jobs.json
   ```
4. Check saved cron outputs for the same window:
   ```bash
   find /opt/data/cron/output -type f -name 'YYYY-MM-DD_*.md' -o -name 'PREVIOUS-DAY_*.md' | sort
   ```
5. Check scheduler/gateway logs for actual starts and duplicate gateway attempts:
   ```bash
   grep -E 'cron.scheduler: (Running job|Output saved|Delivery failed)' /opt/data/logs/agent.log | tail -80
   tail -80 /opt/data/logs/gateway_restarts.log
   grep -E 'Another gateway instance is already running|asyncio.run\(\) shutdown|Task exception' /opt/data/logs/errors.log | tail -80
   ```

## Interpretation

- `jobs.json` has `last_status: ok` and cron output markdown exists, but JSONL audit file is missing: this is an observability/audit logging failure, not evidence that cron jobs failed.
- Repeated `Another gateway instance is already running` usually means multiple gateway launch mechanisms are active or a launcher starts `hermes gateway run &` without checking for an existing gateway process.
- `KeyboardInterrupt`, `OSError(5, Input/output error)`, and `asyncio.run() shutdown` near PTY/session closures may be shutdown noise, but still degrade health reports when scraped from errors.log.

## Fix patterns

- Add or restore a structured audit write in the cron scheduler after each run, near the code that saves output and calls `mark_job_run(...)`. Record at least: `job_id`, `job_name`, `started_at`, `ended_at`, `status`, `error`, `delivery_error`, `output_file`, and `deliver`.
- Make the health report fallback-count inferred runs from `$HERMES_HOME/cron/output/<job_id>/...md` and `jobs.json` when JSONL records are absent. Label this clearly as inferred evidence.
- Add an idempotent gateway-start guard in launch scripts such as `/hermes.sh`: if a live gateway for the same `HERMES_HOME` already exists, do not start a second one.
- When writing scheduler audit code, support legacy/test job shapes: `job["schedule"]` may be a string instead of a dict. Use a helper that accepts dict schedules (`display`, `expr`, `kind`) and string schedules rather than calling `.get(...)` on `job.get("schedule", {})` unconditionally.

## Human-report conventions

For executive summaries, avoid turning observability gaps into apparent execution failures.

- Show separate sections for cron execution health, delivery health, audit/observability warnings, and gateway lifecycle warnings.
- Do not put text like "Cron jobs — no job execution errors" under an "Errors detected" heading. If execution is OK but audit/gateway is degraded, say that directly.
- Prefer compact local time fields for humans. For Roman's deployment, use Europe/Paris display fields such as `last_run_local` and `next_run_local`, rendering `CET`/`CEST` labels instead of long ISO timestamps with fractional seconds.
- Keep raw file paths such as `$HERMES_HOME/logs/cron_runs/YYYY-MM-DD.jsonl` and full JSON report paths in the detailed log/report, not in the executive summary.

## Verification notes

- Test the audit writer in a temporary `HERMES_HOME` and verify that `$HERMES_HOME/logs/cron_runs/YYYY-MM-DD.jsonl` is created and parseable.
- Use `scripts/run_tests.sh` for CI-parity when possible. If the wrapper fails before running tests because the local venv lacks `pip` while installing helper packages, run only a narrow fallback direct pytest command with `-o 'addopts='` and explicitly report that it is not CI-equivalent.
