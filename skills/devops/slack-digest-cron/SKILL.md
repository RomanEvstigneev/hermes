---
name: slack-digest-cron
description: "Create a scheduled Slack channel digest using cron + data-collection script. Reads channel history via Slack API and has Hermes summarize it. Includes a file-based persistent memory system for channels and people."
version: 1.3.0
tags: [slack, cron, digest, summary, notifications, memory]
---

# Slack Daily Digest via Cron

Use when: user wants Hermes to periodically read Slack channel history and send a summary.

## Key Discovery: slack_sdk is only in the hermes-agent venv

System Python does NOT have slack_sdk. Must add to sys.path before importing:

```python
VENV_SITE_PACKAGES = "/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages"
if VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)
from slack_sdk import WebClient
```

## Key Discovery: /opt/data/.env contains MASKED values (***) when read directly

The .env file is written by Hermes with `***` placeholders for security — reading it
with open() or a plain shell `cat` gives you `SLACK_BOT_TOKEN=***`, not the real token.

The real token is loaded into memory only when the hermes venv's dotenv loader runs.
To access it programmatically, use the hermes venv Python:

```python
# Script must be run with: /usr/local/lib/hermes-agent/venv/bin/python3
import sys
sys.path.insert(0, "/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages")
from dotenv import load_dotenv
from pathlib import Path
import os
load_dotenv(Path("/opt/data/.env"), override=True)
token = os.environ["SLACK_BOT_TOKEN"]  # now the real token
```

OR just run scripts with the venv python directly and let dotenv do the work.
The `source /opt/data/.env` shell approach does NOT work (same *** values in the file).

## Key Discovery: cron scripts must load .env manually

Cron jobs run in a fresh session with no shell env. Load secrets explicitly:

```python
def load_env_file():
    env_path = "/opt/data/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")
load_env_file()
```

## Cron logging and state inspection

Use `cronjob(action='list')` first for current status. It reports each job's `last_run_at`, `last_status`, `last_delivery_error`, `next_run_at`, enabled/state, and script path.

Quick workflow for "did the overnight cron jobs run successfully?":
1. Get the current UTC time with `date -u` so you can distinguish overdue jobs from jobs not due yet.
2. Run `cronjob(action='list')` and classify each job:
   - `last_run_at` after the expected scheduled time + `last_status: ok` + no `last_delivery_error` = successful.
   - `next_run_at` still in the future and `last_run_at` null = not due yet, not failed.
   - `last_status` non-ok or `last_delivery_error` non-null = investigate.
3. Check `/opt/data/logs/cron_runs/YYYY-MM-DD.jsonl` for structured audit records if present.
4. Read `/opt/data/cron/output/<job_id>/<timestamp>.md` for the exact script output and final response.
5. For git backup jobs, verify the commit directly in `/opt/data` with `git log -1 --oneline --date=iso` and `git status --short`; untracked files after the run may simply be new runtime files created after the backup.
6. If Slack delivery is relevant, inspect `last_delivery_error` and scan `gateway.log` / `errors.log` for `Send error`, `channel_not_found`, or `Slack app token already in use`.
7. If a log says "Another gateway instance is already running", check `ps -p <PID> -o pid,ppid,stat,lstart,cmd`; if that PID is a healthy running gateway, treat it as a duplicate start attempt, not automatically as a cron failure.

Persistent cron definitions and last status are stored in:

```text
/opt/data/cron/jobs.json
```

Each job entry includes:
- `last_run_at`
- `last_status`
- `last_error`
- `last_delivery_error`
- `repeat.completed`
- `next_run_at`

This is a last-known-state file, not a complete historical audit trail of every run.

Runtime logs are in:

```text
/opt/data/logs/agent.log      # cron.scheduler lines, run_agent, tool/API logs
/opt/data/logs/errors.log     # ERROR/WARNING entries and tracebacks
/opt/data/logs/gateway.log    # gateway/platform + cron scheduler process logs
```

