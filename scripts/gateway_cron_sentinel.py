#!/usr/bin/env python3
"""Lightweight Gateway/Cron Sentinel for Hermes operations.

Runs frequently as a cron pre-check script. It always writes structured logs and
only wakes the LLM/Slack delivery path when a meaningful warning or critical
condition is detected. A final stdout line of {"wakeAgent": false} tells the
Hermes cron scheduler to skip the agent run for healthy checks.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HERMES_HOME = Path(os.getenv("HERMES_HOME", "/opt/data"))
LOCAL_TZ = ZoneInfo(os.getenv("HERMES_OPS_TZ", "Europe/Paris"))
LOGS_DIR = HERMES_HOME / "logs"
JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
CRON_RUNS_DIR = LOGS_DIR / "cron_runs"
CRON_OUTPUT_DIR = HERMES_HOME / "cron" / "output"
SENTINEL_DIR = LOGS_DIR / "gateway_sentinel"
RUN_LOG_DIR = LOGS_DIR / "cron_runs" / "gateway-cron-sentinel"
INCIDENT_LOG = LOGS_DIR / "incident_log.md"
GATEWAY_LOG = LOGS_DIR / "gateway.log"
ERRORS_LOG = LOGS_DIR / "errors.log"
GATEWAY_RESTART_LOG = LOGS_DIR / "gateway_restarts.log"
STATE_FILE = HERMES_HOME / "state" / "gateway_cron_sentinel_state.json"

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d{3})?")
DUP_GATEWAY_RE = re.compile(r"Another gateway instance is already running", re.IGNORECASE)
SLACK_DISCONNECT_RE = re.compile(r"(slack.*disconnect|socket mode.*disconnect|app token already in use)", re.IGNORECASE)
SLACK_CONNECT_RE = re.compile(r"(Socket Mode connected|slack connected|✓ slack connected)", re.IGNORECASE)
CRON_TICKER_RE = re.compile(r"Cron ticker started", re.IGNORECASE)
SHUTDOWN_NOISE_RE = re.compile(r"(unhandled exception during asyncio\.run\(\) shutdown|Task exception was never retrieved|Task was destroyed|KeyboardInterrupt)", re.IGNORECASE)
# CLI-origin shutdown noise: tracebacks referencing cli.py _signal_handler (interactive TTY sessions via ttyd).
# These are not gateway crashes — they happen when a user closes a browser tab or the PTY is disconnected.
# We exclude them from the gateway shutdown_noise count to avoid false-positive WARNING alerts.
CLI_SHUTDOWN_NOISE_RE = re.compile(r"cli\.py.*_signal_handler|_signal_handler.*cli\.py", re.IGNORECASE)
DELIVERY_ERROR_RE = re.compile(r"(send error|send failed|fallback send also failed|channel_not_found|not_in_channel|delivery failed|could not deliver)", re.IGNORECASE)


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


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def write_run_log(label: str, output: str, now: datetime) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = RUN_LOG_DIR / f"{now.date().isoformat()}.log"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n--- {label} at {iso(now)} ---\n")
        fh.write(output.rstrip() + "\n")
    return path


def load_state() -> dict[str, Any]:
    data = safe_read_json(STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:
        pass


def collect_gateway_processes() -> dict[str, Any]:
    try:
        proc = subprocess.run(["ps", "-eo", "pid=,ppid=,stat=,lstart=,args="], text=True, capture_output=True, timeout=8)
        lines = proc.stdout.splitlines()
    except Exception as exc:
        return {"error": str(exc), "canonical": [], "wrappers": [], "count": 0}

    canonical: list[dict[str, Any]] = []
    wrappers: list[dict[str, Any]] = []
    for line in lines:
        if "hermes gateway run" not in line or "gateway_cron_sentinel.py" in line:
            continue
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        pid, ppid, stat = parts[0], parts[1], parts[2]
        lstart = " ".join(parts[3:8])
        cmd = parts[8]
        item = {"pid": int(pid), "ppid": int(ppid), "stat": stat, "started": lstart, "cmd": cmd[:300]}
        if "python" in cmd and ("/usr/local/bin/hermes gateway run" in cmd or cmd.strip().endswith("hermes gateway run")):
            canonical.append(item)
        elif "bash" in cmd or "sh -" in cmd:
            wrappers.append(item)
        elif "/usr/local/bin/hermes gateway run" in cmd:
            canonical.append(item)
    return {"canonical": canonical, "wrappers": wrappers, "count": len(canonical)}


def scan_log_patterns(path: Path, start: datetime, end: datetime, patterns: dict[str, re.Pattern[str]], max_examples: int = 5, exclude_block_patterns: dict[str, re.Pattern[str]] | None = None) -> dict[str, Any]:
    """Scan a log file for pattern matches within a time window.

    Args:
        path: Log file path.
        start / end: UTC datetime window (inclusive).
        patterns: Dict of name -> compiled regex to count/collect.
        max_examples: Max example lines to keep per pattern.
        exclude_block_patterns: Optional dict of name -> compiled regex.
            When a traceback block (lines within the same timestamp context)
            contains a match for the exclude pattern, hits for that pattern
            name are suppressed for the entire block.  Use this to strip
            CLI-origin noise (e.g. cli.py _signal_handler) from counts that
            are meant to track gateway-origin events.
    """
    counters: Counter[str] = Counter()
    examples: dict[str, list[str]] = {name: [] for name in patterns}
    last_seen: dict[str, str] = {}
    if not path.exists():
        return {"missing": True, "counts": {}, "examples": examples, "last_seen": last_seen}

    exclude_block_patterns = exclude_block_patterns or {}

    # We do a two-pass approach within the time window:
    # collect lines grouped by "block" (a block starts at each timestamped line
    # and runs until the next timestamped line), then evaluate each block.
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    # Build blocks: list of (timestamp, [lines_in_block])
    blocks: list[tuple[datetime, list[str]]] = []
    current_ts: datetime | None = None
    current_block: list[str] = []

    def flush_block() -> None:
        if current_ts is not None and current_block:
            if start <= current_ts <= end:
                blocks.append((current_ts, list(current_block)))

    for line in lines:
        parsed = parse_log_ts(line)
        if parsed:
            flush_block()
            current_ts = parsed
            current_block = [line]
        else:
            current_block.append(line)
    flush_block()

    for block_ts, block_lines in blocks:
        block_text = "\n".join(block_lines)
        # Check which exclude patterns fire anywhere in this block
        excluded_names: set[str] = set()
        for name, excl_re in exclude_block_patterns.items():
            if excl_re.search(block_text):
                excluded_names.add(name)

        for line in block_lines:
            for name, pattern in patterns.items():
                if name in excluded_names:
                    continue
                if pattern.search(line):
                    counters[name] += 1
                    last_seen[name] = iso(block_ts)
                    if len(examples[name]) < max_examples:
                        examples[name].append(line[:500])

    return {"missing": False, "counts": dict(counters), "examples": examples, "last_seen": last_seen}


def latest_log_match(path: Path, pattern: re.Pattern[str]) -> datetime | None:
    if not path.exists():
        return None
    latest: datetime | None = None
    current_ts: datetime | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = parse_log_ts(line)
        if parsed:
            current_ts = parsed
        if current_ts and pattern.search(line):
            latest = current_ts
    return latest


def count_recent_cron_audit_records(start: datetime, end: datetime, valid_job_ids: set[str]) -> dict[str, Any]:
    total = 0
    success = 0
    failed = 0
    delivery_errors = 0
    ignored_unknown_job_ids = 0
    latest: datetime | None = None
    parse_errors = 0
    days = []
    day = start.date()
    while day <= end.date():
        days.append(day.isoformat())
        day += timedelta(days=1)
    for day_s in days:
        path = CRON_RUNS_DIR / f"{day_s}.jsonl"
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
            if rec.get("success") is True or rec.get("status") == "ok":
                success += 1
            else:
                failed += 1
            if rec.get("delivery_error"):
                delivery_errors += 1
            if dt and (latest is None or dt > latest):
                latest = dt
    return {"total": total, "success": success, "failed": failed, "delivery_errors": delivery_errors, "latest_at": iso(latest) if latest else None, "parse_errors": parse_errors, "ignored_unknown_job_ids": ignored_unknown_job_ids}


def infer_recent_outputs(jobs: list[dict[str, Any]], start: datetime, end: datetime) -> dict[str, Any]:
    count = 0
    latest: datetime | None = None
    for job in jobs:
        job_id = job.get("id")
        if not job_id:
            continue
        job_dir = CRON_OUTPUT_DIR / str(job_id)
        if not job_dir.exists():
            continue
        for path in job_dir.glob("*.md"):
            try:
                # Filenames are YYYY-MM-DD_HH-MM-SS.md in UTC.
                stem = path.stem
                dt = datetime.strptime(stem, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if start <= dt <= end:
                count += 1
                if latest is None or dt > latest:
                    latest = dt
    return {"count": count, "latest_at": iso(latest) if latest else None, "latest_local": fmt_local(latest)}


def classify_jobs(now: datetime, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    enabled = [j for j in jobs if j.get("enabled", True) and j.get("state") != "paused"]
    failed = []
    delivery_failed = []
    overdue = []
    for job in enabled:
        if job.get("last_status") in {"error", "failed"}:
            failed.append({"id": job.get("id"), "name": job.get("name"), "last_error": job.get("last_error")})
        if job.get("last_delivery_error"):
            delivery_failed.append({"id": job.get("id"), "name": job.get("name"), "last_delivery_error": job.get("last_delivery_error")})
        next_run = parse_iso(job.get("next_run_at"))
        if next_run and next_run < now - timedelta(minutes=20):
            overdue.append({"id": job.get("id"), "name": job.get("name"), "next_run_at": job.get("next_run_at"), "next_run_local": fmt_local(next_run)})
    return {"total": len(jobs), "enabled": len(enabled), "failed": failed, "delivery_failed": delivery_failed, "overdue": overdue}


def append_incident(record: dict[str, Any], state: dict[str, Any], now: datetime) -> bool:
    incident_key = record["incident_key"]
    last_key = f"last_incident_{incident_key}"
    last_dt = parse_iso(state.get(last_key))
    cooldown = timedelta(hours=6)
    if last_dt and now - last_dt < cooldown:
        return False
    INCIDENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with INCIDENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {now.date().isoformat()} — Gateway/Cron Sentinel: {record['severity'].upper()} — {record['title']}\n")
        fh.write(f"- Time: {fmt_local(now)}\n")
        fh.write(f"- Summary: {record['summary']}\n")
        if record.get("evidence"):
            fh.write("- Evidence:\n")
            for item in record["evidence"][:6]:
                fh.write(f"  - {item}\n")
    state[last_key] = iso(now)
    return True


def evaluate() -> dict[str, Any]:
    now = utc_now()
    short_window_start = now - timedelta(minutes=20)
    long_window_start = now - timedelta(hours=24)
    jobs_data = safe_read_json(JOBS_FILE, {"jobs": []})
    jobs = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else []
    state = load_state()
    if not state.get("activated_at"):
        state["activated_at"] = iso(now)
    activated_at = parse_iso(state.get("activated_at")) or now

    valid_job_ids = {str(job.get("id")) for job in jobs if job.get("id")}
    process_info = collect_gateway_processes()
    gateway_patterns = scan_log_patterns(
        GATEWAY_LOG,
        short_window_start,
        now,
        {
            "duplicate_gateway_start": DUP_GATEWAY_RE,
            "slack_disconnect": SLACK_DISCONNECT_RE,
            "shutdown_noise": SHUTDOWN_NOISE_RE,
            "delivery_error": DELIVERY_ERROR_RE,
        },
    )
    errors_patterns = scan_log_patterns(
        ERRORS_LOG,
        short_window_start,
        now,
        {
            "duplicate_gateway_start": DUP_GATEWAY_RE,
            "slack_disconnect": SLACK_DISCONNECT_RE,
            "shutdown_noise": SHUTDOWN_NOISE_RE,
            "delivery_error": DELIVERY_ERROR_RE,
        },
        # Exclude traceback blocks that contain cli.py _signal_handler — those
        # are interactive TTY sessions (ttyd/pts) being closed, not gateway crashes.
        exclude_block_patterns={"shutdown_noise": CLI_SHUTDOWN_NOISE_RE},
    )
    restart_patterns = scan_log_patterns(
        GATEWAY_RESTART_LOG,
        long_window_start,
        now,
        {"gateway_start": re.compile(r"GATEWAY START", re.IGNORECASE), "gateway_start_skipped": re.compile(r"GATEWAY START SKIPPED", re.IGNORECASE)},
    )

    latest_slack_connect = latest_log_match(GATEWAY_LOG, SLACK_CONNECT_RE)
    latest_cron_ticker = latest_log_match(GATEWAY_LOG, CRON_TICKER_RE)
    audit = count_recent_cron_audit_records(long_window_start, now, valid_job_ids)
    output_fallback = infer_recent_outputs(jobs, long_window_start, now)
    output_fallback_count = int(output_fallback.get("count", 0))
    job_status = classify_jobs(now, jobs)

    issues: list[dict[str, Any]] = []

    canonical_count = process_info.get("count", 0)
    if process_info.get("error"):
        issues.append({"severity": "warning", "code": "process_scan_failed", "title": "Gateway process scan failed", "summary": process_info["error"], "evidence": []})
    elif canonical_count == 0:
        issues.append({"severity": "critical", "code": "gateway_process_absent", "title": "Gateway process is absent", "summary": "No canonical Hermes gateway process was found.", "evidence": [json.dumps(p, ensure_ascii=False) for p in process_info.get("wrappers", [])[:3]]})
    elif canonical_count > 1:
        issues.append({"severity": "critical", "code": "duplicate_gateway_processes", "title": "Duplicate gateway processes detected", "summary": f"Found {canonical_count} canonical Hermes gateway processes.", "evidence": [json.dumps(p, ensure_ascii=False) for p in process_info.get("canonical", [])[:5]]})

    duplicate_count = gateway_patterns["counts"].get("duplicate_gateway_start", 0) + errors_patterns["counts"].get("duplicate_gateway_start", 0)
    if duplicate_count:
        issues.append({"severity": "warning", "code": "duplicate_gateway_start_attempts", "title": "Duplicate gateway start attempts detected", "summary": f"Detected {duplicate_count} duplicate gateway start log event(s) in the last 20 minutes.", "evidence": gateway_patterns["examples"].get("duplicate_gateway_start", []) + errors_patterns["examples"].get("duplicate_gateway_start", [])})

    slack_disconnect_count = gateway_patterns["counts"].get("slack_disconnect", 0) + errors_patterns["counts"].get("slack_disconnect", 0)
    if slack_disconnect_count and (latest_slack_connect is None or latest_slack_connect < short_window_start):
        issues.append({"severity": "critical", "code": "slack_disconnected", "title": "Slack connection may be down", "summary": "Slack disconnect/token conflict events appeared recently and no recent reconnect was observed.", "evidence": gateway_patterns["examples"].get("slack_disconnect", []) + errors_patterns["examples"].get("slack_disconnect", [])})

    if latest_cron_ticker is None and canonical_count > 0:
        issues.append({"severity": "warning", "code": "cron_ticker_not_observed", "title": "Cron ticker startup not observed", "summary": "Gateway is running, but no 'Cron ticker started' log line was found.", "evidence": []})

    shutdown_count = gateway_patterns["counts"].get("shutdown_noise", 0) + errors_patterns["counts"].get("shutdown_noise", 0)
    if shutdown_count >= 2:
        issues.append({"severity": "warning", "code": "gateway_shutdown_noise", "title": "Gateway shutdown noise detected", "summary": f"Detected {shutdown_count} shutdown-noise events in the last 20 minutes.", "evidence": gateway_patterns["examples"].get("shutdown_noise", []) + errors_patterns["examples"].get("shutdown_noise", [])})

    delivery_log_count = gateway_patterns["counts"].get("delivery_error", 0) + errors_patterns["counts"].get("delivery_error", 0)
    if delivery_log_count or job_status["delivery_failed"]:
        issues.append({"severity": "critical", "code": "delivery_errors", "title": "Cron/gateway delivery errors detected", "summary": f"Delivery evidence: {delivery_log_count} log event(s), {len(job_status['delivery_failed'])} job state error(s).", "evidence": gateway_patterns["examples"].get("delivery_error", []) + errors_patterns["examples"].get("delivery_error", []) + [json.dumps(x, ensure_ascii=False) for x in job_status["delivery_failed"][:3]]})

    if job_status["failed"]:
        issues.append({"severity": "critical", "code": "cron_job_failed", "title": "Cron job failure state detected", "summary": f"{len(job_status['failed'])} enabled job(s) have failed last_status.", "evidence": [json.dumps(x, ensure_ascii=False) for x in job_status["failed"][:5]]})

    if job_status["overdue"]:
        issues.append({"severity": "critical", "code": "cron_job_overdue", "title": "Cron job appears overdue", "summary": f"{len(job_status['overdue'])} enabled job(s) have next_run_at older than the grace window.", "evidence": [json.dumps(x, ensure_ascii=False) for x in job_status["overdue"][:5]]})

    if audit["parse_errors"]:
        issues.append({"severity": "warning", "code": "cron_audit_parse_errors", "title": "Cron audit JSONL parse errors", "summary": f"Detected {audit['parse_errors']} malformed cron audit record(s) in the last 24 hours.", "evidence": []})

    if audit["total"] == 0 and output_fallback_count > 0:
        latest_output_dt = parse_iso(output_fallback.get("latest_at"))
        post_activation_output = bool(latest_output_dt and latest_output_dt > activated_at)
        last_audit_warning = parse_iso(state.get("last_audit_missing_warning"))
        if post_activation_output and (last_audit_warning is None or now - last_audit_warning > timedelta(hours=24)):
            issues.append({"severity": "warning", "code": "cron_audit_missing_with_outputs", "title": "Cron audit records missing but outputs exist", "summary": f"No JSONL audit records in the last 24 hours, but {output_fallback_count} saved cron output(s) exist; latest output: {output_fallback.get('latest_local')}.", "evidence": []})
            state["last_audit_missing_warning"] = iso(now)

    severity_rank = {"ok": 0, "warning": 1, "critical": 2}
    status = "ok"
    for issue in issues:
        if severity_rank[issue["severity"]] > severity_rank[status]:
            status = issue["severity"]

    record = {
        "schema_version": 1,
        "event": "gateway_cron_sentinel_check",
        "checked_at": iso(now),
        "checked_at_local": fmt_local(now),
        "status": status,
        "wake_agent": status != "ok",
        "process": process_info,
        "logs": {
            "gateway_short_window": gateway_patterns,
            "errors_short_window": errors_patterns,
            "restart_24h": restart_patterns,
            "latest_slack_connect": iso(latest_slack_connect) if latest_slack_connect else None,
            "latest_slack_connect_local": fmt_local(latest_slack_connect),
            "latest_cron_ticker": iso(latest_cron_ticker) if latest_cron_ticker else None,
            "latest_cron_ticker_local": fmt_local(latest_cron_ticker),
        },
        "cron": {
            "jobs": job_status,
            "audit_24h": audit,
            "output_fallback_24h": output_fallback,
        },
        "issues": issues,
    }

    append_jsonl(SENTINEL_DIR / f"{now.date().isoformat()}.jsonl", record)

    incident_written = False
    for issue in issues:
        if issue["severity"] in {"warning", "critical"}:
            incident_written = append_incident({"incident_key": issue["code"], **issue}, state, now) or incident_written
    record["incident_written"] = incident_written
    state["last_run_at"] = iso(now)
    state["last_status"] = status
    state["last_issue_codes"] = [i["code"] for i in issues]
    save_state(state)
    return record


def build_stdout(record: dict[str, Any]) -> str:
    status = record["status"]
    lines = [
        f"Gateway/Cron Sentinel status: {status.upper()}",
        f"Checked: {record['checked_at_local']}",
        f"Gateway processes: {record['process'].get('count', 0)} canonical, {len(record['process'].get('wrappers', []))} wrapper(s)",
        f"Cron jobs: {record['cron']['jobs']['enabled']} enabled / {record['cron']['jobs']['total']} total",
        f"Cron audit 24h: {record['cron']['audit_24h']['total']} records, {record['cron']['audit_24h']['failed']} failed, {record['cron']['audit_24h']['delivery_errors']} delivery errors",
        f"Saved cron outputs 24h: {record['cron']['output_fallback_24h'].get('count', 0)}",
        f"Latest Slack connect: {record['logs']['latest_slack_connect_local']}",
        f"Latest cron ticker: {record['logs']['latest_cron_ticker_local']}",
    ]
    if record["issues"]:
        lines.append("Issues:")
        for issue in record["issues"]:
            lines.append(f"- {issue['severity'].upper()} {issue['code']}: {issue['summary']}")
            for ev in issue.get("evidence", [])[:2]:
                lines.append(f"  evidence: {ev}")
    else:
        lines.append("No actionable issues detected.")
    lines.append(f"SENTINEL_LOG: {SENTINEL_DIR / (record['checked_at'][:10] + '.jsonl')}")
    lines.append(f"INCIDENT_LOG: {INCIDENT_LOG}")
    if not record["wake_agent"]:
        lines.append(json.dumps({"wakeAgent": False}, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def main() -> int:
    record = evaluate()
    output = build_stdout(record)
    run_log = write_run_log("gateway-cron-sentinel", output, utc_now())
    if "{\"wakeAgent\":false}" not in output:
        output += f"RUN_LOG: {run_log}\n"
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
