# Debian Server Deployment

This guide installs FlibustaBot as a systemd process on Debian.

The scripted deployment uses `/home/crearec/FlibustaBot` as the app directory. Adjust paths if needed, then update the systemd unit and `.env` to match.

## 1. Install Python

Install Python 3.12 or newer and pip. On Debian:

```sh
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip
python3 --version
```

## 2. Configure Environment

Create the app directory and `.env` with your bot token:

```sh
mkdir -p /home/crearec/FlibustaBot
echo 'TELEGRAM_BOT_TOKEN=<your_token>' > /home/crearec/FlibustaBot/.env
chmod 600 /home/crearec/FlibustaBot/.env
```

Get a token from [@BotFather](https://t.me/BotFather) on Telegram.

Other settings (mirrors, admin ID, rate limits) live in `config.py` in the repository.

## 3. Manual Install (Optional)

If you prefer to set up the server without the deploy script:

```sh
cd /home/crearec/FlibustaBot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Install the systemd unit:

```sh
sed -e "s#__USER__#crearec#g" \
    -e "s#__APP_DIR__#/home/crearec/FlibustaBot#g" \
    deploy/telegram-flibusta.service | sudo tee /etc/systemd/system/telegram-flibusta.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-flibusta
sudo systemctl start telegram-flibusta
```

Check status and logs:

```sh
sudo systemctl status telegram-flibusta
sudo journalctl -u telegram-flibusta -f
```

The installed unit uses `Restart=always` and `RuntimeMaxSec=24h` to recycle the process once per day.

## 4. Updating The Service

```sh
cd /home/crearec/FlibustaBot
.venv/bin/pip install -r requirements.txt
sudo systemctl restart telegram-flibusta
```

After editing `.env`, restart the service so the bot reloads the token:

```sh
sudo systemctl restart telegram-flibusta
```

## Scripted Deployment

To deploy or update the app without cloning the repository on the server, run this from your local project root:

```sh
./scripts/deploy.sh
```

By default, the script connects to `192.168.1.135`, rsyncs the project to `/home/crearec/FlibustaBot`, installs dependencies in a venv on the server, installs the `telegram-flibusta` systemd unit, and restarts the service. It runs `pytest` locally first and aborts if tests fail.

Use `--remote` to connect via `crearec.app` instead of the local network IP:

```sh
./scripts/deploy.sh --remote
```

Override any of: `SERVER_HOST`, `SSH_USER`, `REMOTE_APP_DIR`, `SERVICE_NAME`.

```sh
SERVER_HOST=192.168.1.135 SSH_USER=crearec REMOTE_APP_DIR=/home/crearec/FlibustaBot ./scripts/deploy.sh
```

Set optional `DEPLOY_PASSWORD` in a local `.env` file (or export it) to skip SSH/sudo prompts during deploy; you need `sshpass` installed locally. When `DEPLOY_PASSWORD` is unset, deploy asks for passwords interactively.

The deploy script reuses one SSH connection and one `sudo` session on the server, so you should only be prompted for the server login password once and the sudo password once (if password auth is used). For zero prompts, use SSH keys and passwordless sudo for the deploy user, or `DEPLOY_PASSWORD` with `sshpass`.

The deploy script never overwrites `.env` on the server. If it is missing, the remote deploy script seeds it from `.env.example` so you can edit it on the server before the bot can start.

The deploy script also never overwrites `users.db` or `utils/whitelist.json` on the server (user data and access list persist across deploys).

**Server prerequisite:** Python 3.12+ with `python3-venv` must already be installed on the server (see section 1 above). The deploy script does not install Python for you.

## GitHub Actions CI/CD

Merging into `main` triggers an automatic deploy to the production server via [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml).

**On every push and pull request:** the `test` job runs `pip install` and `pytest`.

**On push to `main` only:** the `deploy` job runs after tests pass. GitHub Actions sets `CI=true` on the runner; `scripts/deploy.sh` forwards `CI`/`GITHUB_ACTIONS` to the remote script and skips forced TTY (`-tt`) when `DEPLOY_PASSWORD` is unset. The workflow then:

1. Writes the deploy SSH private key from GitHub Secrets
2. Opens an SSH ControlMaster socket authenticated with that key
3. Calls `./scripts/deploy.sh --remote`, which reuses the existing socket for rsync and remote install/restart

Required GitHub Secrets (Settings → Secrets and variables → Actions):

| Secret | Purpose |
|--------|---------|
| `DEPLOY_SSH_KEY` | Private deploy key (matching the public key in server `authorized_keys`) |
| `DEPLOY_HOST` | Server hostname, for example `crearec.app` |
| `DEPLOY_USER` | SSH user, for example `crearec` |

These are the same secrets used by the TelegramVideo project on the same server.

**Server prerequisites for CI deploy** (one-time setup):

- Public deploy key in `~/.ssh/authorized_keys` for the deploy user
- Passwordless sudo for deploy commands. **The sudoers username must match `DEPLOY_USER` in GitHub Secrets exactly** (for example `crearec`).

  If you already deployed TelegramVideo to this server, the sudoers rule in `/etc/sudoers.d/crearec-deploy` should already be in place. Otherwise, on the server as a user with sudo access:

  ```sh
  DEPLOY_USER=crearec   # must match GitHub secret DEPLOY_USER
  command -v cp systemctl journalctl

  sudo tee "/etc/sudoers.d/${DEPLOY_USER}-deploy" > /dev/null <<EOF
  ${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/cp, /usr/bin/cp, /bin/systemctl, /usr/bin/systemctl, /usr/bin/journalctl
  EOF
  sudo chmod 440 "/etc/sudoers.d/${DEPLOY_USER}-deploy"
  sudo visudo -c -f "/etc/sudoers.d/${DEPLOY_USER}-deploy"
  ```

  Then **as the deploy user** (not root), verify no password is asked:

  ```sh
  sudo -n systemctl --version
  sudo -n cp --version
  sudo -n systemctl status telegram-flibusta
  ```

- Python 3.12+ and `.env` with `TELEGRAM_BOT_TOKEN` already configured on the server

`DEPLOY_PASSWORD` is not used in CI. The workflow never overwrites `.env` on the server.

After a successful deploy, verify the service:

```sh
./scripts/service-debian.sh --remote status
./scripts/service-debian.sh --remote logs
```

## Service Helper Script

From your local project root, use `scripts/service-debian.sh` to manage the remote systemd service over SSH:

```sh
./scripts/service-debian.sh restart
./scripts/service-debian.sh start
./scripts/service-debian.sh status
./scripts/service-debian.sh logs
./scripts/service-debian.sh stop
./scripts/service-debian.sh --remote status
```

The script defaults to `SERVER_HOST=192.168.1.135`, `SSH_USER=crearec`, and `SERVICE_NAME=telegram-flibusta`. Override them when needed:

```sh
SERVER_HOST=192.168.1.135 SSH_USER=crearec ./scripts/service-debian.sh restart
```

Optional `DEPLOY_PASSWORD` in local `.env` (or env) works the same way as in `scripts/deploy.sh`.

For a quick operations reference, see `docs/debian-commands.md`.

## Notes

- Keep `.env` readable only by the service user (`chmod 600`).
- SQLite database (`users.db`), whitelist (`utils/whitelist.json`), and log files live in the app directory and are excluded from rsync during deploy.
- With `ProtectSystem=full`, the app directory must be listed in `ReadWritePaths` — the deploy script handles this automatically.
