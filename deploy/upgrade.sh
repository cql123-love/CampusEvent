#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT"
if [[ $(id -u) == 0 ]]; then
    echo "Run as ubuntu without sudo; sudo is requested only for the service."
    exit 1
fi
if [[ -n $(git status --porcelain --untracked-files=normal) ]]; then
    echo "Working tree has changes. Preserve them before upgrading."
    exit 1
fi
DB="$PROJECT/instance/campusevent.db"
if [[ ! -f $DB ]]; then
    echo "Production database not found: $DB"
    exit 1
fi
if [[ $(git rev-parse HEAD) != $(git rev-parse 'change-v2^{}') ]]; then
    echo "Checkout the verified change-v2 release before running this script."
    exit 1
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -v -p no:cacheprovider
.venv/bin/python tests/e2e_check.py
OLD_STATUS=$(sudo systemctl is-active campusevent || true)
if [[ $OLD_STATUS != active ]]; then
    echo "campusevent is not active; inspect the existing service first."
    exit 1
fi
sudo systemctl stop campusevent
trap 'echo "Upgrade stopped. Preserve instance/backups and inspect logs before restarting." >&2' ERR
umask 077
.venv/bin/python tools/upgrade_database.py "$DB"
sudo systemctl restart campusevent
for attempt in {1..20}; do
    if curl --fail --silent http://127.0.0.1/ | grep 'data-release="change-v2"' > /dev/null; then
        echo "LOCAL UPGRADE PASSED. Verify the public site, grade rules and mock emails."
        exit 0
    fi
    sleep 1
done
sudo journalctl -u campusevent -n 40 --no-pager
exit 1
