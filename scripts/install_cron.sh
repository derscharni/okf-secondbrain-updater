#!/usr/bin/env bash
# Install (or update) a crontab entry that runs okf_sync.py on a schedule.
# Idempotent: re-running replaces the previously installed entry instead of
# duplicating it, identified by the "# okf-secondbrain-updater" marker.
#
# Usage:
#   ./scripts/install_cron.sh
#   SCHEDULE="0 * * * *" ./scripts/install_cron.sh          # every hour
#   PYTHON_BIN=/usr/bin/python3.11 ./scripts/install_cron.sh
#   LOG_FILE=/var/log/okf-sync.log ./scripts/install_cron.sh
set -euo pipefail

SCHEDULE="${SCHEDULE:-*/30 * * * *}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${LOG_FILE:-$HOME/.okf-sync/cron.log}"
MARKER="# okf-secondbrain-updater"

mkdir -p "$(dirname "$LOG_FILE")"

CRON_LINE="${SCHEDULE} cd ${REPO_DIR} && ${PYTHON_BIN} okf_sync.py >> ${LOG_FILE} 2>&1 ${MARKER}"

( crontab -l 2>/dev/null | grep -vF "$MARKER" || true ; echo "$CRON_LINE" ) | crontab -

echo "Installed cron entry:"
echo "  $CRON_LINE"
echo "Logs: $LOG_FILE"
echo "Remove with: ./scripts/uninstall_cron.sh"
