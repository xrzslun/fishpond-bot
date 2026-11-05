#!/bin/bash
# 发布目录包更新：bot.py + fishpond + web，避免只更新 bot.py 缺模块
set -euo pipefail
V="${1:?用法: release_pkg.sh <version> [notes]}"
NOTES="${2:-}"
DIR=/opt/qqbot/bridge
cd "$DIR"
TMP="/tmp/update-$V.tar.gz"
tar czf "$TMP" \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.db' --exclude='*.db-*' \
  --exclude='config.yaml' --exclude='tunnel_url' --exclude='snapshots' \
  bot.py fishpond web
SHA=$(sha256sum "$TMP" | awk '{print $1}')
SIZE=$(stat -c%s "$TMP")
sudo mkdir -p "$DIR/updates"
sudo cp "$TMP" "$DIR/updates/bot-$V.tar.gz"
DATE=$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M')
TMPJSON=$(mktemp /tmp/latest.XXXXXX.json)
cat > "$TMPJSON" <<JSON
{
  "version": "$V",
  "date": "$DATE",
  "notes": "$NOTES",
  "url": "https://xrzs.cloud/updates/bot-$V.tar.gz",
  "sha256": "$SHA",
  "min_version": "",
  "type": "package",
  "size": $SIZE
}
JSON
sudo cp "$TMPJSON" "$DIR/updates/latest.json"
rm -f "$TMPJSON"
sudo chown -R "$(id -un)":"$(id -gn)" "$DIR/updates"
echo "已发布 v$V ($DATE)"
echo "url: https://xrzs.cloud/updates/bot-$V.tar.gz"
echo "sha256: $SHA"
