#!/usr/bin/env python3
"""Collect operational evidence for the daily closed-loop operations review.

Scope:
- Previous UTC calendar day only.
- Hermes sessions, logs, cron job state, cron output/audit logs, and prior proposal state.
- No Slack workspace content is collected.

The LLM cron prompt uses this evidence to propose at most one improvement to an
existing process, or to recommend no action. The prompt is responsible for
updating the persistent state file with the selected proposal/no-action record
before returning the Slack-ready message.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.getenv("HERMES_HOME", "/opt/data"))
SESSIONS_DIR = HERMES_HOME / "sessions"
LOGS_DIR = HERMES_HOME / "logs"
CRON_DIR = HERMES_HOME / "cron"
CRON_OUTPUT_DIR = CRON_DIR / "output"
JOBS_FILE = CRON_DIR / "jobs.json"
STATE_DIR = HERMES_HOME / "state"
STATE_FILE = STATE_DIR / "closed_loop_ops_review.json"
REPORTS_DIR = LOGS_DIR / "closed_loop_ops_review"
RUN_LOG_DIR = LOGS_DIR / "cron_runs" / "closed-loop-ops-review"
CRON_RUNS_DIR = LOGS_DIR / "cron_runs"

LOG_FILES = [
    LOGS_DIR / "agent.log",
    LOGS_DIR / "errors.log",
    LOGS_DIR / "gateway.log",
    LOGS_DIR / "gateway_restarts.log",
]

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d{3})?")
SESSION_FILE_RE = re.compile(r"session_(cron_)?(?:(?P<jobid>[a-f0-9]{12})_)?(?P<stamp>\d{8}_\d{6})")
NOISE_ROLES = {"system"}
MAX_TEXT = 700
MAX_ITEMS = 25
SLACK_CONTENT_SCRIPTS = {
    "slack_daily_digest.py",
    "slack_memory_update.py",
    "slack_memory_weekly.py",
    "slack_memory_monthly.py",
}

KEY_PATTERNS = {
    "errors": re.compile(r"\b(error|exception|traceback|failed|failure|crash)\b", re.IGNORECASE),
    "warnings": re.compile(r"\b(warn|warning|degraded|retry|timeout)\b", re.IGNORECASE),
    "delivery": re.compile(r"\b(delivery|send error|channel_not_found|not_in_channel|fallback send)\b", re.IGNORECASE),
    "approval": re.compile(r"\b(approve|approval|confirm|permission|dangerous)\b", re.IGNORECASE),
    "follow_up": re.compile(r"\b(follow[- ]?up|implemented|plan approved|approved plan|proposal)\b", re.IGNORECASE),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def previous_utc_day(now: datetime) -> tuple[datetime, datetime, str]:
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    start = today_start - timedelta(days=1)
    end = today_start - timedelta(microseconds=1)
    return start, end, start.strftime("%Y-%m-%d")


def safe_read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "path": str(path)}
    return default


def truncate(text: Any, limit: int = MAX_TEXT) -> str:
    s = str(text or "").replace("\x00", "").strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > limit:
        return s[: limit - 3] + "..."
    return s


def dt_from_session_filename(path: Path) -> datetime | None:
    m = SESSION_FILE_RE.search(path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("stamp"), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def message_text(msg: dict[str, Any]) -> str:
    content = msg.get("content")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False) if content is not None else ""


def classify_text(text: str) -> list[str]:
    labels = []
    for label, pattern in KEY_PATTERNS.items():
        if pattern.search(text):
            labels.append(label)
    return labels


def slack_content_job_ids() -> set[str]:
    """Return cron job IDs whose outputs may contain Slack workspace content."""
    jobs_data = safe_read_json(JOBS_FILE, {"jobs": []})
    jobs = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else []
    return {
        str(job.get("id"))
        for job in jobs
        if job.get("script") in SLACK_CONTENT_SCRIPTS and job.get("id")
    }


def collect_sessions(start: datetime, end: datetime) -> dict[str, Any]:
    sessions = []
    counters = Counter()
    tool_counter = Counter()
    issue_snippets = []
    sensitive_job_ids = slack_content_job_ids()

    for path in sorted(SESSIONS_DIR.glob("session_*.json")):
        file_dt = dt_from_session_filename(path)
        if file_dt and not (start <= file_dt <= end):
            continue
        data = safe_read_json(path, None)
        if not isinstance(data, dict):
            continue
        session_start = parse_iso(data.get("session_start")) or file_dt
        last_updated = parse_iso(data.get("last_updated")) or session_start
        if not session_start or not (start <= session_start <= end or start <= last_updated <= end):
            continue
        filename_match = SESSION_FILE_RE.search(path.name)
        cron_job_id = filename_match.group("jobid") if filename_match else None
        suppress_content_samples = data.get("platform") == "slack" or cron_job_id in sensitive_job_ids

        messages = data.get("messages") or []
        roles = Counter(m.get("role", "unknown") for m in messages if isinstance(m, dict))
        user_prompts = []
        final_responses = []
        session_labels = Counter()
        empty_assistant_messages = 0
        tool_calls = 0

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "unknown")
            text = message_text(msg)
            labels = classify_text(text)
            session_labels.update(labels)
            if suppress_content_samples:
                # Keep metadata/labels only. Do not include Slack workspace content
                # from Slack-platform sessions or Slack-derived cron sessions.
                continue
            if role == "user" and len(user_prompts) < 3:
                # Exclude internal skill-save reminders when possible.
                if not text.startswith("Review the conversation above and consider saving"):
                    user_prompts.append(truncate(text, 260))
            elif role == "assistant":
                if not text.strip():
                    empty_assistant_messages += 1
                elif len(final_responses) < 2:
                    final_responses.append(truncate(text, 300))
                if msg.get("tool_calls"):
                    try:
                        for call in msg.get("tool_calls") or []:
                            name = (((call or {}).get("function") or {}).get("name")) or (call or {}).get("name") or "unknown"
                            tool_counter[name] += 1
                            tool_calls += 1
                    except Exception:
                        pass
            elif role == "tool":
                tool_calls += 1

        counters.update({
            "sessions": 1,
            f"platform:{data.get('platform', 'unknown')}": 1,
            f"model:{data.get('model', 'unknown')}": 1,
        })
        if path.name.startswith("session_cron_"):
            counters["cron_sessions"] += 1
        if session_labels:
            for label, count in session_labels.items():
                counters[f"label:{label}"] += count

        session_summary = {
            "file": str(path),
            "session_id": data.get("session_id"),
            "platform": data.get("platform"),
            "model": data.get("model"),
            "session_start": session_start.isoformat() if session_start else None,
            "last_updated": last_updated.isoformat() if last_updated else None,
            "message_count": data.get("message_count", len(messages)),
            "role_counts": dict(roles),
            "tool_or_tool_call_events": tool_calls,
            "empty_assistant_messages": empty_assistant_messages,
            "detected_labels": dict(session_labels),
            "sample_user_prompts": user_prompts,
            "sample_final_responses": final_responses,
            "content_samples_suppressed": suppress_content_samples,
            "suppression_reason": "Slack workspace content excluded" if suppress_content_samples else None,
        }
        sessions.append(session_summary)

        if session_labels and len(issue_snippets) < MAX_ITEMS:
            issue_snippets.append({
                "session_file": str(path),
                "labels": dict(session_labels),
                "sample_user_prompts": user_prompts[:2],
                "sample_final_responses": final_responses[:1],
            })

    return {
        "summary_counts": dict(counters),
        "top_tools": tool_counter.most_common(20),
        "sessions": sessions[-MAX_ITEMS:],
        "sessions_total_in_window": len(sessions),
        "issue_snippets": issue_snippets,
    }


def load_run_records_for_day(day_label: str) -> list[dict[str, Any]]:
    records = []
    path = CRON_RUNS_DIR / f"{day_label}.jsonl"
    if not path.exists():
        return records
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            rec["source_file"] = str(path)
            records.append(rec)
        except Exception as exc:
            records.append({"source_file": str(path), "line_no": line_no, "parse_error": str(exc), "raw_preview": truncate(line, 300)})
    return records


def collect_cron(start: datetime, end: datetime, day_label: str) -> dict[str, Any]:
    jobs_data = safe_read_json(JOBS_FILE, {"jobs": []})
    jobs = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else []
    sensitive_job_ids = {
        str(job.get("id"))
        for job in jobs
        if job.get("script") in SLACK_CONTENT_SCRIPTS and job.get("id")
    }
    run_records = load_run_records_for_day(day_label)
    runs_by_job = defaultdict(list)
    for rec in run_records:
        runs_by_job[rec.get("job_id") or "unknown"].append(rec)

    job_summaries = []
    for job in jobs:
        last_run = parse_iso(job.get("last_run_at"))
        related_runs = runs_by_job.get(job.get("id"), [])
        failures = [r for r in related_runs if r.get("status") != "ok" or r.get("error") or r.get("delivery_error")]
        job_summaries.append({
            "job_id": job.get("id"),
            "name": job.get("name"),
            "enabled": job.get("enabled"),
            "state": job.get("state"),
            "schedule": job.get("schedule_display"),
            "script": job.get("script"),
            "deliver": job.get("deliver"),
            "last_run_at": job.get("last_run_at"),
            "last_status": job.get("last_status"),
            "last_error": job.get("last_error"),
            "last_delivery_error": job.get("last_delivery_error"),
            "ran_in_previous_day": bool(last_run and start <= last_run <= end),
            "audit_runs_in_previous_day": len(related_runs),
            "audit_failures_in_previous_day": failures[-3:],
            "prompt_preview": truncate(job.get("prompt"), 500),
        })

    output_summaries = []
    for job_dir in sorted(CRON_OUTPUT_DIR.glob("*")):
        if not job_dir.is_dir():
            continue
        for out in sorted(job_dir.glob("*.md"))[-5:]:
            try:
                mtime = datetime.fromtimestamp(out.stat().st_mtime, tz=timezone.utc)
            except Exception:
                continue
            if start <= mtime <= end:
                if job_dir.name in sensitive_job_ids:
                    txt = "[Preview suppressed: this cron output may contain Slack workspace content.]"
                    labels = []
                else:
                    try:
                        txt = out.read_text(encoding="utf-8", errors="replace")
                    except Exception as exc:
                        txt = f"READ_ERROR: {exc}"
                    labels = classify_text(txt)
                output_summaries.append({
                    "file": str(out),
                    "mtime": mtime.isoformat(),
                    "preview": truncate(txt, 900),
                    "labels": labels,
                    "preview_suppressed": job_dir.name in sensitive_job_ids,
                })

    return {
        "jobs_file": str(JOBS_FILE),
        "jobs_total": len(jobs),
        "jobs_enabled": sum(1 for j in jobs if j.get("enabled", True)),
        "job_summaries": job_summaries,
        "audit_records_count": len(run_records),
        "audit_records_path": str(CRON_RUNS_DIR / f"{day_label}.jsonl"),
        "output_summaries": output_summaries[-MAX_ITEMS:],
    }


def scan_log(path: Path, start: datetime, end: datetime, max_matches: int = 80) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "matches": []}
    matches = []
    counts = Counter()
    current_ts: datetime | None = None
    current_ts_str = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return {"path": str(path), "exists": True, "read_error": str(exc), "matches": []}

    for line in lines:
        m = TS_RE.match(line)
        if m:
            current_ts_str = m.group(1)
            try:
                current_ts = datetime.strptime(current_ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                current_ts = None
        if current_ts and start <= current_ts <= end:
            labels = classify_text(line)
            if labels:
                for label in labels:
                    counts[label] += 1
                if len(matches) < max_matches:
                    matches.append({"timestamp": current_ts_str, "labels": labels, "line": truncate(line, 500)})
    return {"path": str(path), "exists": True, "label_counts": dict(counts), "matches": matches[-max_matches:]}


def collect_logs(start: datetime, end: datetime) -> dict[str, Any]:
    scans = [scan_log(path, start, end) for path in LOG_FILES]
    combined = Counter()
    for scan in scans:
        combined.update(scan.get("label_counts", {}))
    return {"combined_label_counts": dict(combined), "log_scans": scans}


def summarize_recent_state(state: dict[str, Any]) -> dict[str, Any]:
    proposals = state.get("proposals", []) if isinstance(state, dict) else []
    if not isinstance(proposals, list):
        proposals = []
    recent = proposals[-20:]
    open_items = [p for p in recent if p.get("status") in {"proposed", "approved_for_plan", "plan_approved", "implementation_started"}]
    implemented_recent = [p for p in recent if p.get("status") == "implemented"][-10:]
    rejected_recent = [p for p in recent if p.get("status") == "rejected"][-10:]
    return {
        "state_file": str(STATE_FILE),
        "state_exists": STATE_FILE.exists(),
        "total_records": len(proposals),
        "recent_records": recent,
        "open_items_requiring_follow_up": open_items,
        "recent_implemented_items": implemented_recent,
        "recent_rejected_items": rejected_recent,
        "dedupe_instruction": "Do not repeat recent proposal fingerprints unless there is a materially new signal in yesterday's evidence.",
    }


def main() -> None:
    now = utc_now()
    start, end, day_label = previous_utc_day(now)
    state = safe_read_json(STATE_FILE, {"schema_version": 1, "proposals": []})

    report = {
        "schema_version": 1,
        "report_type": "daily_closed_loop_ops_review_evidence",
        "generated_at": now.isoformat(),
        "analysis_window": {
            "timezone": "UTC",
            "date": day_label,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "note": "This is the previous UTC calendar day. The cron schedule is fixed at 04:00 UTC, equivalent to 05:00 CET in winter.",
        },
        "scope": {
            "included": [
                "Hermes session files under /opt/data/sessions",
                "Hermes logs under /opt/data/logs",
                "Cron job definitions and statuses under /opt/data/cron/jobs.json",
                "Cron output files under /opt/data/cron/output",
                "Cron audit/log files under /opt/data/logs/cron_runs",
                "Persistent proposal state under /opt/data/state/closed_loop_ops_review.json",
            ],
            "excluded": ["Slack workspace channel/message content"],
        },
        "state_summary": summarize_recent_state(state if isinstance(state, dict) else {}),
        "sessions": collect_sessions(start, end),
        "cron": collect_cron(start, end, day_label),
        "logs": collect_logs(start, end),
        "decision_rules_for_llm": [
            "Recommend at most one initiative.",
            "If evidence is weak, impact is low, or the idea is not tied to an existing process/job/script/log/session, recommend no action.",
            "Do not recommend net-new workflows or processes.",
            "Do not repeat recent proposal fingerprints unless yesterday adds a materially new signal.",
            "Use business language first and technical evidence second.",
            "Do not implement anything from the cron job; request approval first.",
            "If an open item exists in state, provide follow-up status before considering a new recommendation.",
        ],
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{day_label}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(report_path, 0o600)
    report["saved_report_path"] = str(report_path)
    report["state_file_to_update_before_final_response"] = str(STATE_FILE)

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def write_run_log(captured_output: str) -> str:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    _, _, day_label = previous_utc_day(now)
    log_path = RUN_LOG_DIR / f"{now.strftime('%Y-%m-%d')}.log"
    header = (
        "=== Daily Closed-Loop Operations Review Collector ===\n"
        f"Generated at: {now.isoformat()}\n"
        f"Analysis date: {day_label} UTC\n"
        f"State file: {STATE_FILE}\n"
        "Scope: sessions, logs, cron state/output; Slack workspace content excluded.\n"
        f"{'=' * 72}\n\n"
    )
    log_path.write_text(header + captured_output, encoding="utf-8")
    os.chmod(log_path, 0o600)
    print(f"\nLOG_PATH: {log_path}", flush=True)
    return str(log_path)


if __name__ == "__main__":
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main()
    output = buf.getvalue()
    sys.stdout.write(output)
    sys.stdout.flush()
    write_run_log(output)
