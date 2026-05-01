---
name: slack-communication
description: "Rules and conventions for communicating on Slack in Roman's Hermes environment"
version: 1.0.0
author: Roman Evstigneev + Hermes Agent
---

# Slack Communication

Rules for responding on Slack in this environment.

## Language

- **Always respond in English only.** Never use Russian or any other language, regardless of what language the user writes in.

**Rationale:** The Slack platform adapter has `PLATFORM_HINTS["slack"]` modified to force English-only responses in `/usr/local/lib/hermes-agent/agent/prompt_builder.py`. This custom mod will be overwritten on Hermes update, so the skill rule is the stable source of truth.

## Formatting Constraints

Slack's message formatting is limited. Avoid these markdown constructs:

- **No markdown tables** — Slack does not render them. They appear as raw text/ASCII.
- **No fenced code blocks with language tags** — Use simple `backtick` inline code or plain indented text blocks.
- **No complex nested lists** — Slack's list rendering is basic. Use flat bullet lists.

**Preferred alternatives:**
- Bullet lists (`• item` or `- item`)
- Numbered lists (`1. item`)
- Plaintext with clear line breaks
- Simple `inline code` with single backticks
- Simple code blocks with triple backticks but NO language identifier

## Threading

- Responses go in threads when the user replies in a thread.
- Do not break out of threads.

## Platform Quirks

- Markdown link syntax `[text](url)` works in Slack.
- Bold via `**text**` works.
- Italic via `*text*` or `_text_` works.
- Strikethrough via `~~text~~` works.
- Emoji reactions are not sent by the agent.