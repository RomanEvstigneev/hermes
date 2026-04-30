#!/usr/bin/env python3
"""
Slack Memory Weekly Review Script — Phase 3
Collects last 7 days of messages + outputs memory files for pruning.
"""

import os
import sys
import time
import re
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
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")

load_env_file()
client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN", ""))

def get_bot_channels():
    channels = []
    try:
        resp = client.conversations_list(types="public_channel,private_channel",
                                          exclude_archived=True, limit=200)
        for ch in resp.get("channels", []):
            if ch.get("is_member"):
                channels.append({"id": ch["id"], "name": ch.get("name", ch["id"])})
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
    return channels

def get_channel_messages(channel_id, oldest, latest):
    messages = []
    try:
        resp = client.conversations_history(channel=channel_id, oldest=str(oldest),
                                             latest=str(latest), limit=1000, inclusive=True)
        for msg in resp.get("messages", []):
            if msg.get("subtype") or msg.get("bot_id"):
                continue
            messages.append(msg)
    except SlackApiError:
        pass
    return messages

def get_username(user_id, cache):
    if user_id in cache:
        return cache[user_id]
    try:
        resp = client.users_info(user=user_id)
        profile = resp["user"].get("profile", {})
        name = profile.get("real_name") or profile.get("display_name") or user_id
        cache[user_id] = name
    except Exception:
        cache[user_id] = user_id
    return cache[user_id]

def output_memory_files():
    print("\n=== EXISTING MEMORY FILES ===\n")
    for subdir in ("people", "channels"):
        dirpath = os.path.join(MEMORY_DIR, subdir)
        if not os.path.exists(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if fname.endswith(".md"):
                with open(os.path.join(dirpath, fname)) as f:
                    print(f"--- memory/{subdir}/{fname} ---")
                    print(f.read())

def main():
    now = datetime.now(tz=timezone.utc)
    week_start = now - timedelta(days=7)
    oldest = week_start.timestamp()
    latest = now.timestamp()
    week_label = f"{week_start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}"

    print(f"=== SLACK MEMORY WEEKLY REVIEW ===")
    print(f"Period: {week_label}\n")

    channels = get_bot_channels()
    user_cache = {}

    for channel in channels:
        time.sleep(0.4)
        messages = get_channel_messages(channel["id"], oldest, latest)
        if not messages:
            print(f"--- #{channel['name']}: no activity this week ---\n")
            continue
        print(f"--- #{channel['name']} ({len(messages)} messages this week) ---")
        # Count unique active users
        active_users = set()
        for msg in messages:
            uid = msg.get("user")
            if uid:
                active_users.add(get_username(uid, user_cache))
        print(f"Active participants: {', '.join(active_users)}")
        # Sample a few messages for context
        for msg in messages[:5]:
            uid = msg.get("user", "unknown")
            text = msg.get("text", "")[:120]
            ts = datetime.fromtimestamp(float(msg.get("ts", 0)), tz=timezone.utc)
            print(f"  [{ts.strftime('%m-%d %H:%M')}] {get_username(uid, user_cache)}: {text}")
        if len(messages) > 5:
            print(f"  ... and {len(messages) - 5} more messages")
        print()

    output_memory_files()

if __name__ == "__main__":
    main()