Search examples:

```text
search_files(path="/opt/data/logs", pattern="cron|job_id|Running job|last_delivery_error|<job name>")
read_file(path="/opt/data/cron/jobs.json")
```

Pitfall: `/opt/data/state.db` may not contain cron job tables; cron state is file-backed in `/opt/data/cron/jobs.json`. Do not assume sqlite contains cron history.

If the user needs a full audit trail, recommend adding explicit JSONL logging such as `/opt/data/logs/cron_runs/YYYY-MM-DD.jsonl` with timestamp, job_id, name, script stdout/stderr, status, final response, and delivery error.

### Daily cron health report pattern

For a reusable "report whether other cron jobs/logs were successful" workflow:

1. Patch the live cron scheduler source that is actually imported by the running gateway (verify with `ps`, `pwdx <pid>`, and module `__file__`). Roman's Docker entrypoint should `cd /usr/local/lib/hermes-agent` before launching Hermes so `/usr/local/lib/hermes-agent/cron/scheduler.py` is imported; if cwd is still `/opt/hermes`, the old tree can shadow the upgraded package.
2. Add per-run JSONL audit logging from `cron.scheduler.tick()` after `save_job_output()` and delivery, writing records to:
   ```text
   /opt/data/logs/cron_runs/YYYY-MM-DD.jsonl
   ```
3. Include at least: `schema_version`, `event`, `job_id`, `job_name`, `session_id`, `started_at`, `ended_at`, `success`, `status`, `error`, `delivery_error`, `output_file`, `final_response`, `full_output_doc`, and `traceback`.
4. Add a collector script such as:
   ```text
   /opt/data/scripts/cron_health_report.py
   ```
   It should read `/opt/data/cron/jobs.json`, the JSONL audit directory, and excerpts from `agent.log`, `errors.log`, and `gateway.log`; save snapshots under:
   ```text
   /opt/data/logs/cron_health_reports/YYYY-MM-DD.json
   ```
5. Create a daily cron job with `script='scripts/cron_health_report.py'`, `deliver='local'`, and a prompt that sends a concise Slack report.

Known instance in Roman's setup:
```text
Name: Daily Cron Health Report
Job ID: 976c82c577dd
Schedule: 0 19 * * *
Script: cron_health_report.py         <-- bare filename, NOT scripts/cron_health_report.py
Deliver: slack:C0B18TP48JD
Reports: /opt/data/logs/cron_health_reports/YYYY-MM-DD.json
Audit input: /opt/data/logs/cron_runs/YYYY-MM-DD.jsonl   (empty until gateway restart)
```

Important pitfall: after patching live scheduler code, the already-running gateway process must be cleanly restarted before new cron audit logging is active. Do not start a second gateway; Slack will fail with `Slack app token already in use`. Use the existing deployment's restart path, and verify that the restarted process imports from `/usr/local/lib/hermes-agent`, not the stale `/opt/hermes` tree.

### Why cron_runs/ stays empty even after patching scheduler.py

The `_write_cron_run_audit()` function is called inside `tick()`. The manual `cronjob(action='run')` path only sets `next_run_at = now` in jobs.json and waits for the scheduler's 60-second tick loop to pick it up. The tick loop runs inside the already-running gateway process — which loaded the old scheduler code at startup. Patching the file on disk has no effect until the gateway process is restarted.

**Bottom line:** JSONL audit records will only appear in `/opt/data/logs/cron_runs/` after the gateway is cleanly restarted (stop existing PID, start fresh once).

### Top 3 logging gaps to fix

1. **JSONL cron audit missing** — `/opt/data/logs/cron_runs/` is always empty because the running gateway loaded old code. Fix: clean gateway restart. Unblocks the health report's ability to read structured run history.

