#!/usr/bin/env python3
"""
Boilerplate for cron data-collection scripts.
Replace JOB_SLUG and call main() + any other functions inside the redirect block.
"""
import io, os, sys, contextlib
from datetime import datetime, timezone
from pathlib import Path

JOB_SLUG = "my-job-name"  # e.g. "slack-daily-digest", "memory-enrichment"


def write_run_log(label: str, captured_output: str) -> str:
    """Save a detailed run log and return its path."""
    log_dir = Path(f"/opt/data/logs/cron_runs/{JOB_SLUG}")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}.log"
    header = (
        f"=== {JOB_SLUG} Run Log ===\n"
        f"Label: {label}\n"
        f"Script ran at: {datetime.now(tz=timezone.utc).isoformat()}\n"
        f"{'='*50}\n\n"
    )
    log_path.write_text(header + captured_output, encoding="utf-8")
    # Print to stdout so the LLM cron prompt can reference the path
    print(f"\nLOG_PATH: {log_path}", flush=True)
    return str(log_path)


def main():
    # Your data-collection logic here
    print("Hello from main()")


if __name__ == "__main__":
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main()
        # Add any other output functions here, e.g. output_memory_context()
    output = buf.getvalue()
    sys.stdout.write(output)
    sys.stdout.flush()
    label = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    write_run_log(label, output)
