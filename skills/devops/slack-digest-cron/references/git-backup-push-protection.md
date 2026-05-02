# Git backup push protection remediation

Use when a daily Git auto-commit or backup job created a local commit, but `git push` failed because GitHub push protection detected a Slack token or another secret.

## Known incident pattern

- Repository: `/opt/data`
- Symptom: daily backup says a commit was created but push failed.
- Git state: `main...origin/main [ahead 1]` or similar.
- GitHub rejects push with push protection because a Slack token pattern was found in the backup commit.
- Common source: `cron/output/<job_id>/<timestamp>.md` captured a prompt, session transcript, or tool output containing Slack credentials.

## Safe investigation rules

1. Do not print full secrets in the terminal or final answer.
2. Use masked scans only. Show file, line, token family, and masked prefix/suffix at most.
3. Inspect the blocked commit with `git diff-tree` and `git show HEAD:<path>` rather than pushing again.
4. Check both the blocked commit and current working tree, because there may be safe uncommitted changes created after the failed backup.
5. If the blocked commit never reached GitHub, credential rotation is risk-based rather than automatically urgent. Recommend rotation for production/high-scope tokens or if the token may have passed through Slack, LLM provider logs, session history, or other shared systems.

## Roman's backup preference

Roman wants cron output, runtime output, transcripts, logs, and accumulated operational history preserved in git where practical. Do not broadly exclude `cron/output/` from backups. Preserve history, but sanitize secrets before committing.

## Remediation workflow

From `/opt/data`:

```bash
git status --short --branch
git log --oneline -3
git diff-tree --no-commit-id --name-only -r HEAD
```

If HEAD is the blocked local backup commit and it has not reached GitHub:

```bash
git reset --soft origin/main
```

Remove only the specific unsafe output file or line that captured credentials. Example:

```bash
git rm -f cron/output/<job_id>/<timestamp>.md
```

or sanitize a file in place by replacing the secret value with `[REDACTED_SECRET]`.

Patch `/opt/data/scripts/daily_git_commit.py` so it scans candidate commit files before staging/committing and redacts known secret patterns such as Slack tokens (`xox...`, `xapp...`) to `[REDACTED_SECRET]`. The script may print a redaction summary, but must never print the raw secret.

Re-stage safe backup content, then recommit:

```bash
git add -A
git commit -m "chore: daily auto-commit YYYY-MM-DD"
```

Before pushing, run a masked secret scan against the new HEAD. Only then:

```bash
git push origin main
```

## Rotation and service recovery

For real production tokens, rotation remains best practice if the token appeared in Slack messages, LLM prompts, session transcripts, logs, or any other system beyond the local git object database.

If rotating:

- Rotate Slack app-level token (`xapp-...`) if exposed.
- Rotate Slack bot token (`xoxb-...`) if exposed or uncertain.
- Store new values only in the secrets location, normally `/opt/data/.env`.
- Restart Hermes gateway and verify Slack reconnects.

## Prevention checklist

- Keep `cron/output/` eligible for backup, but sanitize it before commit.
- Include a secret-handling rule in cron prompts: never include raw credentials, API keys, Slack token strings, authorization headers, or private key material in Slack messages or generated files; redact as `[REDACTED_SECRET]` if seen.
- Keep GitHub push protection enabled as the final safety net.
- Consider enabling Hermes secret redaction: `hermes config set security.redact_secrets true`, then restart Hermes/gateway.
- Log the incident in `/opt/data/logs/incident_log.md` with summary, root cause, actions, verification, and follow-up, but never include the full secret.
