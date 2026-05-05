#!/usr/bin/env python3
"""Collect meaningful Hermes cron health data for the daily Slack report.

The report separates execution health from observability/gateway warnings:
- Structured audit records: /opt/data/logs/cron_runs/YYYY-MM-DD.jsonl
- Fallback evidence: /opt/data/cron/output/<job_id>/*.md and jobs.json
- Human Slack summary: concise, CET/CEST times, no operational file paths in the executive section
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HERMES_HOME = Path(os.getenv("HERMES_HOME", "/opt/data"))
JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
CRON_RUNS_DIR = HERMES_HOME / "logs" / "cron_runs"
CRON_OUTPUT_DIR = HERMES_HOME / "cron" / "output"
REPORTS_DIR = HERMES_HOME / "logs" / "cron_health_reports"
AGENT_LOG = HERMES_HOME / "logs" / "agent.log"
ERRORS_LOG = HERMES_HOME / "logs" / "errors.log"
GATEWAY_LOG = HERMES_HOME / "logs" / "gateway.log"
GATEWAY_RESTART_LOG = HERMES_HOME / "logs" / "gateway_restarts.log"
LOCAL_TZ = ZoneInfo(os.getenv("CRON_HEALTH_TZ", "Europe/Paris"))

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d{3})?")
OUTPUT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})\.md$")
_DELIVERY_ERROR_RE = re.compile(
    r"(send error|send failed|fallback send also failed|channel_not_found|"
    r"not_in_channel|delivery failed|could not deliver|chat\.postMessage)",
    re.IGNORECASE,
)
_RESTART_RE = re.compile(r"(gateway.*start|cron ticker started|exiting with code)", re.IGNORECASE)
_DUPLICATE_GATEWAY_RE = re.compile(r"Another gateway instance is already running", re.IGNORECASE)
_SHUTDOWN_NOISE_RE = re.compile(
    r"(unhandled exception during asyncio\.run\(\) shutdown|Task exception was never retrieved|Input/output error|KeyboardInterrupt|Task was destroyed)",
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


def fmt_local(value: str | datetime | None) -> str:
    dt = parse_iso(value) if isinstance(value, str) else value
    if not dt:
        return "never"
    local = dt.astimezone(LOCAL_TZ)
    return local.strftime("%d %b %H:%M %Z")


def fmt_window(start: datetime, end: datetime) -> str:
    return f"{fmt_local(start)} to {fmt_local(end)}"


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
                    "success": False,
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


def infer_output_runs(jobs: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Infer successful runs from saved cron output files when JSONL audit is missing."""
    records: list[dict[str, Any]] = []
    job_by_id = {j.get("id"): j for j in jobs}
    if not CRON_OUTPUT_DIR.exists():
        return records
    for job_id, job in job_by_id.items():
        if not job_id:
            continue
        job_dir = CRON_OUTPUT_DIR / str(job_id)
        if not job_dir.exists():
            continue
        for path in job_dir.glob("*.md"):
            m = OUTPUT_RE.match(path.name)
            if not m:
                continue
            dt = datetime(
                int(m.group(1)[:4]),
                int(m.group(1)[5:7]),
                int(m.group(1)[8:10]),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                tzinfo=timezone.utc,
            )
            if start <= dt <= end:
                records.append({
                    "event": "cron_job_run_inferred_from_output",
                    "job_id": job_id,
                    "job_name": job.get("name"),
                    "started_at": dt.isoformat(),
                    "ended_at": dt.isoformat(),
                    "status": "ok" if job.get("last_status") != "error" else "unknown",
                    "success": job.get("last_status") != "error",
                    "error": None,
                    "delivery_error": job.get("last_delivery_error"),
                    "output_file": str(path),
                    "source": "cron_output_fallback",
                })
    records.sort(key=lambda r: r.get("ended_at") or r.get("started_at") or "")
    return records


def read_log_excerpt(path: Path, start: datetime, end: datetime, max_lines: int = 120) -> list[str]:
    if not path.exists():
        return []
    selected: list[str] = []
    current_ts: datetime | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS_RE.match(line)
        if m:
            try:
                current_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                current_ts = None
        if current_ts and start <= current_ts <= end:
            low = line.lower()
            if any(token in low for token in (" error ", " warning ", "failed", "traceback", "exception", "delivery failed")):
                selected.append(line)
    return selected[-max_lines:]


