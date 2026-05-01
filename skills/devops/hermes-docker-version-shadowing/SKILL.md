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

Use this when a Docker-hosted Hermes deployment appears updated in one shell, but the live gateway or terminal UI still behaves like an older version.

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

If the container entrypoint executes bare `hermes` and an older virtualenv appears earlier on PATH, change the entrypoint to use the intended absolute launcher and preserve the data directory:

```bash
export HERMES_HOME=/opt/data
/usr/local/bin/hermes gateway run &
/usr/local/bin/hermes
```

Then restart the container from the Docker host:

```bash
docker restart <container_id_or_name>
```

## Verification

After restart, verify:

```bash
/usr/local/bin/hermes --version
hermes status --all
```

Confirm that:

- The desired version is shown.
- `Project:` points to the intended source tree.
- `Gateway Service` is running.
- Messaging platforms such as Slack remain configured.

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
