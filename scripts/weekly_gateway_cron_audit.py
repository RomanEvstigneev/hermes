#!/usr/bin/env python3
"""Weekly deeper audit for Hermes gateway and cron operations.

Collects trend evidence from the lightweight sentinel, structured cron audit
records, jobs.json, gateway logs, and incident log. The cron LLM turns this JSON
into a concise founder-readable weekly report.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HERMES_HOME = Path(os.getenv("HERMES_HOME", "/opt/data"))
LOCAL_TZ = ZoneInfo(os.getenv("HERMES_OPS_TZ", "Europe/Paris"))
LOGS_DIR = HERMES_HOME / "logs"
JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
CRON_RUNS_DIR = LOGS_DIR / "cron_runs"
SENTINEL_DIR = LOGS_DIR / "gateway_sentinel"
REPORTS_DIR = LOGS_DIR / "gateway_cron_weekly_audit"
RUN_LOG_DIR = LOGS_DIR / "cron_runs" / "weekly-gateway-cron-audit"
INCIDENT_LOG = LOGS_DIR / "incident_log.md"
GATEWAY_LOG = LOGS_DIR / "gateway.log"
ERRORS_LOG = LOGS_DIR / "errors.log"
GATEWAY_RESTART_LOG = LOGS_DIR / "gateway_restarts.log"

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d{3})?")
PATTERNS = {
    "duplicate_gateway_start": re.compile(r"Another gateway instance is already running|GATEWAY START SKIPPED", re.IGNORECASE),
    "slack_disconnect_or_token_conflict": re.compile(r"slack.*disconnect|socket mode.*disconnect|app token already in use", re.IGNORECASE),
    "shutdown_noise": re.compile(r"unhandled exception during asyncio\.run\(\) shutdown|Task exception was never retrieved|Task was destroyed|KeyboardInterrupt", re.IGNORECASE),
    "delivery_error": re.compile(r"send error|send failed|fallback send also failed|channel_not_found|not_in_channel|delivery failed|could not deliver", re.IGNORECASE),
    "cron_ticker_started": re.compile(r"Cron ticker started", re.IGNORECASE),
    "gateway_running": re.compile(r"Gateway running with", re.IGNORECASE),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def fmt_local(dt: datetime | None) -> str:
    if not dt:
        return "never"
    return dt.astimezone(LOCAL_TZ).strftime("%d %b %H:%M %Z")


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


def parse_log_ts(line: str) -> datetime | None:
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def safe_read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "path": str(path)}
    return default


def append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def iter_days(start: datetime, end: datetime):
    day = start.date()
    while day <= end.date():
        yield day.isoformat()
        day += timedelta(days=1)


def load_sentinel_records(start: datetime, end: datetime) -> dict[str, Any]:
    records = []
    parse_errors = 0
    for day in iter_days(start, end):
        path = SENTINEL_DIR / f"{day}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                parse_errors += 1
                continue
            dt = parse_iso(rec.get("checked_at"))
            if dt and start <= dt <= end:
                records.append(rec)
    status_counts = Counter(rec.get("status", "unknown") for rec in records)
    issue_counts = Counter()
    issue_examples = defaultdict(list)
    for rec in records:
        for issue in rec.get("issues", []):
            code = issue.get("code", "unknown")
            issue_counts[code] += 1
            if len(issue_examples[code]) < 3:
                issue_examples[code].append({"checked_at_local": rec.get("checked_at_local"), "severity": issue.get("severity"), "summary": issue.get("summary")})
    return {
        "records": len(records),
        "parse_errors": parse_errors,
        "status_counts": dict(status_counts),
        "issue_counts": dict(issue_counts),
        "issue_examples": dict(issue_examples),
        "first_record_local": records[0].get("checked_at_local") if records else None,
        "last_record_local": records[-1].get("checked_at_local") if records else None,
    }


def load_cron_audit(start: datetime, end: datetime, valid_job_ids: set[str]) -> dict[str, Any]:
    total = success = failed = delivery_errors = parse_errors = ignored_unknown_job_ids = 0
    by_job: dict[str, dict[str, Any]] = {}
    for day in iter_days(start, end):
        path = CRON_RUNS_DIR / f"{day}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                parse_errors += 1
                continue
            if rec.get("event") != "cron_job_run":
                continue
            if valid_job_ids and str(rec.get("job_id")) not in valid_job_ids:
                ignored_unknown_job_ids += 1
                continue
            dt = parse_iso(rec.get("ended_at") or rec.get("started_at"))
            if dt and not (start <= dt <= end):
                continue
            total += 1
            ok = rec.get("success") is True or rec.get("status") == "ok"
            if ok:
                success += 1
            else:
                failed += 1
            if rec.get("delivery_error"):
                delivery_errors += 1
            job_id = str(rec.get("job_id") or "unknown")
            item = by_job.setdefault(job_id, {"job_name": rec.get("job_name"), "runs": 0, "success": 0, "failed": 0, "delivery_errors": 0})
            item["runs"] += 1
            item["success"] += int(ok)
            item["failed"] += int(not ok)
            item["delivery_errors"] += int(bool(rec.get("delivery_error")))
    return {"total": total, "success": success, "failed": failed, "delivery_errors": delivery_errors, "parse_errors": parse_errors, "ignored_unknown_job_ids": ignored_unknown_job_ids, "by_job": by_job}


def scan_logs(start: datetime, end: datetime) -> dict[str, Any]:
    result = {}
    for path in [GATEWAY_LOG, ERRORS_LOG, GATEWAY_RESTART_LOG]:
        counts = Counter()
        examples = defaultdict(list)
        if path.exists():
            current_ts: datetime | None = None
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                parsed = parse_log_ts(line)
                if parsed:
                    current_ts = parsed
                if current_ts is None or not (start <= current_ts <= end):
                    continue
                for name, pattern in PATTERNS.items():
                    if pattern.search(line):
                        counts[name] += 1
                        if len(examples[name]) < 3:
                            examples[name].append(line[:500])
        result[path.name] = {"counts": dict(counts), "examples": dict(examples), "exists": path.exists()}
    return result


def collect_jobs(now: datetime) -> dict[str, Any]:
    data = safe_read_json(JOBS_FILE, {"jobs": []})
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    rows = []
    for job in jobs:
        last_run = parse_iso(job.get("last_run_at"))
        next_run = parse_iso(job.get("next_run_at"))
        rows.append({
            "id": job.get("id"),
            "name": job.get("name"),
            "enabled": job.get("enabled"),
            "state": job.get("state"),
            "schedule": job.get("schedule_display") or (job.get("schedule") or {}).get("display") if isinstance(job.get("schedule"), dict) else job.get("schedule"),
            "last_status": job.get("last_status"),
            "last_delivery_error": job.get("last_delivery_error"),
            "last_run_local": fmt_local(last_run),
            "next_run_local": fmt_local(next_run),
            "overdue": bool(next_run and next_run < now - timedelta(minutes=20) and job.get("enabled", True) and job.get("state") != "paused"),
        })
    return {"total": len(rows), "enabled": sum(1 for r in rows if r["enabled"] and r["state"] != "paused"), "jobs": rows}


def incident_excerpt(start: datetime, end: datetime) -> list[str]:
    if not INCIDENT_LOG.exists():
        return []
    lines = INCIDENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    selected: list[str] = []
    include = False
    for line in lines:
        if line.startswith("## ") and "Gateway/Cron Sentinel" in line:
            include = False
            m = re.search(r"## (\d{4}-\d{2}-\d{2})", line)
            if m:
                try:
                    dt = datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
                    include = start.date() <= dt.date() <= end.date()
                except Exception:
                    include = False
        if include:
            selected.append(line[:500])
    return selected[-80:]


def recommendations(report: dict[str, Any]) -> list[str]:
    recs = []
    sentinel_issues = report["sentinel"].get("issue_counts", {})
    cron = report["cron_audit"]
    logs = report["logs"]
    if sentinel_issues.get("duplicate_gateway_processes") or sentinel_issues.get("duplicate_gateway_start_attempts"):
        recs.append("Gateway lifecycle: keep a single authoritative startup path and investigate duplicate start attempts if they persist despite /hermes.sh guard.")
    if sentinel_issues.get("cron_audit_missing_with_outputs") or (cron["total"] == 0 and report["jobs"]["enabled"] > 0):
        recs.append("Cron observability: verify that the running gateway imported the patched scheduler and that cron_runs JSONL records are created after each job.")
    if cron["failed"] or cron["delivery_errors"]:
        recs.append("Cron reliability: inspect failed job audit records and last_delivery_error fields before changing schedules.")
    if any(v["counts"].get("slack_disconnect_or_token_conflict") for v in logs.values()):
        recs.append("Slack gateway: investigate Socket Mode disconnect/token conflict patterns and avoid blind restarts without cooldown.")
    if not recs:
        recs.append("No new action recommended this week if the next daily health report remains clean.")
    return recs[:4]


def build_report() -> dict[str, Any]:
    now = utc_now()
    start = now - timedelta(days=7)
    report = {
        "schema_version": 1,
        "event": "weekly_gateway_cron_audit",
        "generated_at": iso(now),
        "generated_at_local": fmt_local(now),
        "window_start": iso(start),
        "window_end": iso(now),
        "window_local": f"{fmt_local(start)} to {fmt_local(now)}",
    }
    report["jobs"] = collect_jobs(now)
    valid_job_ids = {str(job.get("id")) for job in report["jobs"]["jobs"] if job.get("id")}
    report["sentinel"] = load_sentinel_records(start, now)
    report["cron_audit"] = load_cron_audit(start, now, valid_job_ids)
    report["logs"] = scan_logs(start, now)
    report["incident_excerpt"] = incident_excerpt(start, now)

    issue_count = sum(report["sentinel"].get("issue_counts", {}).values())
    critical_signals = 0
    critical_signals += int(report["cron_audit"]["failed"] > 0)
    critical_signals += int(report["cron_audit"]["delivery_errors"] > 0)
    critical_signals += int(any(r.get("overdue") for r in report["jobs"]["jobs"]))
    critical_signals += int(report["sentinel"].get("status_counts", {}).get("critical", 0) > 0)
    if critical_signals:
        status = "Needs attention"
    elif issue_count or report["sentinel"].get("status_counts", {}).get("warning", 0):
        status = "Watch"
    else:
        status = "Healthy"
    report["overall_status"] = status
    report["recommendations"] = recommendations(report)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{now.date().isoformat()}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report


def build_stdout(report: dict[str, Any]) -> str:
    lines = [
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        f"REPORT_PATH: {report['report_path']}",
        f"RUN_LOG_PATH: {RUN_LOG_DIR / (report['generated_at'][:10] + '.log')}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    report = build_report()
    output = build_stdout(report)
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    append_log(RUN_LOG_DIR / f"{report['generated_at'][:10]}.log", output)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
