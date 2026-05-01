---
name: hermes-docker-version-shadowing
description: "Diagnose and fix Docker Hermes deployments where an updated install exists but the live gateway/CLI still runs an older copy because PATH or entrypoint points elsewhere."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, docker, deployment, upgrade, gateway, path]
---

# Hermes Docker version shadowing

Use this when a Docker-hosted Hermes deployment appears updated in one shell, but the live gateway or terminal UI still runs an older copy because PATH or entrypoint points elsewhere.

Session reference: `references/roman-post-upgrade-audit-2026-05-01.md` captures a concrete post-upgrade audit where `/opt/hermes` v0.9 was dead for imports but still contained the active Playwright browser cache.

## Symptoms

- `hermes --version` from one context shows the desired/new version.
- The running gateway/CLI process still imports code from an older directory.
- Restarting the Hermes process does not help because the container entrypoint keeps invoking a shadowed `hermes` executable.

## Diagnosis

1. Compare all Hermes executables visible on PATH:

```bash
command -v hermes
which -a hermes
hermes --version
```

2. Identify the live gateway/CLI processes:

```bash
ps -eo pid,ppid,stat,etime,cmd | grep -E '[h]ermes|[t]tyd'
```

3. Check where live processes are running from:

```bash
pwdx <gateway_pid> <cli_pid>
```

4. Compare explicit launchers if multiple installs exist:

```bash
/usr/local/bin/hermes --version 2>&1 || true
/opt/hermes/.venv/bin/hermes --version 2>&1 || true
readlink -f /usr/local/bin/hermes /opt/hermes/.venv/bin/hermes 2>/dev/null || true
```

5. Inspect the entrypoint script rather than assuming the global executable is used. Common location in Roman's deployment:

```bash
sed -n '1,120p' /hermes.sh
```

Avoid dumping full process environments because they can contain secrets; only inspect targeted variables if necessary.

## Fix pattern

If the container entrypoint executes bare `hermes` and an older virtualenv appears earlier on PATH, change the entrypoint to use the intended absolute launcher and preserve the data directory. Check PID 1's environment too: `tr '\0' '\n' < /proc/1/environ | grep -E '^(PATH|HERMES_HOME|TERMINAL_CWD|PLAYWRIGHT_BROWSERS_PATH)='`. In Roman's Docker deployment, PID 1 may keep `/opt/hermes/.venv/bin` first in PATH, so bare `hermes` in `/hermes.sh` keeps launching `/opt/hermes` v0.9 even when `/usr/local/bin/hermes` is v0.11+.

Before deleting or quarantining a stale `/opt/hermes` tree, verify it is not still serving runtime assets. In Roman's container, the old v0.9 source tree was dead for Python imports, but PID 1 still had `PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright` and the browser cache under that directory was large and active. Migrate/reinstall Playwright browsers or update the environment first, then restart the container, then quarantine `/opt/hermes` before permanent deletion.

Recommended entrypoint pattern:

```bash
export HERMES_HOME=/opt/data
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset TERMINAL_CWD
HERMES_BIN=/usr/local/bin/hermes
HERMES_PROJECT=/usr/local/lib/hermes-agent
cd "$HERMES_PROJECT" || exit 1
"$HERMES_BIN" gateway run &
"$HERMES_BIN"
```

The `cd` is important even when `HERMES_BIN` is absolute: Python console scripts keep the current directory (`''`) first on `sys.path`, so launching `/usr/local/bin/hermes` while cwd is `/opt/hermes` can still import old `/opt/hermes/*.py` modules. `unset TERMINAL_CWD` prevents inherited terminal-tool defaults from pushing new sessions back to the stale tree.

Then restart the container from the Docker host:

```bash
docker restart <container_id_or_name>
```

If Docker is unavailable inside the container, do not assume the agent can perform the final restart. Complete code/config changes, verify them with explicit `/usr/local/bin/hermes ...` commands, and clearly tell the user that the live PID 1/gateway/CLI will remain on the old runtime until the container is restarted from the host or the user approves stopping/restarting the gateway process.

