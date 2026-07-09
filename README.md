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

Production deploys to a Debian server via SSH/rsync and systemd. See [docs/debian-server.md](docs/debian-server.md) for the full guide.

Quick start:

```sh
./scripts/deploy.sh          # LAN (192.168.1.135)
./scripts/deploy.sh --remote   # crearec.app
./scripts/service-debian.sh --remote status
```

Pushes to `main` trigger automatic deploy via GitHub Actions (same secrets as TelegramVideo: `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`).
