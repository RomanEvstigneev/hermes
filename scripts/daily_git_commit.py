#!/usr/bin/env python3
"""
Daily Git Auto-Commit Script
Checks for changes in /opt/data, commits and pushes if any exist.
Outputs a summary for Hermes to relay to Slack.
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timezone

REPO_DIR = "/opt/data"

SECRET_PATTERNS = [
    ("Slack bot token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("Slack app token", re.compile(r"xapp-[A-Za-z0-9-]{20,}")),
]
SECRET_REPLACEMENT = "[REDACTED_SECRET]"

def run(cmd, check=True):
    result = subprocess.run(
        cmd, shell=True, cwd=REPO_DIR,
        capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"ERROR running: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
    return result

def parse_porcelain_line(line):
    """Return (status, path) for a git status --porcelain line."""
    status = line[:2]
    # Porcelain v1 uses two status columns, a space, then the path. Be defensive
    # because malformed/manual lines previously caused first-character truncation.
    path = line[3:].strip() if len(line) > 3 and line[2] == " " else line[2:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1].strip()
    return status, path


def business_hint_for_path(path):
    """Convert a repository path into an operator-friendly business impact hint."""
    if path == "cron/jobs.json":
        return "Cron schedule/delivery configuration changed, affecting which automations run and where notifications are sent."
    if path.startswith("cron/output/") or path.startswith("logs/cron_runs/"):
        return "Cron audit/output records were saved, improving traceability of automation runs."
    if path.startswith("scripts/cron_health_report.py") or path.startswith("logs/cron_health_reports/"):
        return "Cron health reporting was added or updated, improving visibility into automation failures."
    if path.startswith("scripts/daily_git_commit.py"):
        return "Daily backup automation was updated, improving backup notifications and change summaries."
    if path.startswith("scripts/slack_memory_") or path.startswith("memory/"):
        return "Slack workspace memory maintenance changed, affecting people/channel context used by Hermes."
    if path.startswith("memories/"):
        return "Hermes persistent memory/profile context changed, affecting future assistant behavior."
    if path.startswith("skills/"):
        return "Hermes operating procedures were updated, improving future troubleshooting and automation behavior."
    if path == "config.yaml" or path.endswith("config.yaml"):
        return "Hermes configuration changed, affecting runtime behavior or integrations."
    return "Repository content changed."


def build_business_summary(paths):
    hints = []
    for path in paths:
        hint = business_hint_for_path(path)
        if hint not in hints:
            hints.append(hint)
    return hints


def redact_secrets_in_file(path):
    """Redact known secret patterns in a text file before it is committed."""
    full_path = os.path.join(REPO_DIR, path)
    if not os.path.isfile(full_path):
        return []
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            original = f.read()
    except OSError:
        return []

    redacted = original
    findings = []
    for label, pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn(SECRET_REPLACEMENT, redacted)
        if count:
            findings.append((label, count))

    if findings and redacted != original:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(redacted)
    return findings


def redact_candidate_files(entries):
    """Sanitize commit candidates while preserving audit/history files in git."""
    redacted = []
    for _, path in entries:
        findings = redact_secrets_in_file(path)
        if findings:
            redacted.append((path, findings))
    return redacted


def main():
    now = datetime.now(tz=timezone.utc)
    date_label = now.strftime("%Y-%m-%d")

    # Check for any changes (staged, unstaged, untracked)
    status = run("git status --porcelain")
    entries = [parse_porcelain_line(l) for l in status.stdout.strip().splitlines() if l.strip()]

    # Filter out runtime/temp files we never want to commit
    IGNORE_PATTERNS = [
        "gateway.pid", "gateway_state.json", "processes.json",
        "pastes/", "channel_directory.json", "kanban.db",
        "backups/", "cache/", "__pycache__/", ".pyc",
    ]
    def should_ignore(path):
        for pat in IGNORE_PATTERNS:
            if pat in path:
                return True
        return False

    entries = [(status_code, path) for status_code, path in entries if not should_ignore(path)]
    redacted_files = redact_candidate_files(entries)

    # Re-read status after redaction because sanitizing files may change tracked files.
    status = run("git status --porcelain")
    entries = [parse_porcelain_line(l) for l in status.stdout.strip().splitlines() if l.strip()]
    entries = [(status_code, path) for status_code, path in entries if not should_ignore(path)]

    if not entries:
        print(f"=== DAILY GIT COMMIT: {date_label} ===")
        print("STATUS: no_changes")
        print("No changes to commit.")
        return

    # Categorize changes
    added    = [path for status_code, path in entries if status_code.startswith("A") or status_code == "??"]
    modified = [path for status_code, path in entries if "M" in status_code and path not in added]
    deleted  = [path for status_code, path in entries if "D" in status_code]

    # Stage everything (except ignored)
    run("git add -A")

    # Un-stage the ignored files just in case
    for pat in IGNORE_PATTERNS:
        run(f"git reset HEAD -- '{pat}' 2>/dev/null || true", check=False)

    # Build commit message
    summary_lines = []
    if modified: summary_lines.append(f"updated: {', '.join(modified[:5])}" + (" ..." if len(modified) > 5 else ""))
    if added:    summary_lines.append(f"added: {', '.join(added[:5])}" + (" ..." if len(added) > 5 else ""))
    if deleted:  summary_lines.append(f"deleted: {', '.join(deleted[:5])}" + (" ..." if len(deleted) > 5 else ""))

    commit_msg = f"chore: daily auto-commit {date_label}\n\n" + "\n".join(summary_lines)
    commit_result = run(f'git commit -m "{commit_msg}"')

    if commit_result.returncode != 0:
        # Nothing actually staged (all were ignored)
        print(f"=== DAILY GIT COMMIT: {date_label} ===")
        print("STATUS: no_changes")
        print("No meaningful changes to commit after filtering.")
        return

    # Push
    push_result = run("git push origin main")
    push_ok = push_result.returncode == 0

    all_paths = modified + added + deleted
    business_summary = build_business_summary(all_paths)

    print(f"=== DAILY GIT COMMIT: {date_label} ===")
    print(f"STATUS: {'pushed' if push_ok else 'push_failed'}")
    print(f"Files changed: {len(entries)}")
    if redacted_files:
        print("Secret redaction: applied before commit")
        for path, findings in redacted_files:
            labels = ", ".join(f"{label} ({count})" for label, count in findings)
            print(f"- {path}: {labels}")
    if modified: print(f"Modified ({len(modified)}): {', '.join(modified)}")
    if added:    print(f"Added ({len(added)}): {', '.join(added)}")
    if deleted:  print(f"Deleted ({len(deleted)}): {', '.join(deleted)}")
    if business_summary:
        print("Business impact hints:")
        for hint in business_summary:
            print(f"- {hint}")
    print("Instruction for Slack summary: explain the practical/business impact of the changes above. Do not list raw file paths unless needed for debugging.")
    if not push_ok:
        print(f"Push error: {push_result.stderr.strip()}")

def write_run_log(date_label: str, captured_output: str) -> str:
    """Save a detailed run log and return the path."""
    import pathlib
    log_dir = pathlib.Path("/opt/data/logs/cron_runs/daily-git-commit")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}.log"
    header = (
        f"=== Daily Git Auto-Commit Run Log ===\n"
        f"Date: {date_label}\n"
        f"Script ran at: {datetime.now(tz=timezone.utc).isoformat()}\n"
        f"{'='*50}\n\n"
    )
    log_path.write_text(header + captured_output, encoding="utf-8")
    print(f"\nLOG_PATH: {log_path}", flush=True)
    return str(log_path)


if __name__ == "__main__":
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main()
    output = buf.getvalue()
    sys.stdout.write(output)
    sys.stdout.flush()
    now_dt = datetime.now(tz=timezone.utc)
    write_run_log(now_dt.strftime("%Y-%m-%d"), output)
