# Post-session knowledge update reports

Use when Roman wants Slack notifications after Hermes finishes a Slack conversation with someone else, summarizing what knowledge changed.

## Desired behavior

After Hermes interacts with a non-Roman Slack user, wait for an inactivity window (usually 5-10 minutes). If the session caused memory, skill, cron, script, or other knowledge-file changes, send Roman a concise executive summary in Slack.

Example summary shape:

```text
:brain: *Post-session knowledge update — Sergei Maslennikov*

I spoke with Sergei in #bizdev and updated knowledge from that conversation.

*What changed:*
• People memory — added/confirmed 2 facts about Sergei's current responsibilities.
• Channel memory — updated #bizdev context with the latest pipeline discussion.
• Skills/procedures — no changes.

*Files changed:*
• /opt/data/memory/people/sergei-maslennikov.md
• /opt/data/memory/channels/bizdev.md

No sensitive credentials were included.
```

## Preferred MVP implementation

Prefer a periodic cron watcher over a gateway hook for the first implementation.

Why:
- Survives gateway restarts better.
- Avoids deep gateway code changes.
- Easier to version-control and audit.
- Good enough timing: "within one cron tick after 5-10 minutes of inactivity".

Suggested schedule:

```text
*/5 * * * *
```

## Watcher responsibilities

1. Read recent Slack-origin Hermes sessions from the session store/transcripts.
2. Ignore Roman's own sessions unless explicitly configured otherwise.
3. Treat a session/thread as complete after 5-10 minutes without new messages.
4. Compare knowledge files changed since the session started or since the previous watcher checkpoint.
5. Summarize only meaningful knowledge changes; do not send if nothing changed.
6. Send to Roman's home Slack target, normally `slack:C0B18TP48JD`.
7. Store a checkpoint so each session is reported at most once.

## Knowledge paths to track

Start with:

```text
/opt/data/memories/
/opt/data/memory/
/opt/data/skills/
/opt/data/cron/jobs.json
```

Optionally include automation code when relevant:

```text
/opt/data/scripts/
/opt/data/gateway/builtin_hooks/
```

## Safety and privacy rules

- Do not include raw Slack transcripts.
- Do not include raw private user messages unless Roman explicitly asks for detail.
- Do not include secrets, tokens, authorization headers, or private keys; redact as `[REDACTED_SECRET]`.
- Slack summaries must be in English only.
- Use bullets, not markdown tables.
- If the changed file diff contains sensitive material, summarize the category of change without quoting it.

## Implementation notes

The watcher can use git state or filesystem mtimes. Git-based diff is usually easier because `/opt/data` is version-controlled:

- Keep a checkpoint file such as `/opt/data/state/post_session_knowledge_reports.json`.
- Record processed `session_id`, last observed commit/hash, and last processed file mtimes.
- For uncommitted changes, inspect `git status --porcelain` and `git diff -- <paths>`.
- For committed changes, inspect `git diff <previous_hash>..HEAD -- <paths>`.

If using Hermes cron, configure delivery directly:

```text
deliver='slack:C0B18TP48JD'
```

The cron prompt should say: do not call `send_message`; return a Slack-ready executive summary as final response, and let cron delivery post it.
