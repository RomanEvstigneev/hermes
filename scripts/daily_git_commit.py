#!/usr/bin/env python3
"""
Daily Git Auto-Commit Script
Checks for changes in /opt/data, commits and pushes if any exist.
Outputs a summary for Hermes to relay to Slack.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_DIR = "/opt/data"

def run(cmd, check=True):
    result = subprocess.run(
        cmd, shell=True, cwd=REPO_DIR,
        capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"ERROR running: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
    return result

def main():
    now = datetime.now(tz=timezone.utc)
    date_label = now.strftime("%Y-%m-%d")

    # Check for any changes (staged, unstaged, untracked)
    status = run("git status --porcelain")
    lines = [l for l in status.stdout.strip().splitlines() if l.strip()]

    # Filter out runtime/temp files we never want to commit
    IGNORE_PATTERNS = [
        "gateway.pid", "gateway_state.json", "processes.json",
        "pastes/", "channel_directory.json",
    ]
    def should_ignore(path):
        for pat in IGNORE_PATTERNS:
            if pat in path:
                return True
        return False

    lines = [l for l in lines if not should_ignore(l)]

    if not lines:
        print(f"=== DAILY GIT COMMIT: {date_label} ===")
        print("STATUS: no_changes")
        print("No changes to commit.")
        return

    # Categorize changes
    added    = [l[3:] for l in lines if l.startswith("A ") or l.startswith("?? ")]
    modified = [l[3:] for l in lines if l.startswith(" M") or l.startswith("M ")]
    deleted  = [l[3:] for l in lines if l.startswith(" D") or l.startswith("D ")]

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

    # Output summary
    print(f"=== DAILY GIT COMMIT: {date_label} ===")
    print(f"STATUS: {'pushed' if push_ok else 'push_failed'}")
    print(f"Files changed: {len(lines)}")
    if modified: print(f"Modified ({len(modified)}): {', '.join(modified)}")
    if added:    print(f"Added ({len(added)}): {', '.join(added)}")
    if deleted:  print(f"Deleted ({len(deleted)}): {', '.join(deleted)}")
    if not push_ok:
        print(f"Push error: {push_result.stderr.strip()}")

if __name__ == "__main__":
    main()
