# FlibustaBot

Telegram bot for searching and downloading books from Flibusta mirrors.

## Local Development

1. Create a virtualenv and install dependencies:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set your bot token:

   ```sh
   cp .env.example .env
   # Edit .env: TELEGRAM_BOT_TOKEN=<token from @BotFather>
   ```

3. Run the bot:

   ```sh
   python main.py
   ```

## Tests

```sh
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Deployment

Production runs in Docker on Debian. Releases go through GitHub Actions → GHCR → `docker compose pull/up`. See [docs/docker.md](docs/docker.md) for bootstrap and [docs/debian-commands.md](docs/debian-commands.md) for day-to-day ops.

Deploy: merge or push to `master`. Required secrets: `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER` (same as the other bots on this host).