2. **Cron delivery failures silently swallowed** — Slack delivery errors (e.g. `channel_not_found`) appear in `gateway.log` but are not surfaced to the user. Fix: update `cron_health_report.py` to scan `gateway.log` for `Send error|channel_not_found|Fallback send also failed` patterns and include them in the daily health report.

3. **Gateway restart events untracked** — The gateway can restart 10+ times a day (exit code 1 → systemd/Docker revives it). There is no structured restart count log. Fix: append a timestamped line to `/opt/data/logs/gateway_restarts.log` inside the startup script (`/hermes.sh`) on each launch.

### Diagnosing silent delivery failures

When a cron job shows `last_status: ok` but the Slack message never arrived, first check the job's `deliver` value in `cronjob(action='list')` or `/opt/data/cron/jobs.json`.

Common cause found in Roman's setup:
- `deliver: local` means the cron output is only saved under `/opt/data/cron/output/<job_id>/...` and is never sent to Slack, even if the prompt says to call `send_message`.
- Cron runs inject a system instruction: do not call `send_message`; return the final response and let the cron delivery system handle delivery.
- Fix by setting `deliver='slack:<channel_id>'` and changing the prompt to return only a Slack-ready message body, not to call `send_message`.

Example fix:

```text
cronjob(action='update', job_id='<job_id>', deliver='slack:C0B18TP48JD', prompt='...return the Slack-ready message as your final response. Do not call send_message...')
```

Then inspect delivery errors:

```bash
grep -i 'Send error\|channel_not_found\|Fallback send\|deliver' /opt/data/logs/gateway.log /opt/data/logs/agent.log /opt/data/logs/errors.log | tail -40
```

Other common causes:
- `channel_not_found` — bot not a member of the target channel, or wrong channel ID
- `Slack app token already in use` — duplicate gateway process (stop old PID first)

### Business-friendly backup notifications

For Daily Git Auto-Commit notifications, Roman does not want raw path lists such as `skills/devops/...` or `cron/output/...` in Slack. Prefer an operator/business summary that explains what changed and why it matters: automation reliability, Slack delivery, memory/context maintenance, health reporting, configuration, or backup coverage.

Implementation pattern:
- Have the backup script output `Business impact hints:` derived from changed paths.
- In the cron prompt, instruct the model to translate repository paths into practical impact and avoid raw file lists unless debugging.
- Keep Slack output brief: files changed count, push success, then `Business summary:` bullets.

### Daily Git Auto-Commit push protection failures

If the daily backup creates a local commit but GitHub rejects the push because push protection detected a Slack token or other secret, do not retry the push. Investigate the local commit with masked output only, then rewrite the unpushed local commit before pushing.

Roman wants cron output, runtime output, transcripts, logs, and accumulated operational history preserved in git where practical. Do **not** broadly exclude `cron/output/` from backups. Instead, sanitize secrets before commit and remove only the specific unsafe output file or line that captured credentials.

Required prevention pattern for `/opt/data/scripts/daily_git_commit.py`:
- Keep `cron/output/` eligible for backup.
- Before staging/committing, scan candidate text files for known secret patterns such as Slack tokens (`xox...`, `xapp...`).
- Replace any matched secret with `[REDACTED_SECRET]` in the file before commit.
- Print a redaction summary without printing the secret value.
- Keep GitHub push protection enabled as a final safety net.

Cron prompts should also include a secret-handling rule: never include raw credentials, API keys, Slack token strings, authorization headers, or private key material in Slack messages or generated files; redact as `[REDACTED_SECRET]` if seen.

Credential rotation is a risk-based decision when the blocked commit never reached GitHub: recommend rotation for production/high-scope tokens or if the token may have passed through Slack/LLM/session logs, but do not present it as mandatory emergency action solely because an unpushed local commit was blocked.

See `references/git-backup-push-protection.md` for the safe investigation workflow, local history rewrite steps, rotation checklist, and prevention checklist.

### Test-running a cron job after a delivery fix

