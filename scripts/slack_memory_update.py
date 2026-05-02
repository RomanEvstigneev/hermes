#!/usr/bin/env python3
"""
Slack Memory Enrichment Script — Phase 2
Collects yesterday's messages + outputs existing memory files.
The cron agent uses this context to update people and channel memory files.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

VENV_SITE_PACKAGES = "/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages"
if VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

MEMORY_DIR = "/opt/data/memory"

def load_env_file():
    env_path = "/opt/data/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = val

load_env_file()

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
if not BOT_TOKEN:
    print("ERROR: SLACK_BOT_TOKEN not set", file=sys.stderr)
    sys.exit(1)

client = WebClient(token=BOT_TOKEN)

def get_user_info(user_id: str, cache: dict) -> dict:
    if user_id in cache:
        return cache[user_id]
    try:
        resp = client.users_info(user=user_id)
        profile = resp["user"].get("profile", {})
        name = profile.get("real_name") or profile.get("display_name") or user_id
        info = {"name": name, "slack_id": user_id}
        cache[user_id] = info
        return info
    except Exception:
        info = {"name": user_id, "slack_id": user_id}
        cache[user_id] = info
        return info

def get_bot_channels():
    channels = []
    cursor = None
    while True:
        kwargs = {"types": "public_channel,private_channel", "exclude_archived": True, "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        try:
            resp = client.conversations_list(**kwargs)
        except SlackApiError as e:
            print(f"ERROR listing channels: {e}", file=sys.stderr)
            break
        for ch in resp.get("channels", []):
            if ch.get("is_member"):
                channels.append({"id": ch["id"], "name": ch.get("name", ch["id"]), "is_private": ch.get("is_private", False)})
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return channels

def get_channel_messages(channel_id: str, oldest: float, latest: float) -> list:
    messages = []
    cursor = None
    while True:
        kwargs = {"channel": channel_id, "oldest": str(oldest), "latest": str(latest), "limit": 200, "inclusive": True}
        if cursor:
            kwargs["cursor"] = cursor
        try:
            resp = client.conversations_history(**kwargs)
        except SlackApiError as e:
            err = str(e)
            if "not_in_channel" in err or "channel_not_found" in err:
                break
            print(f"WARN: {channel_id}: {e}", file=sys.stderr)
            break
        for msg in resp.get("messages", []):
            if msg.get("subtype") in ("bot_message", "channel_join", "channel_leave",
                                      "bot_add", "bot_remove"):
                continue
            if msg.get("bot_id"):
                continue
            messages.append(msg)
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor or not resp.get("has_more"):
            break
        time.sleep(0.3)
    return messages

def output_memory_files():
    """Output all existing memory files for the agent to read."""
    print("\n=== EXISTING MEMORY FILES ===")
    print("(Read these carefully — update them based on today's messages)\n")

    index = os.path.join(MEMORY_DIR, "MEMORY_INDEX.md")
    if os.path.exists(index):
        with open(index) as f:
            print("--- MEMORY_INDEX.md ---")
            print(f.read())

    for subdir in ("people", "channels"):
        dirpath = os.path.join(MEMORY_DIR, subdir)
        if not os.path.exists(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if not fname.endswith(".md"):
                continue
            with open(os.path.join(dirpath, fname)) as f:
                print(f"--- memory/{subdir}/{fname} ---")
                print(f.read())

def main():
    now = datetime.now(tz=timezone.utc)
    yesterday = now - timedelta(days=1)
    day_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
    oldest = day_start.timestamp()
    latest = day_end.timestamp()
    date_label = yesterday.strftime("%Y-%m-%d")

    print(f"=== SLACK MEMORY ENRICHMENT: {date_label} ===\n")

    channels = get_bot_channels()
    user_cache = {}
    has_activity = False

    for channel in channels:
        time.sleep(0.4)
        messages = get_channel_messages(channel["id"], oldest, latest)
        if not messages:
            continue
        has_activity = True
        print(f"--- #{channel['name']} ({len(messages)} messages) ---")
        for msg in messages:
            user_id = msg.get("user", "unknown")
            info = get_user_info(user_id, user_cache)
            import re
            text = msg.get("text", "").strip()
            def replace_mention(m):
                uid = m.group(1)
                return f"@{get_user_info(uid, user_cache)['name']}"
            text = re.sub(r"<@([A-Z0-9]+)>", replace_mention, text)
            ts = float(msg.get("ts", 0))
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            thread_note = f" [+{msg['reply_count']} replies]" if msg.get("reply_count") else ""
            print(f"[{dt.strftime('%H:%M')}] {info['name']} (id:{info['slack_id']}): {text}{thread_note}")
        print()

    # Also output all unique users seen with their real names for profile matching
    if user_cache:
        print("=== USERS SEEN TODAY ===")
        for uid, info in user_cache.items():
            print(f"  {info['name']} — Slack ID: {uid}")
        print()

    if not has_activity:
        print(f"No messages found in any channel for {date_label}.\n")

    # Output existing memory for context
    output_memory_files()

def write_run_log(date_label: str, captured_output: str) -> str:
    """Save a detailed run log and return the path."""
    import pathlib
    log_dir = pathlib.Path("/opt/data/logs/cron_runs/memory-enrichment")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}.log"
    header = (
        f"=== Daily Memory Enrichment Run Log ===\n"
        f"Date range: {date_label}\n"
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
    yesterday_dt = now_dt - timedelta(days=1)
    write_run_log(yesterday_dt.strftime("%Y-%m-%d"), output)
