#!/usr/bin/env python3
"""Collect Hermes cron health data as JSON for the daily Slack report.

The cron scheduler writes per-run JSONL audit records to:
  /opt/data/logs/cron_runs/YYYY-MM-DD.jsonl

This script reads the last 24 hours by default, combines that audit trail with
current /opt/data/cron/jobs.json state and relevant error log excerpts, writes a
machine-readable report snapshot, and prints JSON for the LLM cron prompt.

It also parses gateway.log for Slack delivery errors and gateway.log +
errors.log for cron-related failures, providing coverage even when JSONL
audit records have not yet been written (e.g. before first gateway restart).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.getenv("HERMES_HOME", "/opt/data"))
JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
CRON_RUNS_DIR = HERMES_HOME / "logs" / "cron_runs"
REPORTS_DIR = HERMES_HOME / "logs" / "cron_health_reports"
AGENT_LOG = HERMES_HOME / "logs" / "agent.log"
ERRORS_LOG = HERMES_HOME / "logs" / "errors.log"
GATEWAY_LOG = HERMES_HOME / "logs" / "gateway.log"
GATEWAY_RESTART_LOG = HERMES_HOME / "logs" / "gateway_restarts.log"

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d{3})?")

# Patterns that indicate a Slack/delivery failure in gateway.log
_DELIVERY_ERROR_RE = re.compile(
    r"(send error|send failed|fallback send also failed|channel_not_found|"
    r"not_in_channel|delivery failed|could not deliver|chat\.postMessage)",
    re.IGNORECASE,
)

# Patterns that indicate a gateway restart event in gateway_restarts.log or gateway.log
_RESTART_RE = re.compile(
    r"(gateway.*start|cron ticker started|exiting with code)",
    re.IGNORECASE,
)


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


def load_jobs() -> list[dict[str, Any]]:
    if not JOBS_FILE.exists():
        return []
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        return data.get("jobs", []) if isinstance(data, dict) else []
    except Exception as exc:
        return [{"id": "__jobs_file_error__", "name": "jobs.json read failed", "last_status": "error", "last_error": str(exc)}]


def iter_candidate_days(start: datetime, end: datetime):
    day = start.date()
    while day <= end.date():
        yield day.isoformat()
        day += timedelta(days=1)


def load_run_records(start: datetime, end: datetime) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for day in iter_candidate_days(start, end):
        path = CRON_RUNS_DIR / f"{day}.jsonl"
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception as exc:
                records.append({
                    "event": "cron_run_log_parse_error",
                    "source_file": str(path),
                    "line_no": line_no,
                    "status": "error",
                    "error": str(exc),
                    "raw_line_preview": line[:500],
                })
                continue
            dt = parse_iso(rec.get("ended_at") or rec.get("started_at"))
            if dt is None or start <= dt <= end:
                rec["source_file"] = str(path)
                records.append(rec)
    records.sort(key=lambda r: r.get("ended_at") or r.get("started_at") or "")
    return records


def read_log_excerpt(path: Path, start: datetime, end: datetime, max_lines: int = 120) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    selected: list[str] = []
    current_ts: datetime | None = None
    for line in lines:
        m = TS_RE.match(line)
        if m:
            try:
                current_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                current_ts = None
        if current_ts and start <= current_ts <= end:
            low = line.lower()
            if any(token in low for token in (
                " error ", " warning ", "failed", "traceback", "exception",
                "cron.scheduler", "running job", "completed successfully", "delivery failed",
            )):
                selected.append(line)
    return selected[-max_lines:]


def scan_delivery_errors(path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Parse gateway.log for Slack/delivery error events in the time window."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[dict[str, Any]] = []
    current_ts: datetime | None = None
    current_ts_str: str = ""
    block: list[str] = []

    def _flush_block(ts_str: str, block_lines: list[str]) -> None:
        text = " ".join(block_lines)
        if _DELIVERY_ERROR_RE.search(text):
            # Extract Slack error detail if present
            detail = text.strip()
            # Try to pull the response body line
            resp_match = re.search(r"The server responded with:\s*(\{[^}]+\})", text)
            events.append({
                "timestamp": ts_str,
                "type": "delivery_error",
                "detail": detail[:400],
                "slack_response": resp_match.group(1) if resp_match else None,
            })

    for line in lines:
        m = TS_RE.match(line)
        if m:
            ts_str = m.group(1)
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                ts = None
            if current_ts and start <= current_ts <= end and block:
                _flush_block(current_ts_str, block)
            current_ts = ts
            current_ts_str = ts_str
            block = [line]
        else:
            # Continuation line (traceback etc.)
            block.append(line)

    # Flush last block
    if current_ts and start <= current_ts <= end and block:
        _flush_block(current_ts_str, block)

    return events


def scan_gateway_restarts(path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Parse gateway_restarts.log (structured) and gateway.log (fallback) for restart events."""
    events: list[dict[str, Any]] = []

    # Primary: structured restart log written by hermes.sh
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            # Format: "2026-05-01 19:00:01 UTC | GATEWAY START | PID=12345"
            m = TS_RE.match(line)
            if m:
                try:
                    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if start <= ts <= end:
                    events.append({"timestamp": m.group(1), "source": "gateway_restarts.log", "detail": line})

    # Fallback / supplement: scan gateway.log for start/stop lines
    if GATEWAY_LOG.exists():
        for line in GATEWAY_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            m = TS_RE.match(line)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if start <= ts <= end and _RESTART_RE.search(line):
                events.append({"timestamp": m.group(1), "source": "gateway.log", "detail": line.strip()})

    events.sort(key=lambda e: e["timestamp"])
    return events


