# Docker + GHCR deployment

The bot runs as a Docker container pulled from GitHub Container Registry (GHCR). Releases happen only through GitHub Actions when changes land on `master`. There is no local deploy script.

Image: `ghcr.io/crearec/crea-flibusta-bot`

Deploy directory: `/home/crearec/crea-flibusta-bot`

## How a release works

1. Merge or push to `master`.
2. Actions runs tests and builds the image.
3. Actions pushes tags `master` and `sha-<short>` to GHCR.
4. Actions copies `docker-compose.yml` to the server, exports `IMAGE_TAG` in the SSH session (overrides `.env` for Compose interpolation), then runs `docker compose pull && docker compose up -d`.

App secrets stay on the server in `.env`. SQLite DB, whitelist, and logs live in `./data`. CI never mutates `.env`.

## One-time server bootstrap

Use the same Linux user that already runs Docker/Portainer (`crearec`). Do not create a separate service user.

### 1. GitHub / GHCR

After the first successful `publish` job:

1. Open the `crea-flibusta-bot` package under your GitHub user/org.
2. Link it to the `FlibustaBot` repository if needed.
3. Keep the package **Private**.
4. Ensure the server can pull private GHCR images (same `docker login ghcr.io` used for other bots is fine).

### 2. Docker login on the server

```sh
echo "$GHCR_TOKEN" | docker login ghcr.io -u CreaRec --password-stdin
docker compose version
```

### 3. Deploy directory

```sh
mkdir -p /home/crearec/crea-flibusta-bot/data
cd /home/crearec/crea-flibusta-bot
```

Copy `docker-compose.yml` from the repo once (Actions will refresh it on later deploys).

Create `.env` from [`.env.example`](../.env.example):

```sh
TELEGRAM_BOT_TOKEN=<token from @BotFather>
IMAGE=ghcr.io/crearec/crea-flibusta-bot
IMAGE_TAG=master
```

```sh
chmod 600 .env
```

### 4. Migrate data from the old systemd install

If the bot previously ran under `/home/crearec/FlibustaBot`:

```sh
# From the old checkout into the new data volume
cp /home/crearec/FlibustaBot/users.db /home/crearec/crea-flibusta-bot/data/
cp /home/crearec/FlibustaBot/utils/whitelist.json /home/crearec/crea-flibusta-bot/data/
# Optional: copy logs if you want them
# cp /home/crearec/FlibustaBot/bot.log /home/crearec/crea-flibusta-bot/data/
```

Ensure `data/` is writable by the container user (UID 1000):

```sh
sudo chown -R 1000:1000 /home/crearec/crea-flibusta-bot/data
```

### 5. Stop the old systemd unit

```sh
sudo systemctl disable --now telegram-flibusta
```

Later deploys also attempt this if the unit still exists.

### 6. First start

Either:

```sh
cd /home/crearec/crea-flibusta-bot
docker compose pull
docker compose up -d
```

Or merge to `master` and let Actions deploy.

Check Portainer, `docker compose logs -f bot`, and send `/start` in Telegram.

After the container is stable, you can remove the old full source checkout (`/home/crearec/FlibustaBot`) and keep only this thin deploy directory.

## Day-to-day operations

Deploy: merge to `master`.

On the server (or via Portainer):

```sh
cd /home/crearec/crea-flibusta-bot
docker compose ps
docker compose logs -f bot
docker compose restart bot
```

After editing `.env` (for example the bot token), restart so the process reloads env:

```sh
docker compose restart bot
```

## GitHub Actions secrets

| Secret | Purpose |
|--------|---------|
| `GHCR_USERNAME` | GHCR owner username (`CreaRec` / `crearec`) |
| `GHCR_TOKEN` | PAT from that account with `write:packages` (and `read:packages`) |
| `DEPLOY_SSH_KEY` | Private key for SSH deploy |
| `DEPLOY_HOST` | Tailscale IP or MagicDNS hostname of the server (for example `100.118.169.52`) |
| `DEPLOY_USER` | SSH user (for example `crearec`) |
| `TS_OAUTH_CLIENT_ID` | Tailscale OAuth client ID (Trust credentials) for ephemeral CI nodes |
| `TS_OAUTH_SECRET` | Tailscale OAuth client secret (Trust credentials) |

Deploy joins the tailnet with `tag:ci` via [`tailscale/github-action`](https://github.com/tailscale/github-action), then SSHs to `DEPLOY_HOST`. Create the OAuth client under Tailscale **Settings → Trust credentials** (not legacy OAuth clients).

Publish logs into GHCR as `crearec` (repo is under `L0rd1es`, so `GITHUB_TOKEN` cannot push that package namespace).

The deploy user needs Docker Compose without sudo, and passwordless sudo for `systemctl` only while the systemd unit is being retired.

The deploy user needs Docker Compose without sudo, and passwordless sudo for `systemctl` only while the systemd unit is being retired.