def scan_delivery_errors(path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    current_ts: datetime | None = None
    current_ts_str = ""
    block: list[str] = []

    def flush(ts_str: str, block_lines: list[str]) -> None:
        text = " ".join(block_lines)
        if _DELIVERY_ERROR_RE.search(text):
            events.append({"timestamp": ts_str, "time_local": fmt_local(datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)), "type": "delivery_error", "detail": text.strip()[:400]})

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS_RE.match(line)
        if m:
            if current_ts and start <= current_ts <= end and block:
                flush(current_ts_str, block)
            current_ts_str = m.group(1)
            try:
                current_ts = datetime.strptime(current_ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                current_ts = None
            block = [line]
        else:
            block.append(line)
    if current_ts and start <= current_ts <= end and block:
        flush(current_ts_str, block)
    return events


def scan_gateway_restarts(path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            m = TS_RE.match(line)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if start <= ts <= end:
                events.append({"timestamp": m.group(1), "time_local": fmt_local(ts), "source": "gateway_restarts.log", "detail": line})
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
                events.append({"timestamp": m.group(1), "time_local": fmt_local(ts), "source": "gateway.log", "detail": line.strip()})
    events.sort(key=lambda e: e["timestamp"])
    return events


def classify_log_issues(lines: list[str]) -> dict[str, Any]:
    duplicate_gateway = [line for line in lines if _DUPLICATE_GATEWAY_RE.search(line)]
    shutdown_noise = [line for line in lines if _SHUTDOWN_NOISE_RE.search(line)]
    other_errors = [
        line for line in lines
        if ("ERROR" in line or "WARNING" in line) and line not in duplicate_gateway and line not in shutdown_noise
    ]
    return {
        "duplicate_gateway_start_attempts": len(duplicate_gateway),
        "shutdown_noise_events": len(shutdown_noise),
        "other_error_or_warning_events": len(other_errors),
        "examples": {
            "duplicate_gateway": duplicate_gateway[:2],
            "shutdown_noise": shutdown_noise[:2],
            "other": other_errors[:3],
        },
    }


def summarize(jobs: list[dict[str, Any]], audit_records: list[dict[str, Any]], inferred_records: list[dict[str, Any]], start: datetime, end: datetime) -> dict[str, Any]:
    records_for_execution = audit_records if audit_records else inferred_records
    evidence_source = "jsonl_audit" if audit_records else ("output_fallback" if inferred_records else "jobs_state_only")
    runs_by_job: dict[str, list[dict[str, Any]]] = {}
    for rec in records_for_execution:
        runs_by_job.setdefault(rec.get("job_id") or "unknown", []).append(rec)

    job_summaries = []
    for job in jobs:
        jid = job.get("id")
        runs = runs_by_job.get(jid, [])
        failures = [r for r in runs if r.get("status") != "ok" or r.get("error") or r.get("delivery_error")]
        successes = [r for r in runs if (r.get("status") == "ok" or r.get("success") is True) and not r.get("error") and not r.get("delivery_error")]
        last_run_dt = parse_iso(job.get("last_run_at"))
        next_run_dt = parse_iso(job.get("next_run_at"))
        ran_in_window = bool(runs) or (last_run_dt is not None and start <= last_run_dt <= end)
        not_due = next_run_dt is not None and not ran_in_window and job.get("last_status") != "error"
        if failures or job.get("last_status") == "error" or job.get("last_delivery_error"):
            status = "FAILED"
        elif ran_in_window:
            status = "OK"
        elif not_due:
            status = "NOT DUE"
        else:
            status = "NO RUN IN WINDOW"
        job_summaries.append({
            "job_id": jid,
            "name": job.get("name"),
            "enabled": job.get("enabled"),
            "state": job.get("state"),
            "schedule": job.get("schedule_display"),
            "next_run_at": job.get("next_run_at"),
            "next_run_local": fmt_local(job.get("next_run_at")),
            "last_run_at": job.get("last_run_at"),
            "last_run_local": fmt_local(job.get("last_run_at")),
            "last_status": job.get("last_status"),
            "display_status": status,
            "last_error": job.get("last_error"),
            "last_delivery_error": job.get("last_delivery_error"),
            "runs_in_window": len(runs),
            "successful_runs_in_window": len(successes),
            "failed_runs_in_window": len(failures),
            "ran_in_window": ran_in_window,
            "recent_failures": failures[-5:],
        })

    failed_records = [r for r in records_for_execution if r.get("status") != "ok" or r.get("error") or r.get("delivery_error")]
    jobs_with_failures = [j for j in job_summaries if j["failed_runs_in_window"] or j.get("last_status") == "error" or j.get("last_delivery_error")]
    return {
        "total_jobs": len(jobs),
        "enabled_jobs": sum(1 for j in jobs if j.get("enabled", True)),
        "execution_evidence_source": evidence_source,
        "audit_records_in_window": len(audit_records),
        "inferred_output_runs_in_window": len(inferred_records),
        "runs_in_window": len(records_for_execution),
        "successful_runs": len([r for r in records_for_execution if (r.get("status") == "ok" or r.get("success") is True) and not r.get("error") and not r.get("delivery_error")]),
        "failed_or_delivery_error_runs": len(failed_records),
        "jobs_with_failures": len(jobs_with_failures),
        "jobs_without_runs_in_window": [j["name"] for j in job_summaries if j["enabled"] and j["display_status"] == "NO RUN IN WINDOW"],
        "job_summaries": job_summaries,
    }


def compute_overall_status(summary: dict[str, Any], audit_active: bool, log_issues: dict[str, Any]) -> str:
    if summary["jobs_with_failures"] or summary["failed_or_delivery_error_runs"]:
        return "Failing"
    if not audit_active or summary["execution_evidence_source"] != "jsonl_audit":
        return "Degraded"
    # shutdown_noise_events are mostly benign prompt_toolkit teardown artifacts
    # (asyncio.run() shutdown, Task destroyed) that occur on every normal CLI exit.
    # We only escalate to Degraded when there are *also* duplicate gateway start attempts,
    # which signals a real concurrent-gateway problem.
    if log_issues["duplicate_gateway_start_attempts"]:
        return "Degraded"
    return "Healthy"


def main() -> None:
    end = utc_now()
    hours = int(os.getenv("CRON_HEALTH_WINDOW_HOURS", "24"))
    start = end - timedelta(hours=hours)

    jobs = load_jobs()
    valid_job_ids = {str(job.get("id")) for job in jobs if job.get("id")}
    raw_audit_records = load_run_records(start, end)
    ignored_unknown_audit_records = [
        rec for rec in raw_audit_records
        if rec.get("event") == "cron_job_run" and valid_job_ids and str(rec.get("job_id")) not in valid_job_ids
    ]
    audit_records = [
        rec for rec in raw_audit_records
        if not (rec.get("event") == "cron_job_run" and valid_job_ids and str(rec.get("job_id")) not in valid_job_ids)
    ]
    inferred_records = infer_output_runs(jobs, start, end)
    summary = summarize(jobs, audit_records, inferred_records, start, end)

    delivery_errors = scan_delivery_errors(GATEWAY_LOG, start, end)
    gateway_restarts = scan_gateway_restarts(GATEWAY_RESTART_LOG, start, end)
    error_lines = read_log_excerpt(ERRORS_LOG, start, end)
    agent_lines = read_log_excerpt(AGENT_LOG, start, end)
    gateway_lines = read_log_excerpt(GATEWAY_LOG, start, end)
    log_issues = classify_log_issues(error_lines + agent_lines + gateway_lines)

    summary["delivery_errors_in_window"] = len(delivery_errors)
    summary["gateway_restart_events_in_window"] = len(gateway_restarts)
    summary["duplicate_gateway_start_attempts"] = log_issues["duplicate_gateway_start_attempts"]
    summary["shutdown_noise_events"] = log_issues["shutdown_noise_events"]

    audit_active = any((CRON_RUNS_DIR / f"{day}.jsonl").exists() for day in iter_candidate_days(start, end))
    overall_status = compute_overall_status(summary, audit_active, log_issues)

    report = {
        "schema_version": 3,
        "report_type": "daily_cron_health",
        "generated_at": end.isoformat(),
        "generated_local": fmt_local(end),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "window_local": fmt_window(start, end),
        "timezone": str(LOCAL_TZ),
        "overall_status": overall_status,
        "summary": summary,
        "observability": {
            "json_audit_log_dir": str(CRON_RUNS_DIR),
            "audit_log_active": audit_active,
            "audit_records_in_window": len(audit_records),
            "ignored_unknown_job_audit_records": len(ignored_unknown_audit_records),
            "inferred_output_runs_in_window": len(inferred_records),
            "note": "Execution metrics use JSONL audit records when present; otherwise they are inferred from cron output files and jobs.json.",
        },
        "runs": [{
            "job_id": r.get("job_id"),
            "job_name": r.get("job_name"),
            "started_at": r.get("started_at"),
            "started_local": fmt_local(r.get("started_at")),
            "ended_at": r.get("ended_at"),
            "ended_local": fmt_local(r.get("ended_at")),
            "status": r.get("status"),
            "success": r.get("success"),
            "error": r.get("error"),
            "delivery_error": r.get("delivery_error"),
            "output_file": r.get("output_file"),
            "source": r.get("source") or r.get("source_file"),
        } for r in (audit_records if audit_records else inferred_records)],
        "delivery_errors": delivery_errors,
        "gateway_restart_events": gateway_restarts,
        "log_issues": log_issues,
        "error_log_excerpt": error_lines,
        "agent_log_excerpt": agent_lines,
        "gateway_log_excerpt": gateway_lines,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{end.strftime('%Y-%m-%d')}.json"
    report["saved_report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(report_path, 0o600)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
