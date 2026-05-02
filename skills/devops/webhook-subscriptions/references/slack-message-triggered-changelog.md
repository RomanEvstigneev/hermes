# Slack message-triggered changelog pattern

Use this pattern when a user wants an automation to run from messages in a Slack channel rather than from a timer or external HTTP webhook.

## Trigger shape

- Event source: Slack `message` event inside `gateway/platforms/slack.py`.
- Hook location: a narrow module in `gateway/builtin_hooks/`.
- Filtering: match the exact channel name or channel ID as early as possible.
- Rate limiting: check durable `last_triggered_at` before API calls or LLM work.
- Concurrency: use a lock file so simultaneous Slack events do not create duplicate runs.
- State path: use `get_hermes_home() / "state" / <automation>.json`.
- Logs path: use `get_hermes_home() / "logs" / <automation> / YYYY-MM-DD.log`.

## Bot messages and feedback loops

If the user asks to trigger on all messages, including bot messages, invoke the hook before normal Slack bot filtering. This creates a potential self-trigger when the hook posts back to the same channel. Mitigate it by making the rate-limit check the first meaningful operation after channel filtering. Do not rely only on ignoring Hermes's own messages if the requirement says bot messages should count.

## GitHub data collection for private repos

Prefer `gh api` when `gh` is installed and authenticated. If `gh` is unavailable, use GitHub REST directly with `GITHUB_TOKEN` or `GH_TOKEN` from the process environment or Hermes `.env`. Private repositories return 404 without a valid token, so treat 404 on a known private repo as an auth/access problem.

For a `main`-only production changelog:

- Current main SHA: `GET /repos/{owner}/{repo}/commits/main`.
- First run window: `GET /repos/{owner}/{repo}/commits?sha=main&since=<24h-ago>`.
- Subsequent window: `GET /repos/{owner}/{repo}/compare/{last_processed_sha}...main`.
- Associated PRs: `GET /repos/{owner}/{repo}/commits/{sha}/pulls` with GitHub JSON accept headers.

Update `last_processed_sha` only after the Slack send succeeds; otherwise the automation can lose a changelog if collection succeeds but delivery fails.

## Slack output guidance

For product changelogs, keep the message plain and Slack-friendly:

- No markdown tables.
- English-only if the workspace convention requires it.
- Sections such as `What changed` and `Summary`.
- In `What changed`, sort by business priority: new features first, critical fixes second, everything else last.
- Do not include a separate `Commit links` section unless the user explicitly asks for it.
- If no changes exist, send the exact no-change message the user requested rather than inventing a changelog.

## Priority-ordered `What changed` implementation

When generating a production changelog, do not rely on chronological commit order for the `What changed` section. Group first, then render in this order:

1. `New features` — user-facing capabilities and enabled workflows. Match terms such as `feat`, `feature`, `add`, `added`, `new`, `introduce`, `launch`, `implement`, `enable`, `support`.
2. `Critical fixes` — production fixes, hotfixes, bug/regression/security/crash repairs. Match terms such as `critical`, `urgent`, `blocker`, `hotfix`, `fix`, `fixed`, `bug`, `issue`, `error`, `crash`, `broken`, `regression`, `resolve`, `repair`, `security`.
3. `Other changes` — improvements, chores, refactors, docs, dependency updates, and internal maintenance.

Feature detection should run before fix detection so mixed titles like `feat: add validation fix` are still surfaced as a new capability. Add a unit test that constructs commits in non-priority order and asserts that the rendered message contains `New features` before `Critical fixes` before `Other changes`.

## Durable product feature memory log

For Axion Lab's #deploys-prod changelog automation, maintain a long-term English-only product memory log at:

```text
/opt/data/memory/product/axion-product-feature-log.md
```

Rules:
- Append to this log only after the Slack production changelog sends successfully.
- Record only `New features` / high-signal product capabilities and user-facing workflows.
- Do not record critical fixes, chores, dependency updates, routine maintenance, or raw commit links.
- Deduplicate by source SHA so retries do not create duplicate entries.
- Include release context such as commit count, PR count, and source SHA for traceability.
- Add tests that monkeypatch the memory-log path and verify feature-only logging plus deduplication.