Use `cronjob(action='run', job_id='<job_id>')` to trigger a test run. Important behavior: this does not execute synchronously; it sets `next_run_at` to now and the gateway's cron ticker picks it up on its next interval, usually within 60 seconds.

Verification workflow:
1. Run the job with `cronjob(action='run', job_id='<job_id>')`.
2. Wait about 60-75 seconds.
3. Re-run `cronjob(action='list')` and verify:
   - `last_run_at` moved to the test-run time.
   - `last_status` is `ok`.
   - `last_delivery_error` is null.
   - `deliver` is the intended Slack target, not `local`.
4. Check `/opt/data/cron/output/<job_id>/` for the new output markdown file and read it to confirm the generated Slack message body.
5. If Slack still did not receive it, search logs for `Send error`, `channel_not_found`, and `Fallback send`.

### Post-session knowledge update reports

When Roman asks whether Hermes can notify him after conversations with other Slack users about memories or knowledge files that changed, answer yes but treat it as a separate automation rather than built-in default behavior.

Preferred MVP: a cron watcher every 5 minutes that detects Slack-origin sessions with non-Roman users, waits 5-10 minutes of inactivity, diffs knowledge paths, and sends Roman an executive Slack summary only if meaningful changes occurred. Avoid gateway hooks for the first version unless Roman explicitly wants exact timer behavior.

Track knowledge paths such as `/opt/data/memories/`, `/opt/data/memory/`, `/opt/data/skills/`, and `/opt/data/cron/jobs.json`. Do not send raw transcripts or private message excerpts; summarize what changed, list changed files, and redact secrets.

See `references/post-session-knowledge-update-reports.md` for the implementation shape, safety rules, and summary template.

## References and templates (load with skill_view file_path=)

- `references/post-session-knowledge-update-reports.md` — design notes for a cron-based watcher that notifies Roman after non-Roman Slack sessions when memories, skills, or knowledge files changed.
- `templates/cron-prompt-daily-digest.md` — proven prompt for Slack Daily Digest job
- `templates/cron-prompt-memory-enrichment.md` — proven prompt for Daily Memory Enrichment job
- `templates/cron-prompt-memory-weekly.md` — proven prompt for Weekly Memory Review job
- `templates/cron-prompt-memory-monthly.md` — proven prompt for Monthly Memory Deep Clean job
- `templates/cron-script-logging-boilerplate.py` — reusable write_run_log() + redirect-stdout boilerplate for any cron script

## Architecture: script= parameter injects data into cron prompt

The `script` parameter of `cronjob(action='create')` runs a Python script before
the cron prompt executes. Its stdout is injected as context. This is the right
pattern for "collect data, then have LLM process it":

```python
cronjob(action='create',
    name='Slack Daily Digest',
    schedule='0 8 * * *',            # 08:00 UTC daily — morning digest of previous day
    script='slack_daily_digest.py',  # basename/relative to /opt/data/scripts/, not scripts/...
    prompt='... analyze the data above and send summary to slack:CHANNEL_ID ...',
    deliver='local',  # bot sends to Slack itself via send_message tool
)
```

Place scripts at: `/opt/data/scripts/your_script.py`, but set the cron `script` field to `your_script.py`. Do NOT use `scripts/your_script.py`, because the scheduler resolves it as `/opt/data/scripts/scripts/your_script.py` and the job fails with "Script not found".

## Slack API: finding channels the bot is a member of

```python
def get_bot_channels():
    channels = []
    cursor = None
    while True:
        resp = client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200,
            **({"cursor": cursor} if cursor else {})
        )
        for ch in resp.get("channels", []):
            if ch.get("is_member"):
                channels.append({"id": ch["id"], "name": ch.get("name")})
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return channels
```

## Slack API: reading channel history for a time range

```python
resp = client.conversations_history(
    channel=channel_id,
    oldest=str(day_start.timestamp()),
    latest=str(day_end.timestamp()),
    limit=200,
    inclusive=True,
)
```

