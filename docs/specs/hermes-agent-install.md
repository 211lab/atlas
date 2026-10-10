# Install Hermes Agent on the hermes VM

Status: draft
Owner: —
Date: 2026-10-08

## Goal

Install Nous Research's [Hermes Agent](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
on the `hermes` VM (`10.0.10.1`, Ubuntu 22.04.5 on Minsky) using the official
POSIX source installer, so the `hermes` CLI is available on the host.

## User-visible behavior

- `~/.local/bin/hermes` exists and `hermes --version` (or `hermes doctor`) runs.
- The install is a source checkout under `~/.hermes/hermes-agent/` with user data
  in `~/.hermes/`.

## Non-goals

- Configuring an LLM provider or API key (`hermes setup` / `hermes model`).
- Messaging gateway, desktop app, or systemd service.
- Any change to the Atlas cluster or other hosts.

## Follow-up (completed)

- **Provider:** OpenRouter with the auto router — `model.provider: openrouter`,
  `model.default: openrouter/auto`, `OPENROUTER_API_KEY` set in `~/.hermes/.env`.
  Verified with a live one-shot prompt.
- **System libraries:** installed the Chromium X/GTK runtime deps and `libxi6`;
  `cua-driver` installed. `hermes doctor` now reports browser, browser-use,
  computer_use, vision, web search and web extract as available.
- **Service:** `hermes gateway install --start-now --start-on-login` created the
  user unit `hermes-gateway.service` (enabled, active) and enabled linger for
  `control`.
- **Telegram transport:** `TELEGRAM_BOT_TOKEN` (bot `@glitch_211bot`) and
  `TELEGRAM_ALLOWED_USERS=8265199040` set in `~/.hermes/.env`; gateway restarted
  and connected in polling mode. The approved user must send `/start` to the bot
  before it can reply (Telegram blocks bot-initiated chats).
- **Telegram reliability tuning:** pinned
  `platforms.telegram.extra.fallback_ips` to `149.154.166.110,149.154.167.220`
  (skips DoH discovery) and set `HERMES_TELEGRAM_HTTP_CONNECT_TIMEOUT=5` in
  `~/.hermes/.env` so transient connect failures are detected in ~5s instead of
  ~10s. The long-poll timeout is PTB's 10s default, so the connection is already
  active every ~10s.
- **Full admin / no approvals:** the agent runs as `control`, which has
  passwordless sudo, so it already administers the VM. Approval gates disabled:
  `approvals.mode: off`, `cron_mode/single_query_mode/unattended_mode: approve`,
  `subagents.subagent_auto_approve: true`, `mcp_reload_confirm` and
  `destructive_slash_confirm: false`, `security.protected_instruction_files:
  false`. Verified end-to-end: the agent ran `sudo whoami` → `root` with no
  approval prompt.

## Acceptance criteria

- Given the hermes VM, when the installer completes, then `~/.local/bin/hermes`
  exists and `hermes --version` prints a version.
- Given the install, then `~/.hermes/logs/install.log` shows no failed step.

## Constraints

- Install as the existing `control` user (passwordless sudo available for the
  `libatomic1` dependency).
- Run the official installer non-interactively (`--non-interactive`) since there
  is no TTY and no provider credentials.
- Standard install (browser/computer-use tools included, per the docs default).

## Assumptions

- ASSUMPTION: headless server; no desktop. Browser/computer-use tools may need
  extra system libraries to function, but the install itself completes.
- ASSUMPTION: provider configuration is a separate follow-up.
