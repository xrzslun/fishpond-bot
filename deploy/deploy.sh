#!/usr/bin/env bash
# 智能部署：生成发布版 → 只有代码真的变了才上传并重启
# 用法:
#   bash deploy/deploy.sh            # 自动判断，代码没变就跳过重启
#   bash deploy/deploy.sh --force    # 强制上传并重启
set -euo pipefail
cd "$(dirname "$0")/.."

REMOTE="${REMOTE:-ubuntu@43.132.175.12}"
LOCAL_FILE="deploy/files/bridge/bot.py"
REMOTE_FILE="/opt/qqbot/bridge/bot.py"
FORCE="${1:-}"

SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20"
SCP="scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
if [ -n "${SSHPASS:-}" ] && command -v sshpass >/dev/null 2>&1; then
  SSH="sshpass -e $SSH"
  SCP="sshpass -e $SCP"
fi

echo "== 1. 生成发布版 =="
rm -rf deploy/files/bridge/__pycache__
python3 deploy/make_release.py

LOCAL_SHA=$(sha256sum "$LOCAL_FILE" | awk '{print $1}')
echo "   本地发布版 sha: $LOCAL_SHA"

echo "== 2. 对比线上代码 =="
REMOTE_SHA=$($SSH "$REMOTE" "sha256sum $REMOTE_FILE 2>/dev/null | awk '{print \$1}'" || true)
echo "   线上代码 sha:   ${REMOTE_SHA:-（读取失败）}"

if [ "$FORCE" != "--force" ] && [ -n "$REMOTE_SHA" ] && [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  echo "== 代码没有变化，跳过上传和重启（避免无意义重连）=="
  exit 0
fi

echo "== 3. 上传并重启 =="
TS=$(date +%Y%m%d-%H%M%S)
$SCP "$LOCAL_FILE" "$REMOTE:/tmp/bot_new.py"
$SSH "$REMOTE" "set -e
  cp $REMOTE_FILE $REMOTE_FILE.bak.$TS
  cp /tmp/bot_new.py $REMOTE_FILE
  sudo test -d /opt/fishpond/app && sudo cp $REMOTE_FILE /opt/fishpond/app/bot.py && sudo chown fishpond:fishpond /opt/fishpond/app/bot.py || true
  sudo systemctl restart qqbot-bridge
  sleep 6
  echo -n '   服务: '; systemctl is-active qqbot-bridge
  echo -n '   版本: '; grep -m1 APP_VERSION $REMOTE_FILE
  sudo journalctl -u qqbot-bridge --since '1 min ago' --no-pager | grep '启动版本' | tail -1 || true
  sudo journalctl -u qqbot-bridge --since '1 min ago' --no-pager | grep -m1 '机器人 QQ 号' || echo '   （暂未看到 QQ 连接日志，稍等几秒）'
  echo '   备份: $REMOTE_FILE.bak.$TS'"

echo "== 完成 =="
