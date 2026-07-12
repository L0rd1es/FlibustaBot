# Debian / Docker operations

Useful commands for the FlibustaBot container on the Debian server.

Deploy directory (default): `/home/crearec/crea-flibusta-bot`

Releases are deployed only by GitHub Actions on `master`. There is no local deploy helper script. You can also use Portainer for the same container.

## Container control

On the server:

```sh
cd /home/crearec/crea-flibusta-bot
docker compose ps
docker compose logs -f bot
docker compose logs --tail=100 bot
docker compose restart bot
docker compose stop
docker compose up -d
```

Pull a specific tag manually (normally Actions exports `IMAGE_TAG` for the deploy session):

```sh
cd /home/crearec/crea-flibusta-bot
# edit IMAGE_TAG in .env, then:
docker compose pull
docker compose up -d
```

## Config changes

Edit the bot token:

```sh
cd /home/crearec/crea-flibusta-bot
nano .env
docker compose restart bot
```

Whitelist and SQLite live under `data/`:

```sh
cd /home/crearec/crea-flibusta-bot
nano data/whitelist.json
# users.db is managed by the bot; restart only if needed after manual edits
docker compose restart bot
```

Other settings (mirrors, admin ID, rate limits) are in `config.py` and take effect after a new image deploy.

## Deploy / update

Merge to `master`. Actions builds, pushes to GHCR, and runs pull/up on the server.

## Troubleshooting

```sh
cd /home/crearec/crea-flibusta-bot
docker compose ps
docker compose logs --tail=100 bot
```

Cannot pull from GHCR:

```sh
docker login ghcr.io -u CreaRec
```

Missing `.env` causes the Actions deploy step to fail with an explicit error — bootstrap it once (see [docker.md](docker.md)).

Old systemd unit still running (two bots):

```sh
sudo systemctl disable --now telegram-flibusta
docker compose ps
```

Permission errors writing `data/`: ensure the host path is writable by UID 1000.

Bot fails to start with token error:

- Verify `TELEGRAM_BOT_TOKEN` is set in `/home/crearec/crea-flibusta-bot/.env`.
- Check file permissions: `chmod 600 .env`.
- `docker compose restart bot` and re-check logs.
