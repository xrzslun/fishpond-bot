#!/bin/bash
# 发布新版本到更新源（在服务器上运行）
set -e
V="$1"; NOTES="${2:-}"; MIN="${3:-}"
DIR=/opt/qqbot
if [ -z "$V" ]; then echo "用法: sudo bash release.sh <version> [notes] [min_version]"; exit 1; fi
mkdir -p "$DIR/bridge/updates"
cp "$DIR/bridge/bot.py" "$DIR/bridge/updates/bot.py"
SHA=$(sha256sum "$DIR/bridge/updates/bot.py" | awk '{print $1}')
DATE=$(date "+%Y-%m-%d %H:%M")
cat > "$DIR/bridge/updates/latest.json" <<EOF
{
  "version": "$V",
  "date": "$DATE",
  "notes": "$NOTES",
  "url": "https://xrzs.cloud/updates/bot.py",
  "sha256": "$SHA",
  "min_version": "$MIN"
}
EOF
chown -R "$(id -un)":"$(id -gn)" "$DIR/bridge/updates"
echo "已发布 v$V ($DATE)"
echo "sha256: $SHA"
