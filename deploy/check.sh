#!/usr/bin/env bash
# FishPond 安装前环境自检（只读，不改系统）
set -uo pipefail

ok=0; warn=0; bad=0
say_ok(){ echo "  ✅ $*"; ok=$((ok+1)); }
say_warn(){ echo "  ⚠️  $*"; warn=$((warn+1)); }
say_bad(){ echo "  ❌ $*"; bad=$((bad+1)); }

echo "==============================================="
echo "  FishPond 安装前自检"
echo "==============================================="

echo ""
echo "[系统]"
if [ -r /etc/os-release ]; then
  . /etc/os-release
  echo "  ${PRETTY_NAME:-unknown}"
  case "${ID:-}" in
    ubuntu|debian) say_ok "系统类型支持（$ID）";;
    *) say_bad "仅支持 Ubuntu/Debian，当前 $ID";;
  esac
else
  say_bad "无法读取 /etc/os-release"
fi
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then say_ok "架构 x86_64"; else say_bad "架构 $ARCH 不受支持（需要 x86_64）"; fi

if command -v apt-get >/dev/null 2>&1; then say_ok "apt-get 可用"; else say_bad "缺少 apt-get"; fi
if command -v curl >/dev/null 2>&1; then say_ok "curl 可用"; else say_bad "缺少 curl"; fi
if command -v openssl >/dev/null 2>&1; then say_ok "openssl 可用"; else say_warn "缺少 openssl（手动解密包需要）"; fi
if command -v ffmpeg >/dev/null 2>&1; then say_ok "ffmpeg 可用"; else say_warn "缺少 ffmpeg（语音会退化为纯 Python 去提示音）"; fi

echo ""
echo "[资源]"
MEM=$(free -m | awk '/Mem:/{print $2}')
DISK=$(df -Pm / | awk 'NR==2{print $4}')
[ "${MEM:-0}" -ge 1800 ] && say_ok "内存 ${MEM}MB" || say_warn "内存 ${MEM}MB，建议 >=2G（会尝试加 swap）"
[ "${DISK:-0}" -ge 8000 ] && say_ok "根分区剩余 ${DISK}MB" || say_warn "磁盘剩余 ${DISK}MB，建议 >=8G"

if command -v docker >/dev/null 2>&1; then say_ok "Docker 已安装"; else say_warn "Docker 未安装（安装脚本会自动装）"; fi
if systemctl is-active --quiet docker 2>/dev/null; then say_ok "Docker 服务运行中"; fi

echo ""
echo "[网络]"
for u in https://api.deepseek.com https://github.com https://pypi.org https://get.docker.com; do
  if curl -sI -m 8 "$u" >/dev/null 2>&1; then say_ok "$u 可访问"; else say_warn "$u 访问超时（可能影响安装）"; fi
done

echo ""
echo "[端口]"
for p in 80 443 8080 8099; do
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$p$"; then
    say_warn "端口 $p 已被占用"
  else
    say_ok "端口 $p 空闲"
  fi
done

echo ""
echo "[已安装]"
if [ -d /opt/qqbot ]; then say_warn "检测到 /opt/qqbot 已存在（重复安装会覆盖代码，数据保留）"; else say_ok "/opt/qqbot 不存在，可全新安装"; fi

echo ""
echo "==============================================="
echo "  通过 $ok 项，警告 $warn 项，不通过 $bad 项"
if [ "$bad" -eq 0 ]; then
  echo "  ✅ 可以安装"
  exit 0
else
  echo "  ❌ 存在硬性条件不满足，请先解决上面 ❌ 项"
  exit 1
fi