## Upgrade workflow notes

When upgrading the newer source tree while preserving local patches:

1. Create backups before touching runtime files. If backing up `/opt/data` into a subdirectory of `/opt/data`, stage the archive in `/tmp` and move it afterward, or exclude `opt/data/backups`; otherwise `tar` can fail with `file changed as we read it`.

```bash
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP_DIR=/opt/data/backups/hermes-upgrade-$TS
TMPDIR=/tmp/hermes-upgrade-$TS
mkdir -p "$BACKUP_DIR" "$TMPDIR"
tar --exclude='opt/data/backups' -czf "$TMPDIR/opt-data.tar.gz" -C / opt/data
mv "$TMPDIR/opt-data.tar.gz" "$BACKUP_DIR/opt-data.tar.gz"
cp /hermes.sh "$BACKUP_DIR/hermes.sh.bak"
git -C /usr/local/lib/hermes-agent diff > "$BACKUP_DIR/hermes-agent-local.patch"
git -C /usr/local/lib/hermes-agent status --short > "$BACKUP_DIR/hermes-agent-local-status.txt"
```

2. Prefer a controlled git update when local changes exist:

```bash
cd /usr/local/lib/hermes-agent
git fetch --tags origin --prune
git stash push -u -m "pre-upgrade local Hermes patches $TS"
git pull --ff-only origin main
```

3. Reapply the stash and resolve conflicts. If `ui-tui/package-lock.json` conflicts and the local change was incidental, prefer the upstream lockfile (`git checkout --ours ui-tui/package-lock.json` during stash-apply conflicts after pulling) and keep functional source patches instead.

4. Do not treat `./venv/bin/python -m pip install -e .` failure as fatal if the venv lacks `pip`; verify the console entry point directly. In Roman's deployment, the updated `/usr/local/bin/hermes` reflected the new source version even though `python -m pip` was unavailable in the venv.

5. Commit preserved deployment customizations in the source tree after resolving conflicts so the tree is not left with fragile uncommitted changes.

6. Run config migration and verification using the explicit launcher:

```bash
HERMES_HOME=/opt/data /usr/local/bin/hermes config migrate
HERMES_HOME=/opt/data /usr/local/bin/hermes config check
HERMES_HOME=/opt/data /usr/local/bin/hermes doctor
```

Preserve Roman-specific settings such as `cron.wrap_response: false` after migration.

## Verification

After restart, verify:

```bash
/usr/local/bin/hermes --version
hermes status --all
HERMES_HOME=/opt/data /usr/local/bin/hermes gateway status 2>&1 || true
cat /opt/data/gateway_state.json 2>/dev/null || true
ps -eo pid,ppid,stat,etime,cmd | grep -E '[h]ermes|[t]tyd' || true
```

Confirm that:

- The desired version is shown.
- `Project:` points to the intended source tree.
- Gateway state is `running`; Slack (if configured) is `connected`.
- `ps` does not show active gateway/CLI processes from `/opt/hermes`; zombie `[hermes] <defunct>` entries may persist until container restart, but they should not hold gateway locks.
- Messaging platforms such as Slack remain configured.

If gateway startup fails with `Slack app token already in use (PID <pid>)` and that PID is `[hermes] <defunct>`, clear scoped gateway locks using the modern runtime before restarting the gateway. Remove stale temp PID files such as `/tmp/hermes_gateway_started.pid` if they point at dead processes.

If `hermes doctor` reports an outdated config version after switching launchers, run:

```bash
/usr/local/bin/hermes config migrate
# or
/usr/local/bin/hermes doctor --fix
```

## Rollback

Before editing the entrypoint, save a backup:

```bash
cp /hermes.sh /hermes.sh.bak.$(date +%Y%m%d-%H%M%S)
```

Rollback by restoring the backup and restarting the container.
