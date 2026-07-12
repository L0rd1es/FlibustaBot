# Debian Server Deployment

Production runs the bot in Docker on Debian. Releases are published to GHCR and pulled by GitHub Actions. See [docker.md](docker.md) for the full guide and one-time bootstrap.

This page is a short server-oriented summary. Local deploy scripts are not used.

## Layout

Default deploy directory: `/home/crearec/crea-flibusta-bot`

| Path | Role |
|------|------|
| `docker-compose.yml` | Synced from git by Actions |
| `.env` | `TELEGRAM_BOT_TOKEN`, `IMAGE`, `IMAGE_TAG` (never overwritten by Actions) |
| `data/` | SQLite DB, whitelist, logs (UID 1000) |

Host user: `crearec` (same user as other Docker/Portainer stacks). No separate service user.

## Prerequisites

- Docker Engine + Compose plugin (already required for Portainer stacks)
- `crearec` can run `docker compose` without sudo
- `docker login ghcr.io` with a PAT that has `read:packages` (private image)
- Passwordless sudo for `systemctl` only if the old systemd unit must still be disabled during migration

Python is **not** required on the server for runtime.

## Migrate from systemd

1. Complete the bootstrap in [docker.md](docker.md) (`.env`, migrate `users.db` / `whitelist.json` into `data/`, GHCR login).
2. `sudo systemctl disable --now telegram-flibusta`
3. Start the container (`docker compose up -d` or wait for Actions)
4. Confirm `/start` works in Telegram and whitelist/DB still apply
5. Remove the old full app checkout (`/home/crearec/FlibustaBot`) if it is no longer needed

## GitHub Actions

Push/merge to `main` runs:

1. `test` — `pytest` and a non-pushing Docker build
2. `publish` — push `ghcr.io/crearec/crea-flibusta-bot:main` and `:sha-<short>`
3. `deploy` — SCP `docker-compose.yml`, export `IMAGE_TAG`, `docker compose pull && up -d`

Required secrets: `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`.

Actions never overwrites `.env` or files under `data/`.

## Notes

- Keep `.env` readable only by the deploy user (`chmod 600`).
- Persistent state is only under `./data` (`users.db`, `whitelist.json`, logs).
- Other settings (mirrors, admin ID, rate limits) live in `config.py` and ship inside the image.
