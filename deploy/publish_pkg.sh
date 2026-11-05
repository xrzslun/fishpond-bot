#!/usr/bin/env bash
# 打包并发布到下载站（需 SSHPASS 环境变量，或用 SSH 密钥）
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

REMOTE="${REMOTE:-ubuntu@43.132.175.12}"
DL_DIR="${DL_DIR:-/var/www/fishpond/dl}"
PACK_PASS="${PACK_PASS:-F7q2Lm9Xz4Rt}"
VERSION=$(grep -m1 'APP_VERSION = ' files/bridge/bot.py | sed 's/.*"\([0-9.]*\)".*/\1/')
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"; SCP="scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
if [ -n "${SSHPASS:-}" ] && command -v sshpass >/dev/null 2>&1; then
  SSH="sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"; SCP="sshpass -e scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
fi

echo "== 打包 $VERSION =="
rm -f qqbot-deploy.tar.gz qqbot-deploy.tar.gz.enc
PACK_PASS="$PACK_PASS" bash pack.sh >/dev/null
SHA=$(sha256sum qqbot-deploy.tar.gz.enc | awk '{print $1}')
sed -i "s/FISHPOND_FALLBACK_SHA:-[0-9a-f]\{64\}/FISHPOND_FALLBACK_SHA:-$SHA/" bootstrap-install.sh
SIZE=$(stat -c%s qqbot-deploy.tar.gz.enc)
DATE=$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M')
cat > latest-pkg.json <<JSON
{
  "version": "$VERSION",
  "date": "$DATE",
  "url": "https://xrzs.cloud/dl/qqbot-latest.tar.gz.enc",
  "sha256": "$SHA",
  "size": $SIZE
}
JSON

echo "== 上传 =="
$SCP qqbot-deploy.tar.gz.enc "$REMOTE:/tmp/pkg.enc"
$SCP qqbot-deploy.tar.gz "$REMOTE:/tmp/pkg.tar.gz"
$SCP bootstrap-install.sh "$REMOTE:/tmp/install.sh"
$SCP check.sh "$REMOTE:/tmp/check.sh"
$SCP latest-pkg.json "$REMOTE:/tmp/latest.json"
$SSH "$REMOTE" "sudo mkdir -p $DL_DIR && sudo cp /tmp/pkg.enc $DL_DIR/qqbot-latest.tar.gz.enc && sudo cp /tmp/pkg.tar.gz $DL_DIR/qqbot-latest.tar.gz && sudo cp /tmp/pkg.enc $DL_DIR/qqbot-$VERSION.tar.gz.enc && sudo cp /tmp/pkg.tar.gz $DL_DIR/qqbot-$VERSION.tar.gz && sudo cp /tmp/install.sh $DL_DIR/install.sh && sudo cp /tmp/check.sh $DL_DIR/check.sh && sudo cp /tmp/latest.json $DL_DIR/latest.json && sudo chmod 644 $DL_DIR/*"

$SCP ../fishpond/tools/smoke_http.py "$REMOTE:/tmp/smoke_http.py"
$SSH "$REMOTE" "rm -rf /tmp/smoke_pkg && mkdir -p /tmp/smoke_pkg && tar xzf /tmp/pkg.tar.gz -C /tmp/smoke_pkg && /opt/qqbot/bridge/venv/bin/python3 /tmp/smoke_http.py /tmp/smoke_pkg" || { echo "!! HTTP 冒烟失败，已中止发布"; exit 1; }

$SCP ../tests/test_update_path.py "$REMOTE:/tmp/test_update_path.py"
$SSH "$REMOTE" 'BOT=$(find /tmp/smoke_pkg -name bot.py -path "*bridge*" | head -1); if [ -n "$BOT" ]; then BOT_PY="$BOT" /opt/qqbot/bridge/venv/bin/python3 -m unittest discover -s /opt/qqbot/tests -p test_update_path.py; else echo "!! 包内找不到 bot.py"; exit 1; fi' || { echo "!! 更新路径回归测试失败，已中止发布"; exit 1; }

echo "== 冒烟测试 =="
SSH_CMD="$SSH $REMOTE" PUBLIC_BASE="https://xrzs.cloud" bash ./smoke_test.sh || { echo "!! 发布后冒烟失败，请立即检查"; exit 1; }

echo "== 完成 =="
echo " 版本: $VERSION"
echo " SHA256: $SHA"
echo " 直链: https://xrzs.cloud/dl/qqbot-latest.tar.gz.enc"
