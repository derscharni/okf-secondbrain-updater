#!/usr/bin/env bash
# Remove the crontab entry installed by install_cron.sh.
set -euo pipefail

MARKER="# okf-secondbrain-updater"

if ! crontab -l 2>/dev/null | grep -qF "$MARKER"; then
  echo "No okf-secondbrain-updater cron entry found."
  exit 0
fi

REMAINING="$(crontab -l 2>/dev/null | grep -vF "$MARKER" || true)"
printf '%s\n' "$REMAINING" | crontab -
echo "Removed okf-secondbrain-updater cron entry."
