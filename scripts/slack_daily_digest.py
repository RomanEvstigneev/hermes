#!/usr/bin/env python3
"""
Slack Daily Digest Script
Collects messages from all channels the bot is a member of
for the previous day and outputs a structured summary for Hermes to process.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Use the hermes-agent venv where slack_sdk is installed
VENV_SITE_PACKAGES = "/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages"
if VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load token from env file if not already set
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

def get_user_display_name(user_id: str, user_cache: dict) -> str:
    if user_id in user_cache:
        return user_cache[user_id]
    try:
        resp = client.users_info(user=user_id)
        profile = resp["user"].get("profile", {})
        name = profile.get("display_name") or profile.get("real_name") or user_id
        user_cache[user_id] = name
        return name
    except Exception:
        user_cache[user_id] = user_id
        return user_id

def get_bot_channels():
    """Get all channels the bot is a member of."""
    channels = []
    cursor = None
    while True:
        kwargs = {
            "types": "public_channel,private_channel",
            "exclude_archived": True,
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor
        try:
            resp = client.conversations_list(**kwargs)
        except SlackApiError as e:
            print(f"ERROR listing channels: {e}", file=sys.stderr)
            break

        for ch in resp.get("channels", []):
            if ch.get("is_member"):
                channels.append({
                    "id": ch["id"],
                    "name": ch.get("name", ch["id"]),
                    "is_private": ch.get("is_private", False),
                })
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return channels

def get_channel_messages(channel_id: str, oldest: float, latest: float) -> list:
    """Fetch messages from a channel within a time range."""
    messages = []
    cursor = None
    while True:
        kwargs = {
            "channel": channel_id,
            "oldest": str(oldest),
            "latest": str(latest),
            "limit": 200,
            "inclusive": True,
        }
        if cursor:
            kwargs["cursor"] = cursor
        try:
            resp = client.conversations_history(**kwargs)
        except SlackApiError as e:
            err = str(e)
            if "not_in_channel" in err or "channel_not_found" in err:
                break
            print(f"WARN: conversations.history error for {channel_id}: {e}", file=sys.stderr)
            break

        for msg in resp.get("messages", []):
            # Skip bot messages, join/leave events, etc.
            if msg.get("subtype") in ("bot_message", "channel_join", "channel_leave",
                                      "bot_add", "bot_remove", "channel_purpose",
                                      "channel_topic", "channel_name"):
                continue
            if msg.get("bot_id"):
                continue
            messages.append(msg)

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor or not resp.get("has_more"):
            break
        time.sleep(0.3)  # rate limit

    return messages

def format_channel_data(channel: dict, messages: list, user_cache: dict) -> dict:
    """Format messages for a channel into structured data."""
    formatted_messages = []
    for msg in messages:
        user_id = msg.get("user", "unknown")
        user_name = get_user_display_name(user_id, user_cache)
        text = msg.get("text", "").strip()
        # Resolve user mentions in text
        if text:
            import re
            def replace_mention(m):
                uid = m.group(1)
                return f"@{get_user_display_name(uid, user_cache)}"
            text = re.sub(r"<@([A-Z0-9]+)>", replace_mention, text)
        ts = float(msg.get("ts", 0))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        formatted_messages.append({
            "time": dt.strftime("%H:%M"),
            "user": user_name,
            "text": text,
            "thread_count": msg.get("reply_count", 0),
        })

    return {
        "channel": channel["name"],
        "is_private": channel["is_private"],
        "message_count": len(formatted_messages),
        "messages": formatted_messages,
    }

def main():
    # Calculate time range: yesterday 00:00 - 23:59:59 UTC
    now = datetime.now(tz=timezone.utc)
    yesterday = now - timedelta(days=1)
    day_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)

    oldest = day_start.timestamp()
    latest = day_end.timestamp()

    date_label = yesterday.strftime("%Y-%m-%d (%A)")

    print(f"=== SLACK DAILY DIGEST: {date_label} ===\n", flush=True)

    channels = get_bot_channels()
    if not channels:
        print("No channels found where the bot is a member.")
        return

    print(f"Found {len(channels)} channel(s) to scan: {', '.join('#' + c['name'] for c in channels)}\n")

    user_cache = {}
    all_channel_data = []

    for channel in channels:
        time.sleep(0.5)  # gentle rate limiting
        messages = get_channel_messages(channel["id"], oldest, latest)
        if not messages:
            continue
        data = format_channel_data(channel, messages, user_cache)
        all_channel_data.append(data)

    if not all_channel_data:
        print(f"No messages found in any channel for {date_label}.")
        return

    # Output structured data for the AI to summarize
    print(f"=== RAW DATA FOR SUMMARIZATION ===")
    print(f"Date: {date_label}")
    print(f"Total channels with activity: {len(all_channel_data)}\n")

    for ch_data in all_channel_data:
        private_label = " [private]" if ch_data["is_private"] else ""
        print(f"--- #{ch_data['channel']}{private_label} ({ch_data['message_count']} messages) ---")
        for msg in ch_data["messages"]:
            thread_note = f" [+{msg['thread_count']} replies]" if msg["thread_count"] > 0 else ""
            print(f"[{msg['time']}] {msg['user']}: {msg['text']}{thread_note}")
        print()

def output_memory_context():
    """Read and output existing memory files so the cron agent has context."""
    memory_dir = "/opt/data/memory"
    if not os.path.exists(memory_dir):
        return

    print("\n=== MEMORY CONTEXT ===")
    print("(Use this to enrich the digest — who people are, recurring topics, open questions)\n")

    index_path = os.path.join(memory_dir, "MEMORY_INDEX.md")
    if os.path.exists(index_path):
        with open(index_path) as f:
            print("--- MEMORY_INDEX.md ---")
            print(f.read())

    for subdir in ("people", "channels"):
        dirpath = os.path.join(memory_dir, subdir)
        if not os.path.exists(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(dirpath, fname)
            with open(fpath) as f:
                print(f"--- memory/{subdir}/{fname} ---")
                print(f.read())


if __name__ == "__main__":
    main()
    output_memory_context()
