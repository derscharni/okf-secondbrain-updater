#!/usr/bin/env bash
# Remove the crontab entry installed by install_spec_check_cron.sh.
set -euo pipefail

MARKER="# okf-spec-check"

if ! crontab -l 2>/dev/null | grep -qF "$MARKER"; then
  echo "No okf-spec-check cron entry found."
  exit 0
fi

REMAINING="$(crontab -l 2>/dev/null | grep -vF "$MARKER" || true)"
printf '%s\n' "$REMAINING" | crontab -
echo "Removed okf-spec-check cron entry."
