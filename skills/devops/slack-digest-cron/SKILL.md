---
name: slack-digest-cron
description: "Create a scheduled Slack channel digest using cron + data-collection script. Reads channel history via Slack API and has Hermes summarize it."
version: 1.0.0
tags: [slack, cron, digest, summary, notifications]
---

# Slack Daily Digest via Cron

Use when: user wants Hermes to periodically read Slack channel history and send a summary.

## Key Discovery: slack_sdk is only in the hermes-agent venv

System Python does NOT have slack_sdk. Must add to sys.path before importing:

```python
VENV_SITE_PACKAGES = "/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages"
if VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)
from slack_sdk import WebClient
```

## Key Discovery: cron scripts must load .env manually

Cron jobs run in a fresh session with no shell env. Load secrets explicitly:

```python
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
```

## Architecture: script= parameter injects data into cron prompt

The `script` parameter of `cronjob(action='create')` runs a Python script before
the cron prompt executes. Its stdout is injected as context. This is the right
pattern for "collect data, then have LLM process it":

```python
cronjob(action='create',
    name='Slack Daily Digest',
    schedule='0 8 * * *',            # 08:00 UTC daily — morning digest of previous day
    script='scripts/slack_daily_digest.py',  # relative to /opt/data/
    prompt='... analyze the data above and send summary to slack:CHANNEL_ID ...',
    deliver='local',  # bot sends to Slack itself via send_message tool
)
```

Place scripts at: `/opt/data/scripts/your_script.py`

## Slack API: finding channels the bot is a member of

```python
def get_bot_channels():
    channels = []
    cursor = None
    while True:
        resp = client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200,
            **({"cursor": cursor} if cursor else {})
        )
        for ch in resp.get("channels", []):
            if ch.get("is_member"):
                channels.append({"id": ch["id"], "name": ch.get("name")})
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return channels
```

## Slack API: reading channel history for a time range

```python
resp = client.conversations_history(
    channel=channel_id,
    oldest=str(day_start.timestamp()),
    latest=str(day_end.timestamp()),
    limit=200,
    inclusive=True,
)
```

Filter out noise (bot messages, join/leave events):
```python
skip_subtypes = {"bot_message", "channel_join", "channel_leave",
                 "bot_add", "bot_remove", "channel_purpose", "channel_topic"}
if msg.get("subtype") in skip_subtypes or msg.get("bot_id"):
    continue
```

## Resolving user IDs to display names

Slack messages contain `<@U12345>` — resolve to real names:

```python
user_cache = {}
def get_display_name(user_id):
    if user_id not in user_cache:
        resp = client.users_info(user=user_id)
        profile = resp["user"].get("profile", {})
        user_cache[user_id] = profile.get("display_name") or profile.get("real_name") or user_id
    return user_cache[user_id]

# In text:
import re
text = re.sub(r"<@([A-Z0-9]+)>", lambda m: f"@{get_display_name(m.group(1))}", text)
```

## Cron deliver='local' when the bot sends to Slack itself

Set `deliver='local'` so Hermes doesn't try to route the final response anywhere —
the prompt instructs Hermes to call `send_message(target='slack:CHANNEL_ID')` itself.

## Rate limiting

Add `time.sleep(0.3-0.5)` between API calls to avoid Slack rate limits (Tier 3: 50 req/min).

## Cron prompt: always specify output language explicitly

Cron jobs run without user context and will default to the user's profile language
(e.g. Russian for Russian-speaking users). If the digest should be in English,
say so explicitly at the top AND in the rules section of the prompt:

```
IMPORTANT: Respond ONLY in English. Never use any other language regardless
of what language the channel messages are written in.
```

Without this, the LLM will mirror the language of the Slack messages or the
user's memory profile — which may not be what's wanted for a team digest.

## Pitfalls

- `conversations.history` requires the bot to be a member — `not_in_channel` error otherwise
- Getting channels for yesterday: use UTC, not local time, unless user specifies timezone
- `reply_count` on a message shows thread depth but threads aren't fetched automatically
  (use `conversations.replies` if you need thread content too)
- 22:00 UTC ≠ 22:00 local time — confirm timezone with user before setting schedule
