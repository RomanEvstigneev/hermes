# Citation Link Patterns in SEO Articles

## Session Context

Roman asked whether SEObot-generated "Insights" articles should use scientific-style superscript source links instead of the regular contextual hyperlinks used in normal articles.

## Practical Conclusion

Superscript citation links are technically acceptable when implemented as real `<a href="...">` links, but they are usually not the best primary linking pattern for commercial SEO/blog content.

Recommended default: use contextual hyperlinks in the article body for the most important sources, plus an optional Sources/References section for transparency.

## Reasoning

- Google can crawl links that are normal anchor elements with `href` attributes.
- Google Search Central says good anchor text is descriptive, reasonably concise, and relevant to both the source page and target page.
- Numeric superscript links provide very weak anchor text because the visible anchor is only a number.
- Google helpful-content guidance emphasizes trust signals such as clear sourcing and evidence of expertise.
- Footnotes can support trust and keep generated text tidy, but overuse can make content look academic, AI-generated, or less consistent with a brand's normal article style.

## Recommended Hybrid Pattern

- Use normal contextual links for important claims and key sources, e.g. link text like "McKinsey's private markets report" rather than only `¹`.
- Keep a bottom "Sources" or "References" list when the article relies on many external facts.
- Avoid excessive outbound links; prioritize authoritative, directly relevant sources.
- Ensure links are crawlable `<a href>` elements and not JavaScript-only interactions.
- Match the site's main editorial style unless there is a deliberate reason to differentiate SEO landing content.

## Short Slack-Ready Answer Shape

- Verdict: not wrong, but not ideal as the default.
- Why it exists: credibility, clean body copy, AI-source transparency.
- SEO issue: weak anchor text and poorer mobile/readability UX.
- Recommendation: hybrid contextual links plus optional references.
- Bottom line: no urgent penalty risk, but standardize toward normal article style.

## Authoritative Basis to Recheck

- Google Search Central: SEO Link Best Practices — crawlable links and descriptive anchor text.
- Google Search Central: SEO Starter Guide — anchor text tells users and Google about linked pages.
- Google Search Central: Creating Helpful, Reliable, People-First Content — clear sourcing and evidence can support trust.