Filter out noise (bot messages, join/leave events):
```python
skip_subtypes = {"bot_message", "channel_join", "channel_leave",
                 "bot_add", "bot_remove", "channel_purpose", "channel_topic"}
if msg.get("subtype") in skip_subtypes or msg.get("bot_id"):
    continue
```

## Resolving user IDs to display names

Slack messages contain `<@U12345>` — resolve to real names:

```python
user_cache = {}
def get_display_name(user_id):
    if user_id not in user_cache:
        resp = client.users_info(user=user_id)
        profile = resp["user"].get("profile", {})
        user_cache[user_id] = profile.get("display_name") or profile.get("real_name") or user_id
    return user_cache[user_id]

# In text:
import re
text = re.sub(r"<@([A-Z0-9]+)>", lambda m: f"@{get_display_name(m.group(1))}", text)
```

## Default rules for every cron job (apply at creation, not just digest)

1. deliver: always set to a real Slack target (e.g. slack:C0B18TP48JD). NEVER leave as "local".
2. Log file: every script must write a detailed run log to /opt/data/logs/cron_runs/<job-slug>/YYYY-MM-DD.log.
   Use the redirect-stdout pattern to capture all output:
   ```python
   if __name__ == "__main__":
       import io, contextlib
       buf = io.StringIO()
       with contextlib.redirect_stdout(buf):
           main()
       output = buf.getvalue()
       sys.stdout.write(output)
       sys.stdout.flush()
       write_run_log(label, output)
   ```
   Print LOG_PATH to stdout so the LLM can include it in the Slack message.
3. Prompt must say: "Do NOT call send_message. Return a Slack-ready executive summary as your final
   response — the cron delivery system posts it automatically." Include LOG_PATH reference.
4. Slack message style: executive summary — concise, actionable, founder-readable in 30 seconds.
   Bullet lists. No markdown tables. Include log path at the bottom.

## Cron Slack delivery target

Roman prefers clean cron Slack reports without wrapper/footer text. Keep `/opt/data/config.yaml` set to:

```yaml
cron:
  wrap_response: false
```

This removes the automatic `Cronjob Response...` header and the `To stop or manage this job...` footer.

Do NOT rely on the cron prompt to call `send_message`: cron injects a system instruction saying the final response will be delivered automatically and the agent must not call `send_message`. If `deliver='local'`, the output is saved only under `/opt/data/cron/output/...` and will not appear in Slack.

For Slack notifications, set an explicit delivery target, e.g.:

```python
deliver='slack:C0B18TP48JD'
```

Then make the prompt return only the Slack-ready message body. Do not tell it to call `send_message`.

## Closed-loop operations review cron pattern

Use this pattern when Roman asks for a recurring operational review that proposes improvements but must not implement them without human approval.

Known live instance in Roman's setup:
```text
Name: Daily Closed-Loop Operations Review
Job ID: 3831a0ec0b1c
Schedule: 0 4 * * *                 # fixed 04:00 UTC daily, intended as 05:00 CET
Script: closed_loop_ops_review.py
Deliver: slack:C0B18TP48JD
State: /opt/data/state/closed_loop_ops_review.json
Reports: /opt/data/logs/closed_loop_ops_review/YYYY-MM-DD.json
Run logs: /opt/data/logs/cron_runs/closed-loop-ops-review/YYYY-MM-DD.log
```

