#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Deployment stopped at line $LINENO. Share the error above, not secrets." >&2' ERR

if [[ $(id -u) == 0 ]]; then
    echo "Run this script as ubuntu, without sudo; it requests sudo when needed."
    exit 1
fi

PUBLIC_IP=${1:?Usage: bash deploy/ubuntu.sh PUBLIC_IPV4}
if [[ ! $PUBLIC_IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Expected a public IPv4 address."
    exit 1
fi
PROJECT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
APP_USER=$(id -un)
APP_GROUP=$(id -gn)
if [[ $PROJECT == *" "* ]]; then
    echo "Clone the repository into a path without spaces."
    exit 1
fi
cd "$PROJECT"

echo "[1/5] Installing Ubuntu packages"
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-venv python3-pip nginx curl

echo "[2/5] Installing dependencies and running tests"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -v
.venv/bin/python tests/e2e_check.py

echo "[3/5] Preparing persistent storage"
mkdir -p instance
chmod 700 instance
if [[ ! -f instance/production.env ]]; then
    (umask 077; .venv/bin/python -c \
        'import secrets; print("CAMPUSEVENT_SECRET=" + secrets.token_hex(32))' \
        > instance/production.env)
fi

echo "[4/5] Configuring the background service and Nginx"
sudo tee /etc/systemd/system/campusevent.service > /dev/null <<EOF
[Unit]
Description=CampusEvent Flask application
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$PROJECT
EnvironmentFile=$PROJECT/instance/production.env
Environment=CAMPUSEVENT_DB=$PROJECT/instance/campusevent.db
Environment=CAMPUSEVENT_SEED=1
Environment=TZ=Asia/Shanghai
Environment=PYTHONUNBUFFERED=1
ExecStart=$PROJECT/.venv/bin/gunicorn --workers 1 --threads 1 --bind 127.0.0.1:8000 --access-logfile - --error-logfile - app:app
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/nginx/sites-available/campusevent > /dev/null <<EOF
server {
    listen 80;
    server_name $PUBLIC_IP localhost 127.0.0.1;
    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF
sudo ln -sfn /etc/nginx/sites-available/campusevent \
    /etc/nginx/sites-enabled/campusevent
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable campusevent nginx
sudo systemctl restart campusevent
sudo systemctl restart nginx
if command -v ufw > /dev/null && sudo ufw status | grep -q '^Status: active'; then
    sudo ufw allow 80/tcp
fi

echo "[5/5] Checking local HTTP"
for attempt in {1..20}; do
    if curl --fail --silent http://127.0.0.1/ | grep -q CampusEvent; then
        echo "LOCAL CHECK PASSED"
        echo "Next: allow TCP 80 in the Tencent Cloud security group."
        echo "Then independently verify http://$PUBLIC_IP/ from outside the server."
        echo "Persistent database: $PROJECT/instance/campusevent.db"
        exit 0
    fi
    sleep 1
done
sudo journalctl -u campusevent -n 40 --no-pager
exit 1
