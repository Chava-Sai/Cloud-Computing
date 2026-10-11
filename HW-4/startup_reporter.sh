#!/usr/bin/env bash
# Compute Engine runs this metadata startup script as root on each boot.
set -euo pipefail
exec > >(tee -a /var/log/hw4-reporter-startup.log) 2>&1

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y curl python3-venv

metadata() {
  curl --fail --silent --show-error -H 'Metadata-Flavor: Google' \
    "http://metadata.google.internal/computeMetadata/v1/$1"
}

project_id="$(metadata project/project-id)"
subscription_id="$(metadata instance/attributes/hw4-subscription)"

install -d -m 0755 /opt/hw4/second_service
metadata instance/attributes/hw4-listener-py > /opt/hw4/second_service/forbidden_listener.py
metadata instance/attributes/hw4-listener-requirements > /opt/hw4/second_service/requirements.txt
python3 -m venv /opt/hw4/venv
/opt/hw4/venv/bin/pip install --no-cache-dir -r /opt/hw4/second_service/requirements.txt

if ! id hw4svc >/dev/null 2>&1; then
  useradd --system --home-dir /opt/hw4 --shell /usr/sbin/nologin hw4svc
fi

cat > /etc/systemd/system/hw4-reporter.service <<EOF
[Unit]
Description=HW4 forbidden-country Pub/Sub reporter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hw4svc
Group=hw4svc
WorkingDirectory=/opt/hw4/second_service
Environment=PYTHONUNBUFFERED=1
Environment=PROJECT_ID=${project_id}
Environment=SUBSCRIPTION_ID=${subscription_id}
ExecStart=/opt/hw4/venv/bin/python /opt/hw4/second_service/forbidden_listener.py
Restart=always
RestartSec=3
NoNewPrivileges=true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now hw4-reporter.service
systemctl --no-pager --full status hw4-reporter.service