Design rules:
1. Analyze the previous UTC calendar day only.
2. Include Hermes sessions, Hermes logs, cron job definitions/status/results, cron output/audit files, and persistent proposal state.
3. Exclude Slack workspace channel/message content unless Roman explicitly asks otherwise.
4. Recommend at most one initiative. If no high-signal improvement exists, say `No action recommended today` and explain why briefly.
5. Forbid net-new workflows. Every recommendation must anchor to an existing process, job, script, log, session pattern, or workflow.
6. Deduplicate against recent proposals in `/opt/data/state/closed_loop_ops_review.json`; do not repeat an idea without a materially new signal.
7. The cron job may update only its state file. It must not edit operational code/config, run shell commands, or implement fixes.
8. Use business language first, then technical evidence. Ask Roman to approve writing an implementation plan; implementation starts only after he approves that plan.
9. Support both follow-up types: immediate post-implementation summary from the implementing Hermes session, and next-day cron follow-up based on evidence/state.
10. Excluding Slack workspace content requires more than not calling the Slack API: suppress previews from Slack-derived cron jobs (`slack_daily_digest.py`, `slack_memory_update.py`, `slack_memory_weekly.py`, `slack_memory_monthly.py`) and suppress text samples from Slack-platform or Slack-derived cron sessions. Keep metadata/labels only.

See `references/closed-loop-ops-review.md` for the implementation details, prompt/state schema, manual Slack delivery test workflow, output/state/log verification checklist, and observed follow-up one-shot behavior.

## Rate limiting

Add `time.sleep(0.3-0.5)` between API calls to avoid Slack rate limits (Tier 3: 50 req/min).

## Cron prompt: always specify output language explicitly

As of the global English-only policy patch (`ENGLISH_ONLY_POLICY` in `prompt_builder.py`), Hermes injects an English-only rule into every system prompt automatically — including cron sessions. However, cron jobs run with `skip_memory=True` and a minimal context, so an explicit reminder in the prompt is still best practice to be safe:

```
IMPORTANT: Respond ONLY in English. Never use any other language regardless
of what language the channel messages are written in.
```

Without the global policy (or before a gateway restart loads it), the LLM will mirror the language of the Slack messages or the user's memory profile — which may not be what's wanted for a team digest.

---

## Persistent Memory System for Channels & People

Use when: user wants the bot to remember ongoing discussions, who people are,
and keep that knowledge accurate over time via automated lifecycle rituals.

### File structure

```
/opt/data/memory/
  people/<firstname-lastname>.md    # one per person
  channels/<channel-name>.md        # one per channel
  archive/people/                   # inactive people (90+ days)
  archive/channels/                 # inactive channels
  MEMORY_INDEX.md                   # auto-updated index
```

### People file format

```markdown
# Full Name
Slack ID: UXXXXXXX
Role: [role]
Last updated: YYYY-MM-DD
Last seen: YYYY-MM-DD

## Confirmed facts
- [fact] (#channel, seen Nx, last YYYY-MM-DD)

## Pending confirmation
- [YYYY-MM-DD] [fact] — 1x seen

## Stale (not seen 30+ days)
- [fact] — last seen YYYY-MM-DD

## Manual overrides (protected — never auto-deleted)
- [fact]
```

### Channel file format

```markdown
# #channel-name
Channel ID: CXXXXXXXX
Type: public/private
Last updated: YYYY-MM-DD

## Purpose / context
## Recurring topics
## Active open questions
## Key decisions (last 90 days)
## Regular participants
## Stale topics (not discussed 30+ days)
```

### Fact lifecycle

```
Slack message → [candidate: Pending, 1x seen]
    → seen again within 14 days → [Confirmed]
    → not seen for 30 days → [Stale]
    → not seen for 90 days → [Archived]
    (manual facts bypass this entirely)
```

### Four cron rituals

| Cron | Schedule | Script | Purpose |
|------|----------|--------|---------|
| Daily enrichment | 08:05 UTC | slack_memory_update.py | Add new facts, promote confirmed |
| Weekly review | 09:00 UTC Sunday | slack_memory_weekly.py | Prune expired pending, mark stale |
| Monthly deep clean | 07:00 UTC 1st | slack_memory_monthly.py | Validate against evidence, archive |
| Git auto-commit | 00:00 UTC | daily_git_commit.py | Version-control all memory changes |

Run enrichment 5 minutes AFTER digest so they don't collide.

### Injecting memory into digest context

At the end of the digest data-collection script, output the memory files:

