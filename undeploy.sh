#!/usr/bin/env bash
# Idempotent teardown for Linux: stops and removes the systemd user
# timer/service installed by deploy.sh. Credentials and state are kept.
# Pipe-safe: curl -sSL <raw-base>/undeploy.sh | bash
set -euo pipefail

UNIT_DIR="$HOME/.config/systemd/user"

systemctl --user stop dsnet-consent.service 2>/dev/null || true
systemctl --user disable --now dsnet-consent.timer 2>/dev/null || true
rm -f "$UNIT_DIR/dsnet-consent.service" "$UNIT_DIR/dsnet-consent.timer"
systemctl --user daemon-reload
systemctl --user reset-failed 2>/dev/null || true

echo "removed dsnet-consent timer/service"
echo "credentials/state kept in ~/.config/dsnet-consent and ~/.local/state/dsnet-consent"
