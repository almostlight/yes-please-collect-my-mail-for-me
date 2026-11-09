#!/usr/bin/env bash
# Idempotent deploy for Linux: installs renew_consent.py plus the systemd
# user timer (every 48h10m). Run from a clone (./deploy.sh) or piped:
#   curl -sSL <raw-base>/deploy.sh | bash
set -euo pipefail

RAW_BASE="${DSNET_RAW_BASE:-https://raw.githubusercontent.com/almostlight/yes-please-collect-my-mail-for-me/main}"
INSTALL_DIR="${DSNET_INSTALL_DIR:-$HOME/.local/share/dsnet-consent}"

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
fi
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/renew_consent.py" ]]; then
    APP_DIR="$SCRIPT_DIR"
    CRED_HINT="$SCRIPT_DIR/setup_credentials.sh"
else
    APP_DIR="$INSTALL_DIR"
    CRED_HINT="curl -sSL $RAW_BASE/setup_credentials.sh | bash"
    for f in renew_consent.py systemd/dsnet-consent.service systemd/dsnet-consent.timer; do
        mkdir -p "$APP_DIR/$(dirname "$f")"
        curl -fsSL "$RAW_BASE/$f" -o "$APP_DIR/$f"
    done
fi

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/dsnet-consent"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/dsnet-consent"
install -d -m 700 "$CONFIG_DIR" "$STATE_DIR"

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"
    for unit in dsnet-consent.service dsnet-consent.timer; do
        sed "s|@REPO_DIR@|$APP_DIR|g" "$APP_DIR/systemd/$unit" > "$UNIT_DIR/$unit"
    done
    systemctl --user daemon-reload
    systemctl --user enable --now dsnet-consent.timer
    systemctl --user list-timers dsnet-consent.timer --no-pager || true
else
    echo "no systemd user session; use cron instead:" >&2
    echo "  */10 * * * * /usr/bin/python3 $APP_DIR/renew_consent.py --if-due" >&2
fi

if [[ ! -f "$CONFIG_DIR/credentials.env" ]]; then
    echo "credentials not configured yet: $CRED_HINT"
fi
echo "app:  $APP_DIR/renew_consent.py"
echo "logs: $STATE_DIR/renew_consent.log"
