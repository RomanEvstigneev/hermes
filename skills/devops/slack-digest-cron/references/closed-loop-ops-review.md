# Closed-Loop Operations Review Cron

Session-derived implementation detail for Roman's Hermes setup.

## Purpose

A daily closed-loop review job should inspect yesterday's Hermes operational evidence and propose at most one actionable improvement to an existing process. It is an improvement scout, not an autonomous implementer.

## Live instance

```text
Name: Daily Closed-Loop Operations Review
Job ID: 3831a0ec0b1c
Schedule: 0 4 * * *
Delivery: slack:C0B18TP48JD
Script: /opt/data/scripts/closed_loop_ops_review.py
State: /opt/data/state/closed_loop_ops_review.json
Evidence reports: /opt/data/logs/closed_loop_ops_review/YYYY-MM-DD.json
Run logs: /opt/data/logs/cron_runs/closed-loop-ops-review/YYYY-MM-DD.log
```

The schedule is fixed 04:00 UTC daily. Roman chose this as fixed CET behavior; do not make it daylight-saving aware unless asked.

## Evidence collection scope

Included:
- `/opt/data/sessions/session_*.json`
- `/opt/data/logs/agent.log`
- `/opt/data/logs/errors.log`
- `/opt/data/logs/gateway.log`
- `/opt/data/logs/gateway_restarts.log`
- `/opt/data/cron/jobs.json`
- `/opt/data/cron/output/`
- `/opt/data/logs/cron_runs/`
- `/opt/data/state/closed_loop_ops_review.json`

Excluded by default:
- Slack workspace channel/message content.

The collector script writes JSON evidence and prints `LOG_PATH` so the cron prompt can include traceability in Slack.

## Prompt constraints

The cron prompt should explicitly say:
- English only.
- Do not call `send_message`; cron delivery posts the final response.
- Do not implement anything.
- Do not edit operational code/config.
- Only file write allowed is updating `/opt/data/state/closed_loop_ops_review.json`.
- Recommend at most one initiative.
- If evidence is weak, low-impact, speculative, or repetitive, return `No action recommended today`.
- Forbid net-new workflows; anchor every proposal to an existing process/job/script/log/session.
- Ask Roman to approve writing an implementation plan; implementation starts only after the plan is approved.
- Include follow-up on open/proposed/approved items and implemented items when state/evidence supports it.

## State schema

`/opt/data/state/closed_loop_ops_review.json` stores an array named `proposals`. Each cron run should append one record:

```json
{
  "date": "YYYY-MM-DD",
  "created_at": "ISO timestamp from generated_at",
  "status": "proposed or no_action",
  "fingerprint": "short stable lowercase identifier",
  "title": "short English title",
  "existing_process_anchor": "existing job/script/log/session/process, or null for no_action",
  "business_reason": "operator/business reason",
  "evidence": ["short evidence item"],
  "requested_next_step": "Roman approval to write plan or none",
  "follow_up": {
    "open_items_reviewed": 0,
    "implemented_items_reviewed": 0,
    "notes": []
  }
}
```

Known status values:
- `no_action`
- `proposed`
- `rejected`
- `approved_for_plan`
- `plan_approved`
- `implementation_started`
- `implemented`
- `followed_up`
- `stale`

## Verification pattern

Before registering or after editing the script:

```bash
/usr/local/lib/hermes-agent/venv/bin/python3 -m py_compile /opt/data/scripts/closed_loop_ops_review.py
/usr/local/lib/hermes-agent/venv/bin/python3 /opt/data/scripts/closed_loop_ops_review.py >/tmp/closed_loop_ops_review.out
python3 - <<'PY'
import json
s=open('/tmp/closed_loop_ops_review.out').read()
data=json.loads(s.split('\nLOG_PATH:', 1)[0])
print(data['report_type'])
print(data['analysis_window']['date'])
print(data['analysis_window']['date'])
print('/opt/data/logs/closed_loop_ops_review/' + data['analysis_window']['date'] + '.json')
print('/opt/data/state/closed_loop_ops_review.json')
PY
```

Then confirm registration with `cronjob(action='list')`. Avoid `cronjob(action='run')` unless Roman wants a test Slack message.

## Manual Slack delivery test

When Roman explicitly asks to test the live Slack delivery, trigger the job through the cron tool rather than running the Python script directly:

```text
cronjob(action='run', job_id='3831a0ec0b1c')
```

Important behavior: this is asynchronous. It sets `next_run_at` to the current UTC time and the gateway cron ticker picks it up on the next tick, usually within about 60 seconds. Verification steps:

1. Wait 60-75 seconds after the trigger.
2. Run `cronjob(action='list')`.
3. Confirm the closed-loop job has:
   - `last_run_at` near the trigger time.
   - `last_status: ok`.
   - `last_delivery_error: null`.
   - `next_run_at` restored to the next scheduled 04:00 UTC run.
4. Read `/opt/data/cron/output/3831a0ec0b1c/<run-timestamp>.md` and inspect the `## Response` section. This is the exact Slack-ready body that delivery posts.
5. Read `/opt/data/state/closed_loop_ops_review.json` and confirm a proposal/no-action record was appended with a stable `fingerprint` and correct `status`.
6. Read `/opt/data/logs/cron_runs/closed-loop-ops-review/YYYY-MM-DD.log` and `/opt/data/logs/closed_loop_ops_review/<analysis-date>.json` for traceability.
7. Ask Roman to confirm the message appeared in Slack home channel `slack:C0B18TP48JD`.

Observed successful manual test on 2026-05-01:

```text
Manual trigger accepted at next_run_at: 2026-05-01T11:46:15.956043+00:00
Completed at last_run_at: 2026-05-01T11:47:36.935691+00:00
last_status: ok
last_delivery_error: null
next_run_at: 2026-05-02T04:00:00+00:00
Output: /opt/data/cron/output/3831a0ec0b1c/2026-05-01_11-47-36.md
State updated: one `proposed` record, fingerprint `cron-audit-jsonl-gap`
Slack content suppression: 3 cron output previews and 4 Slack-derived sessions suppressed
```

If a Slack thread creates a follow-up one-shot verification job after Roman reacts to the proposal, do not confuse it with the daily job. In the observed test, a separate job `2fc083a8a774` named `One-week cron audit visibility check` was created with `deliver: origin` to the Slack thread; that was a follow-up verifier, while the daily closed-loop job remained scheduled at `0 4 * * *` with `deliver: slack:C0B18TP48JD`.

## Pitfalls

- `cronjob(action='run')` does not execute synchronously; do not report success until `last_run_at` advances and `last_status`/`last_delivery_error` are checked.
- Do not require the job to always produce an initiative; this creates noisy artificial recommendations.
- Do not include Slack workspace content unless explicitly requested; this job is about Hermes operations, not business channel digesting.
- Do not create another process/workflow as the recommendation; Roman specifically wants improvements to existing processes only.
- Do not confuse the closed-loop job with the Daily Cron Health Report. The health report summarizes status; the closed-loop review proposes one business-relevant improvement or no action.
- Keep Slack output short and Slack-friendly: bullets, no markdown tables.