```python
def output_memory_context():
    memory_dir = "/opt/data/memory"
    if not os.path.exists(memory_dir):
        return
    print("\n=== MEMORY CONTEXT ===\n")
    for subdir in ("people", "channels"):
        dirpath = os.path.join(memory_dir, subdir)
        if not os.path.exists(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if fname.endswith(".md"):
                with open(os.path.join(dirpath, fname)) as f:
                    print(f"--- memory/{subdir}/{fname} ---")
                    print(f.read())

if __name__ == "__main__":
    main()
    output_memory_context()
```

This means the digest cron agent knows who people are and what recurring topics exist —
making its summaries much richer without any extra API calls.

### Cron prompt rules for memory enrichment

Key instructions to include in daily enrichment prompt:
- Fact goes to Pending first — only moves to Confirmed if seen 2+ times
- Never delete from Confirmed or Pending — only weekly review does that
- Never touch Manual overrides section
- Create new person file on first encounter (use Slack ID from "USERS SEEN TODAY" section)
- Update "Last seen" dates on every run
- Promote Pending → Confirmed if fact already exists in Pending from a previous day

### Manual override commands (Phase 5 / live override)

Teach the bot to respond to these in the gateway:
- `@hermes remember: [fact about person or channel]`
- `@hermes forget: [person] / [topic]`

Manual facts are tagged `[manual]` and never auto-deleted by any cron job.

### Seeding known people

Pre-create people files with known facts before the cron starts.
Use `## Manual overrides` section for founder/role info so it's never wiped.

```markdown
## Manual overrides (protected — never auto-deleted)
- CEO / Co-founder, leads product and engineering
```

### Pitfall: Sergey's Slack ID may be unknown at seed time

If you don't know someone's Slack ID when creating the seed file, set it to
`(unknown — to be discovered from Slack activity)`. The enrichment cron will
fill it in when it first sees that person in a message (from the "USERS SEEN TODAY"
section output by the data collection script).

---

## Looking up a user's messages across channels

Use case: "read all messages from @Person and summarize their responsibilities."

Step 1 — resolve the Slack user ID by name:
```python
data = slack_api("users.list", {})
for m in data.get("members", []):
    name = m.get("real_name", "") + " " + m.get("profile", {}).get("display_name", "")
    if "fedor" in name.lower() or "barbarin" in name.lower():
        print(m["id"], m["real_name"])
```

Step 2 — get bot-member channels (see get_bot_channels above).

Step 3 — filter conversations.history by user ID:
```python
messages = data.get("messages", [])
user_msgs = [m for m in messages if m.get("user") == TARGET_USER_ID]
```

Note: Slack's search.messages API (which could filter by user directly) requires
user OAuth tokens, not bot tokens. The manual filter approach above is the
correct pattern for bot tokens.

---

## Auditing existing cron jobs for silent delivery failures

When asked to review or fix existing cron jobs, always do this audit first:

1. Read `/opt/data/cron/jobs.json` (or `cronjob(action='list')`) and check EVERY job's `deliver` field.
2. Any job with `deliver: local` will NEVER post to Slack even if its prompt says to — this is a silent failure mode.
3. Fix by updating the job: `cronjob(action='update', job_id='...', deliver='slack:C0B18TP48JD', prompt='...')`.
4. Also audit the prompt itself: remove any `send_message` call instructions and replace with "return Slack-ready summary as final response — cron delivery system posts it automatically."
5. After fixing, run `cronjob(action='run', job_id='...')`, wait 75 seconds, then verify:
   - `last_run_at` updated, `last_status: ok`, `last_delivery_error: null`
   - Read `/opt/data/cron/output/<job_id>/<latest_timestamp>.md` to see the exact message that was delivered

## Excluding specific channels from the digest

Use a hardcoded set of channel IDs at the top of the data-collection script.
Filter by ID (not name) so renames don't break the exclusion.

