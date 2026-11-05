#!/usr/bin/env bash
# 发布后冒烟：服务、表情图公开访问、更新源 sha、版本一致性
set -u
SSH_CMD="${SSH_CMD:-}"
PUBLIC="${PUBLIC_BASE:-https://xrzs.cloud}"
fail=0
chk(){ printf "  %-42s " "$1"; shift; if "$@" >/dev/null 2>&1; then echo OK; else echo FAIL; fail=1; fi; }

run_remote(){ $SSH_CMD "$1"; }

echo "== 冒烟测试 =="
for s in qqbot-bridge fishpond-scripts fishpond-host caddy; do
  printf "  %-42s " "服务 $s"
  if run_remote "systemctl is-active $s" | grep -q '^active$'; then echo OK; else echo FAIL; fail=1; fi
done

v=$(run_remote "grep -m1 APP_VERSION /opt/qqbot/bridge/bot.py | awk -F'\"' '{print \$2}'" | head -1)
printf "  %-42s %s\n" "线上版本" "$v"

printf "  %-42s " "表情图公开访问 200"
F=$(run_remote "ls /opt/qqbot/bridge/stickers | head -1")
code=$(curl -s -o /tmp/smoke_sticker -w '%{http_code}' "$PUBLIC/stickers/$F" || echo 000)
disk=$(run_remote "stat -c%s /opt/qqbot/bridge/stickers/$F")
got=$(stat -c%s /tmp/smoke_sticker 2>/dev/null || echo 0)
if [ "$code" = "200" ] && [ "$got" = "$disk" ]; then echo "OK (${got}B)"; else echo "FAIL code=$code got=$got disk=$disk"; fail=1; fi

printf "  %-42s " "更新源 sha 与文件一致"
decl=$(curl -s "$PUBLIC/updates/latest.json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["sha256"])')
real=$(curl -s "$PUBLIC/updates/bot.py" | sha256sum | cut -d' ' -f1)
[ "$decl" = "$real" ] && echo OK || { echo "FAIL $decl != $real"; fail=1; }

printf "  %-42s " "后台页面可访问"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$PUBLIC/xrzs/bot/QQbot/")" = "200" ] && echo OK || { echo FAIL; fail=1; }

if [ "$fail" = "1" ]; then echo "!! 冒烟未通过"; exit 1; fi
echo "== 冒烟全部通过 =="
