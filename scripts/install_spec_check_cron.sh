#!/usr/bin/env bash
# Install (or update) a crontab entry that runs check_okf_spec.py weekly.
# Idempotent: re-running replaces the previously installed entry instead of
# duplicating it, identified by the "# okf-spec-check" marker. Separate
# marker from install_cron.sh's "# okf-secondbrain-updater" so the two
# entries never clobber each other.
#
# Usage:
#   ./scripts/install_spec_check_cron.sh
#   SCHEDULE="0 9 * * MON" ./scripts/install_spec_check_cron.sh   # default: Monday 09:00
#   PYTHON_BIN=/usr/bin/python3.11 ./scripts/install_spec_check_cron.sh
set -euo pipefail

SCHEDULE="${SCHEDULE:-0 9 * * MON}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${LOG_FILE:-$HOME/.okf-sync/spec-check.log}"
MARKER="# okf-spec-check"

mkdir -p "$(dirname "$LOG_FILE")"

CRON_LINE="${SCHEDULE} cd ${REPO_DIR} && ${PYTHON_BIN} check_okf_spec.py >> ${LOG_FILE} 2>&1 ${MARKER}"

( crontab -l 2>/dev/null | grep -vF "$MARKER" || true ; echo "$CRON_LINE" ) | crontab -

echo "Installed cron entry:"
echo "  $CRON_LINE"
echo "Logs: $LOG_FILE"
echo "Remove with: ./scripts/uninstall_spec_check_cron.sh"
