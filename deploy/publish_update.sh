#!/bin/bash
# 发布更新源：上传自包含 bot_fat.py（兼容只替换 bot.py 的旧版更新器）
set -euo pipefail
cd "$(dirname "$0")"
V="${1:?用法: publish_update.sh <version> [notes]}"
NOTES="${2:-}"
FAT="files/bot_fat.py"
[ -f "$FAT" ] || { echo "缺少 $FAT，先运行 make_fat.py"; exit 1; }
REMOTE="${REMOTE:-ubuntu@43.132.175.12}"
SSH="sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
SCP="sshpass -e scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
$SCP "$FAT" "$REMOTE:/tmp/bot_fat_pub.py"
SHA=$(sha256sum "$FAT" | awk '{print $1}')
SIZE=$(stat -c%s "$FAT")
DATE=$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M')
$SSH "$REMOTE" "sudo cp /tmp/bot_fat_pub.py /opt/qqbot/bridge/updates/bot.py; sudo chown ubuntu:ubuntu /opt/qqbot/bridge/updates/bot.py; python3 - <<PY
import json
p='/opt/qqbot/bridge/updates/latest.json'
d={'version':'$V','date':'$DATE','notes':'''$NOTES''','url':'https://xrzs.cloud/updates/bot.py','sha256':'$SHA','min_version':'','type':'file','size':$SIZE}
open(p,'w').write(json.dumps(d,ensure_ascii=False,indent=2))
PY
sudo chown ubuntu:ubuntu /opt/qqbot/bridge/updates/latest.json"
echo "已发布 $V"
echo "sha256: $SHA ($SIZE bytes)"
