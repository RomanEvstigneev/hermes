# External Skill Library Evaluation

Use this reference when reviewing a third-party skill repository for possible Hermes integration.

## Evaluation checklist

1. Inventory the repository
   - Clone or inspect the repo at a specific commit.
   - Count tracked files and skill directories.
   - List every `SKILL.md` with category, line count, description, and support files.
   - Read the top-level README, license, plugin/manifest files, and any agent guidance files such as `AGENTS.md`, `CLAUDE.md`, or `CONTEXT.md`.

2. Classify each skill
   - Directly portable: broadly useful and not tied to another agent runtime.
   - Merge candidate: useful ideas overlap an existing Hermes skill and should patch that umbrella instead of creating a duplicate.
   - Optional/user-local: useful for some users but too narrow for bundled Hermes.
   - Do not import: personal, deprecated, ecosystem-specific, or runtime-specific.

3. Check compatibility
   - Frontmatter fields and unsupported flags.
   - Runtime assumptions such as Claude Code hooks, slash-command semantics, or `CLAUDE.md`-only behavior.
   - File-writing assumptions such as creating `CONTEXT.md`, `docs/adr/`, or issue-tracker config.
   - Tooling assumptions such as `gh`, `glab`, `npx`, package managers, or hardcoded local paths.
   - Whether workflows require interactive one-question-at-a-time sessions and are unsuitable for cron/background jobs.

4. Compare against Hermes umbrellas
   - Prefer patching existing class-level skills over adding duplicate narrow skills.
   - Look especially for overlap with `systematic-debugging`, `test-driven-development`, `writing-plans`, `github-issues`, `requesting-code-review`, `subagent-driven-development`, and `hermes-agent-skill-authoring`.
   - If a third-party skill is mostly a style or personality, consider whether it belongs as a response mode rather than a bundled skill.

5. Recommend an integration path
   - Do not recommend wholesale imports unless the library is already Hermes-native and non-overlapping.
   - Prefer: optional tap/source for original upstream skills, plus Hermes-native ports of the strongest general workflows.
   - Preserve license attribution when copying or adapting content.

## Report shape

Give the user:

- Repository summary: commit, license, size, intended agent runtime.
- What is inside by category.
- Compatibility caveats.
- Skill-by-skill recommendation: port, merge, optional, or skip.
- Prioritized integration plan.
- Clear final verdict: worth integrating wholesale, selectively, or not at all.

## Pattern from the Matt Pocock skills review

The `mattpocock/skills` repository was MIT licensed and valuable, but not suitable for wholesale import because it overlapped existing Hermes skills and contained Claude Code assumptions. The best recommendation was selective integration:

- Port strong unique workflows such as domain/ADR grilling, architecture review, and vertical-slice issue breakdown.
- Merge overlapping debugging/TDD/skill-authoring material into existing Hermes umbrellas.
- Keep narrow, personal, deprecated, or Claude-hook-specific skills out of bundled Hermes.