def summarize(jobs: list[dict[str, Any]], records: list[dict[str, Any]], start: datetime, end: datetime) -> dict[str, Any]:
    runs_by_job: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        jid = rec.get("job_id") or "unknown"
        runs_by_job.setdefault(jid, []).append(rec)

    job_summaries = []
    for job in jobs:
        jid = job.get("id")
        runs = runs_by_job.get(jid, [])
        failures = [r for r in runs if r.get("status") != "ok" or r.get("error") or r.get("delivery_error")]
        successes = [r for r in runs if r.get("status") == "ok" and not r.get("error") and not r.get("delivery_error")]
        last_run_dt = parse_iso(job.get("last_run_at"))
        expected_in_window = bool(job.get("enabled", True)) and bool(job.get("schedule_display"))
        job_summaries.append({
            "job_id": jid,
            "name": job.get("name"),
            "enabled": job.get("enabled"),
            "state": job.get("state"),
            "schedule": job.get("schedule_display"),
            "next_run_at": job.get("next_run_at"),
            "last_run_at": job.get("last_run_at"),
            "last_status": job.get("last_status"),
            "last_error": job.get("last_error"),
            "last_delivery_error": job.get("last_delivery_error"),
            "runs_in_window": len(runs),
            "successful_runs_in_window": len(successes),
            "failed_runs_in_window": len(failures),
            "expected_in_window": expected_in_window,
            "ran_in_window": bool(runs) or (last_run_dt is not None and start <= last_run_dt <= end),
            "recent_failures": [{
                "started_at": r.get("started_at"),
                "ended_at": r.get("ended_at"),
                "status": r.get("status"),
                "error": r.get("error"),
                "delivery_error": r.get("delivery_error"),
                "output_file": r.get("output_file"),
            } for r in failures[-5:]],
        })

    unknown_records = [r for r in records if r.get("job_id") not in {j.get("id") for j in jobs}]
    failed_records = [r for r in records if r.get("status") != "ok" or r.get("error") or r.get("delivery_error")]

    return {
        "total_jobs": len(jobs),
        "enabled_jobs": sum(1 for j in jobs if j.get("enabled", True)),
        "runs_in_window": len(records),
        "successful_runs": len([r for r in records if r.get("status") == "ok" and not r.get("error") and not r.get("delivery_error")]),
        "failed_or_delivery_error_runs": len(failed_records),
        "jobs_with_failures": len([j for j in job_summaries if j["failed_runs_in_window"] or j.get("last_status") == "error" or j.get("last_delivery_error")]),
        "jobs_without_runs_in_window": [j["name"] for j in job_summaries if j["enabled"] and not j["ran_in_window"]],
        "unknown_run_records": len(unknown_records),
        "job_summaries": job_summaries,
    }


def main() -> None:
    end = utc_now()
    hours = int(os.getenv("CRON_HEALTH_WINDOW_HOURS", "24"))
    start = end - timedelta(hours=hours)

    jobs = load_jobs()
    records = load_run_records(start, end)
    summary = summarize(jobs, records, start, end)

    # Delivery error scan: structured events from gateway.log
    delivery_errors = scan_delivery_errors(GATEWAY_LOG, start, end)

    # Gateway restart events
    gateway_restarts = scan_gateway_restarts(GATEWAY_RESTART_LOG, start, end)

    # Annotate: if delivery_errors found, flag in summary
    summary["delivery_errors_in_window"] = len(delivery_errors)
    summary["gateway_restarts_in_window"] = len([e for e in gateway_restarts if "START" in e.get("detail", "").upper() or "Cron ticker started" in e.get("detail", "")])

    report = {
        "schema_version": 2,
        "report_type": "daily_cron_health",
        "generated_at": end.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "timezone": "UTC",
        "json_audit_log_dir": str(CRON_RUNS_DIR),
        "audit_log_active": any(
            (CRON_RUNS_DIR / f"{day}.jsonl").exists()
            for day in iter_candidate_days(start, end)
        ),
        "summary": summary,
        "runs": [{
            "job_id": r.get("job_id"),
            "job_name": r.get("job_name"),
            "started_at": r.get("started_at"),
            "ended_at": r.get("ended_at"),
            "status": r.get("status"),
            "success": r.get("success"),
            "error": r.get("error"),
            "delivery_error": r.get("delivery_error"),
            "output_file": r.get("output_file"),
            "source_file": r.get("source_file"),
        } for r in records],
        "delivery_errors": delivery_errors,
        "gateway_restart_events": gateway_restarts,
        "error_log_excerpt": read_log_excerpt(ERRORS_LOG, start, end),
        "agent_log_excerpt": read_log_excerpt(AGENT_LOG, start, end),
        "gateway_log_excerpt": read_log_excerpt(GATEWAY_LOG, start, end),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{end.strftime('%Y-%m-%d')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(report_path, 0o600)
    report["saved_report_path"] = str(report_path)

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
