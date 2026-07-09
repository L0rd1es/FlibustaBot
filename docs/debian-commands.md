# Debian App Management Commands

Useful commands for managing FlibustaBot on a Debian server.

The systemd service name is `telegram-flibusta`. The default app directory is `/home/crearec/FlibustaBot`.

## Local Helper Script

Run these from your local project root. The script connects to the Debian server over SSH and runs the matching systemd command.

```sh
./scripts/service-debian.sh restart
./scripts/service-debian.sh start
./scripts/service-debian.sh status
./scripts/service-debian.sh logs
./scripts/service-debian.sh stop
```

Override the default server, SSH user, or service name:

```sh
SERVER_HOST=192.168.1.135 SSH_USER=crearec ./scripts/service-debian.sh restart
SERVICE_NAME=telegram-flibusta ./scripts/service-debian.sh status
```

## Service Control

Run these directly on the Debian server.

```sh
sudo systemctl start telegram-flibusta
sudo systemctl stop telegram-flibusta
sudo systemctl restart telegram-flibusta
sudo systemctl status telegram-flibusta
```

Enable or disable start at boot:

```sh
sudo systemctl enable telegram-flibusta
sudo systemctl disable telegram-flibusta
```

Reload systemd after editing `/etc/systemd/system/telegram-flibusta.service`:

```sh
sudo systemctl daemon-reload
sudo systemctl restart telegram-flibusta
```

## Logs

Follow live logs:

```sh
sudo journalctl -u telegram-flibusta -f
```

Show recent logs:

```sh
sudo journalctl -u telegram-flibusta -n 100 --no-pager
```

Show logs since boot:

```sh
sudo journalctl -u telegram-flibusta -b --no-pager
```

## Config Changes

Edit the bot token:

```sh
cd /home/crearec/FlibustaBot
nano .env
```

Restart after changing `.env`:

```sh
sudo systemctl restart telegram-flibusta
```

Other settings (mirrors, admin ID, rate limits) are in `config.py` and take effect after redeploy or manual file update plus restart.

## Deploy Or Update

From your local project root:

```sh
./scripts/deploy.sh
./scripts/deploy.sh --remote
```

Override deploy defaults:

```sh
SSH_USER=crearec SERVER_HOST=192.168.1.135 REMOTE_APP_DIR=/home/crearec/FlibustaBot ./scripts/deploy.sh
```

## Troubleshooting

Check whether the service is active:

```sh
systemctl is-active telegram-flibusta
```

Check whether the service is enabled at boot:

```sh
systemctl is-enabled telegram-flibusta
```

Inspect the installed service file:

```sh
systemctl cat telegram-flibusta
```

Check the Python version:

```sh
python3 --version
/home/crearec/FlibustaBot/.venv/bin/python --version
```

Python should be 3.12 or newer.

Service fails with `Failed at step NAMESPACE` or `Failed to set up mount namespacing` (status `226`):

- Ensure the app directory exists and is writable by the service user.
- Check `ReadWritePaths` in the unit matches the app directory.
- Redeploy or update the unit, then `sudo systemctl daemon-reload` and restart.

Bot fails to start with token error:

- Verify `TELEGRAM_BOT_TOKEN` is set in `/home/crearec/FlibustaBot/.env`.
- Check file permissions: `chmod 600 .env`.
