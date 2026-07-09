#!/usr/bin/env bash
# Remote deploy steps (run on the server via scripts/deploy.sh).
# Expects: REMOTE_APP_DIR, SERVICE_NAME, DEPLOY_USER.

set -euo pipefail

: "${REMOTE_APP_DIR:?REMOTE_APP_DIR is required}"
: "${SERVICE_NAME:?SERVICE_NAME is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"

cd "$REMOTE_APP_DIR"

ENV_PATH="${REMOTE_APP_DIR}/.env"
ENV_EXAMPLE="${REMOTE_APP_DIR}/.env.example"

# Probe passwordless sudo with commands allowed by crearec-deploy sudoers.
sudo_probe() {
  sudo -n systemctl --version >/dev/null 2>&1 || \
    sudo -n cp --version >/dev/null 2>&1
}

is_interactive_deploy() {
  [ -t 0 ] && [ -t 1 ] && \
    [ "${CI:-}" != true ] && [ "${GITHUB_ACTIONS:-}" != true ]
}

# Reuse one sudo authentication for systemd steps (avoids repeated password prompts).
start_sudo_keepalive() {
  while true; do
    sudo_probe || exit
    sleep 50
    kill -0 "$$" || exit
  done 2>/dev/null &
  SUDO_KEEPALIVE_PID=$!
  trap 'kill "$SUDO_KEEPALIVE_PID" 2>/dev/null' EXIT
}

if ! sudo_probe; then
  if [ -n "${DEPLOY_PASSWORD:-}" ]; then
    printf '%s\n' "$DEPLOY_PASSWORD" | sudo -S -v
    start_sudo_keepalive
  elif is_interactive_deploy; then
    echo "[remote] sudo required for systemd setup (enter password once)..."
    sudo -v
    start_sudo_keepalive
  else
    echo "[remote] ERROR: passwordless sudo is required for non-interactive deploy (CI)." >&2
    echo "[remote] Running as: $(whoami) (expected deploy user: ${DEPLOY_USER})" >&2
    echo "[remote] sudo -n systemctl --version:" >&2
    sudo -n systemctl --version 2>&1 >&2 || true
    echo "[remote] sudo -n cp --version:" >&2
    sudo -n cp --version 2>&1 >&2 || true
    echo "[remote] Fix: create /etc/sudoers.d/${DEPLOY_USER}-deploy with NOPASSWD for cp, systemctl, journalctl." >&2
    echo "[remote] The username in sudoers must match DEPLOY_USER exactly. See docs/debian-server.md" >&2
    exit 1
  fi
fi

ENV_SEEDED=false
if [ ! -f "$ENV_PATH" ]; then
  echo "[remote] WARN: ${ENV_PATH} is missing."
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_PATH"
    chmod 600 "$ENV_PATH"
    ENV_SEEDED=true
    echo "[remote] Created ${ENV_PATH} from .env.example."
    echo "[remote] Edit it on the server and set TELEGRAM_BOT_TOKEN before expecting the bot to work."
  else
    echo "[remote] ERROR: ${ENV_EXAMPLE} is also missing."
    exit 1
  fi
fi

if [ "$ENV_SEEDED" = true ]; then
  echo "[remote] WARN: seeded .env has no bot token — the service will fail until you edit ${ENV_PATH}."
fi

echo "[remote] creating virtualenv if needed..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

echo "[remote] installing dependencies..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q --upgrade -r requirements.txt

echo "[remote] installing systemd unit ${SERVICE_NAME}..."
TMP_UNIT="$(mktemp)"
sed -e "s#__USER__#${DEPLOY_USER}#g" \
    -e "s#__APP_DIR__#${REMOTE_APP_DIR}#g" \
    deploy/flibusta-bot.service > "$TMP_UNIT"
sudo cp "$TMP_UNIT" "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "$TMP_UNIT"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[remote] waiting for service to start..."
sleep 3

if ! sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
  echo "[remote] ERROR: ${SERVICE_NAME} is not active after restart." >&2
  sudo systemctl --no-pager --full status "${SERVICE_NAME}" || true
  sudo journalctl -u "${SERVICE_NAME}" -n 40 --no-pager || true
  exit 1
fi

echo "[remote] service status:"
sudo systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo "[remote] startup logs:"
sudo journalctl -u "${SERVICE_NAME}" -n 20 --no-pager || true