```python
# Channels permanently excluded from the daily digest
EXCLUDED_CHANNEL_IDS = {
    "C0B18TP48JD",  # #hermes-home — bot's own operational channel
}

# In get_bot_channels(), filter on membership AND exclusion:
if ch.get("is_member") and ch["id"] not in EXCLUDED_CHANNEL_IDS:
    channels.append(...)
```

Rationale: #hermes-home is where the digest is delivered — including it in the
analysis would produce circular self-referential noise. Always exclude it by default.

## Reading full Slack history (all-time, not just yesterday)

Use case: onboarding, bootstrapping memory, or a one-off audit.

```python
# No oldest/latest — fetches from the beginning of the channel
msgs = []
cursor = None
while True:
    kwargs = {'channel': ch_id, 'limit': 200}
    if cursor:
        kwargs['cursor'] = cursor
    r = client.conversations_history(**kwargs)
    for m in r.get('messages', []):
        if m.get('subtype') in SKIP or m.get('bot_id'):
            continue
        msgs.append(m)
    cursor = r.get('response_metadata', {}).get('next_cursor')
    if not cursor or not r.get('has_more'):
        break
    time.sleep(0.3)
# Messages come newest-first; reverse for chronological order
msgs = list(reversed(msgs))
```

For link/mention cleanup before passing to LLM:
```python
import re
text = re.sub(r'<@([A-Z0-9]+)>', lambda x: '@' + get_name(x.group(1)), text)
text = re.sub(r'<https?://[^|>]+\|([^>]+)>', r'\1', text)  # titled links → title
text = re.sub(r'<https?://[^>]+>', '[link]', text)           # bare links → [link]
```

## Bot channel membership and the channels:join scope gap

The Hermes Slack bot token at Roman's setup includes `channels:history` and `channels:read`
but NOT `channels:join`. This means:

- `conversations.list` will return ALL public channels (member and non-member)
- Trying to read history of a non-member channel → `not_in_channel` error
- Trying to call `conversations_join()` → `missing_scope` error

**The bot cannot self-join channels.** To add the bot to more channels:
- A human must run `/invite @hermes` in the target channel from the Slack UI
- OR a Slack admin can add the bot via the channel settings

Once invited, the bot is automatically picked up by `get_bot_channels()` on the next digest run — no script changes needed.

Current bot membership as of 2026-05-01 (9 channels):
  #general, #website, #bizdev, #proj-pitchdeck, #industry-knowledge,
  #design, #nexus-conf, #founders [private], #hermes-home [private]

Non-member channels worth inviting the bot to (use `/invite @hermes` in each):
  High value: #random, #daily, #ai-hype-cycle, #pricing, #fin-model,
              #linkedin-posts, #awareness, #deploys-prod, #deploys-dev, #alerts-infra
  Project channels: #proj-ardian-general, #proj-ardian-ghg-analysis, #proj-ardian-helix,
                    #proj-indefi-ai-dd, #proj-indefi-sscp, #proj-mazars-valuation,
                    #proj-altor-susty-value-creation, #proj-arendt-esg,
                    #proj-esg-dd-tool, #proj-docs-generation, #proj-custom-plugins
  Skip: #welcome, #slackbot-backlog

## Pitfalls

- `conversations.list` with `types=public_channel,private_channel` can time out (60s+)
  when called from a plain shell curl with `source /opt/data/.env` — the source command
  doesn't actually load the real tokens (they're masked as ***). The call hangs or fails silently.
  Always use the hermes venv python with dotenv to load the real token, then urllib or slack_sdk.

- `conversations.history` requires the bot to be a member — `not_in_channel` error otherwise
- Getting channels for yesterday: use UTC, not local time, unless user specifies timezone
- `reply_count` on a message shows thread depth but threads aren't fetched automatically
  (use `conversations.replies` if you need thread content too)
- 22:00 UTC ≠ 22:00 local time — confirm timezone with user before setting schedule
