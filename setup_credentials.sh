#!/usr/bin/env bash
# Create the off-repo credentials file for renew_consent.py (Linux).
# Run from a clone (./setup_credentials.sh) or piped:
#   curl -sSL <raw-base>/setup_credentials.sh | bash
# Refuses to overwrite unless --force is passed. Reads from /dev/tty so it
# is safe when the script itself arrives on stdin.
set -euo pipefail

DEST="${DSNET_CREDENTIALS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dsnet-consent/credentials.env}"

if [[ -f "$DEST" && "${1:-}" != "--force" ]]; then
    echo "Refusing to overwrite existing $DEST (use --force to replace)." >&2
    exit 1
fi

mkdir -p "$(dirname "$DEST")"
chmod 700 "$(dirname "$DEST")"

read -r -p "DSNet panel e-mail: " email < /dev/tty
read -r -s -p "DSNet panel password: " password < /dev/tty
echo < /dev/tty
if [[ -z "$email" || -z "$password" ]]; then
    echo "Empty e-mail or password, aborting." >&2
    exit 1
fi

umask 077
cat > "$DEST" <<EOF
# Credentials for https://panel.dsnet.agh.edu.pl - keep this file OUT of any git repo.
# Permissions must stay 0600; renew_consent.py refuses group/world-readable files.
DSNET_EMAIL=$email
DSNET_PASSWORD=$password
EOF
chmod 600 "$DEST"

echo "Wrote $DEST (mode 0600)."
echo "Next: deploy the 48h10m schedule (./deploy.sh or curl -sSL <raw-base>/deploy.sh | bash)"
echo "Test manually:  python3 renew_consent.py --dry-run"
