---
name: seo-content-review
description: "Review SEO-oriented articles and content patterns for search, trust, readability, and brand consistency."
version: 1.0.0
author: Hermes Agent
---

# SEO Content Review

Use this skill when reviewing blog posts, AI-generated articles, content templates, citation/link patterns, or SEO copy conventions.

## Goals

- Give short, executive-ready guidance rather than a long SEO lecture.
- Separate what is technically acceptable for crawling from what is best for SEO, UX, and brand consistency.
- Prefer practical recommendations that can be implemented in the content template or editorial workflow.
- Ground claims in authoritative sources when possible, especially Google Search Central.

## Workflow

1. Identify the content pattern under review:
   - Link style, anchor text, citations, headings, schema, internal links, outbound links, author metadata, or article structure.
2. Check whether the implementation is technically crawlable:
   - Normal `<a href="...">` links are generally crawlable.
   - JavaScript-only, click-handler-only, or non-anchor pseudo-links are risky.
3. Assess SEO quality:
   - Anchor text should be descriptive, concise, and relevant.
   - Internal links should support topical clusters and conversion paths.
   - External links should support trust and sourcing without distracting users.
4. Assess user experience and brand fit:
   - Is the pattern readable on mobile?
   - Does it look natural for commercial/blog content?
   - Does it create an AI-generated or overly academic feel?
5. Recommend a default standard:
   - Preserve useful trust signals.
   - Prefer contextual links for important references.
   - Use references/footnotes only when they improve clarity.

## Citation and Source-Link Pattern Reviews

For scientific-style superscript citations in SEO articles, see `references/citation-link-patterns.md`.

Default guidance:
- Superscript citation links are not inherently bad for SEO if they are real crawlable links.
- They are usually weaker than contextual hyperlinks because the anchor text is only a number and gives little semantic context.
- A strong hybrid pattern is usually best: contextual links in the body for key sources plus an optional References/Sources section for transparency.

## Slack Executive Summary Format

When responding in Slack:
- Keep it short and decision-oriented.
- Use bullets, not tables.
- Include: verdict, why it exists, SEO/UX downside, recommendation, and bottom line.
- Avoid over-citing unless the user asks for links; mention the authoritative basis briefly.

## Pitfalls

- Do not claim a pattern is an SEO ranking penalty unless there is strong evidence.
- Do not optimize only for crawlers; include readability, trust, and brand consistency.
- Do not recommend removing citations entirely when transparency is beneficial.
- Do not use vague anchor text such as "click here", "read more", or numeric-only links as the primary source-linking pattern when contextual anchor text is possible.

## Verification

Before finalizing:
- Confirm whether links are actual `<a href>` links if implementation access is available.
- Confirm the recommendation distinguishes crawlability from SEO quality.
- Confirm the output is concise enough for an executive reader if sent in Slack.