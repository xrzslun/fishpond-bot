#!/bin/bash
# 在目标服务器上执行：MODE=prep|finish
set -e
AUTH="echo \"\$SUDOPASS\" | sudo -S "
[ "$(id -u)" = "0" ] && AUTH=""
run() { eval "$AUTH$1"; }
if [ "$MODE" = "prep" ]; then
  run "apt-get update -qq"
  run "env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io python3-venv python3-pip autossh sshpass"
  run "systemctl enable --now docker" || true
  cat > /tmp/fp_daemon.json <<'JSON'
{"registry-mirrors":["https://docker.xuanyuan.run","https://docker.m.daocloud.io","https://docker.1ms.run"]}
JSON
  run "mkdir -p /etc/docker"
  run "cp /tmp/fp_daemon.json /etc/docker/daemon.json"
  run "systemctl restart docker"
  run "docker pull mlikiowa/napcat-docker:latest" || true
  id fishpond >/dev/null 2>&1 || run "useradd -r -m -s /bin/bash fishpond"
  run "usermod -aG docker fishpond"
  run "mkdir -p /opt/fishpond/app /opt/fishpond/hosting /opt/fishpond/tenants"
  run "chown -R fishpond:fishpond /opt/fishpond"
  run "mkdir -p /home/fishpond/.ssh"
  run "chown fishpond:fishpond /home/fishpond/.ssh"
  run "sudo -u fishpond ssh-keygen -t ed25519 -N '' -f /home/fishpond/.ssh/id_ed25519 -q" 2>/dev/null || true
  echo "PUBKEY:$(run "cat /home/fishpond/.ssh/id_ed25519.pub" 2>/dev/null || sudo cat /home/fishpond/.ssh/id_ed25519.pub)"
  exit 0
fi
run "cp /tmp/bot.py /opt/fishpond/app/bot.py"
run "cp /tmp/admin.py /opt/fishpond/hosting/admin.py"
run "cp /tmp/tenant.py /opt/fishpond/hosting/tenant.py"
run "chmod +x /opt/fishpond/hosting/*.py"
run "chown -R fishpond:fishpond /opt/fishpond"
run "python3 -m venv /opt/fishpond/venv"
run "/opt/fishpond/venv/bin/pip install -q --upgrade pip"
run "/opt/fishpond/venv/bin/pip install -q aiohttp pyyaml numpy qrcode pillow"
cat > /tmp/fp_host.env <<ENV
HOST_ADMIN_USER=owner
HOST_ADMIN_PASS=$HOST_PASS
FISHPOND_HOST_ROOT=/opt/fishpond
FISHPOND_HOST_DOMAIN=xrzs.cloud
ENV
run "cp /tmp/fp_host.env /opt/fishpond/host.env"
run "chmod 600 /opt/fishpond/host.env"
cat > /tmp/fp_host.service <<UNIT
[Unit]
Description=FishPond hosting master admin (remote)
After=network-online.target docker.service
[Service]
User=ubuntu
EnvironmentFile=/opt/fishpond/host.env
ExecStart=/opt/fishpond/venv/bin/python3 /opt/fishpond/hosting/admin.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
cat > /tmp/fp_tunnel.service <<UNIT
[Unit]
Description=Tunnel to HK controller
After=network-online.target
[Service]
User=root
ExecStart=/usr/bin/autossh -M 0 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -i /home/fishpond/.ssh/id_ed25519 -R 127.0.0.1:$TUNNEL_PORT:127.0.0.1:8090 $HK_USER@$HK_HOST
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
run "cp /tmp/fp_host.service /etc/systemd/system/fishpond-host.service"
run "cp /tmp/fp_tunnel.service /etc/systemd/system/fishpond-tunnel.service"
run "systemctl daemon-reload"
run "systemctl enable --now fishpond-host"
run "systemctl enable --now fishpond-tunnel"
sleep 3
systemctl is-active fishpond-host fishpond-tunnel
