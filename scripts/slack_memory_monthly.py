#!/usr/bin/env python3
"""
Slack Memory Monthly Deep Clean Script — Phase 4
Collects last 30 days of messages + all memory files for deep validation.
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
    cursor = None
    while True:
        try:
            kwargs = {"channel": channel_id, "oldest": str(oldest),
                      "latest": str(latest), "limit": 200, "inclusive": True}
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.conversations_history(**kwargs)
        except SlackApiError:
            break
        for msg in resp.get("messages", []):
            if msg.get("subtype") or msg.get("bot_id"):
                continue
            messages.append(msg)
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor or not resp.get("has_more"):
            break
        time.sleep(0.3)
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

def output_all_memory_files():
    """Output all memory including archive for full validation."""
    print("\n=== ALL MEMORY FILES (including archive) ===\n")
    for root, dirs, files in os.walk(MEMORY_DIR):
        dirs.sort()
        for fname in sorted(files):
            if fname.endswith(".md"):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, "/opt/data")
                with open(fpath) as f:
                    print(f"--- {rel} ---")
                    print(f.read())

def main():
    now = datetime.now(tz=timezone.utc)
    month_start = now - timedelta(days=30)
    oldest = month_start.timestamp()
    latest = now.timestamp()
    month_label = now.strftime("%B %Y")

    print(f"=== SLACK MEMORY MONTHLY DEEP CLEAN ===")
    print(f"Month: {month_label}")
    print(f"Period: {month_start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}\n")

    channels = get_bot_channels()
    user_cache = {}
    activity_summary = {}  # channel_name -> {user_name -> message_count}

    for channel in channels:
        time.sleep(0.4)
        messages = get_channel_messages(channel["id"], oldest, latest)
        activity_summary[channel["name"]] = {}
        print(f"--- #{channel['name']}: {len(messages)} messages in 30 days ---")
        for msg in messages:
            uid = msg.get("user", "unknown")
            name = get_username(uid, user_cache)
            activity_summary[channel["name"]][name] = \
                activity_summary[channel["name"]].get(name, 0) + 1
        if activity_summary[channel["name"]]:
            for name, count in sorted(activity_summary[channel["name"]].items(),
                                       key=lambda x: -x[1]):
                print(f"  {name}: {count} messages")
        else:
            print("  (no activity)")
        print()

    print("\n=== 30-DAY ACTIVITY SUMMARY ===")
    print("Use this to validate whether facts in memory files are still supported by evidence.\n")
    all_active_users = set()
    for ch, users in activity_summary.items():
        for u in users:
            all_active_users.add(u)
    print(f"Active users this month: {', '.join(sorted(all_active_users))}")
    print(f"Inactive channels (0 messages): {', '.join(k for k, v in activity_summary.items() if not v)}")
    print()

    output_all_memory_files()

if __name__ == "__main__":
    main()
