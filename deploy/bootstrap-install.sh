#!/usr/bin/env bash
# FishPond 一键安装引导（自动读取最新版本与校验值）
set -euo pipefail

BASE="${FISHPOND_BASE:-https://xrzs.cloud/dl}"
PASS="${FISHPOND_PKG_PASS:-F7q2Lm9Xz4Rt}"
PKG_URL="${FISHPOND_PKG_URL:-}"
PKG_SHA="${FISHPOND_PKG_SHA:-}"
DRY=0
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift;;
    --pass) PASS="$2"; shift 2;;
    --pkg) PKG_URL="$2"; shift 2;;
    --sha) PKG_SHA="$2"; shift 2;;
    *) ARGS+=("$1"); shift;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "!! 请用 root 或 sudo 执行"
  exit 1
fi

export FISHPOND_ASR="${FISHPOND_ASR:-n}"
export FISHPOND_MODE="${FISHPOND_MODE:-1}"

echo "== 1/4 读取最新版本信息 =="
META=""
for i in 1 2 3; do
  if META=$(curl -fsSL --connect-timeout 15 "$BASE/latest.json" 2>/dev/null); then break; fi
  sleep 1
done
if [ -n "$META" ]; then
  if command -v python3 >/dev/null 2>&1; then
    M_URL=$(printf '%s' "$META" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("url",""))' 2>/dev/null || true)
    M_SHA=$(printf '%s' "$META" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("sha256",""))' 2>/dev/null || true)
    M_VER=$(printf '%s' "$META" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("version",""))' 2>/dev/null || true)
  else
    M_URL=$(printf '%s' "$META" | grep -o '"url"[^"]*"[^"]*"' | head -1 | sed 's/.*"\(http[^"]*\)".*/\1/')
    M_SHA=$(printf '%s' "$META" | grep -o '"sha256"[^"]*"[^"]*"' | head -1 | sed 's/.*"\([0-9a-f]\{64\}\)".*/\1/')
    M_VER=$(printf '%s' "$META" | grep -o '"version"[^"]*"[^"]*"' | head -1 | sed 's/.*"\([0-9.]*\)".*/\1/')
  fi
  PKG_URL="${PKG_URL:-$M_URL}"
  PKG_SHA="${PKG_SHA:-$M_SHA}"
  echo "  最新版本: ${M_VER:-未知}"
else
  echo "  ⚠️  读取版本清单失败，使用内置地址"
fi
PKG_URL="${PKG_URL:-$BASE/qqbot-latest.tar.gz.enc}"
PKG_SHA="${PKG_SHA:-${FISHPOND_FALLBACK_SHA:-a1602f5acddf618322cf2727712d094dd167dea1c96c5602b530cd65995abfa5}}"
if [ -z "$PKG_SHA" ]; then
  echo "!! 没有可用的校验值，请加 --sha 参数"; exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "== 2/4 下载安装包 =="
curl -fL --retry 3 --connect-timeout 20 -o "$TMP/pkg.enc" "$PKG_URL"
echo "== 3/4 校验文件 =="
if ! echo "$PKG_SHA  $TMP/pkg.enc" | sha256sum -c -; then
  echo "!! 校验失败：文件下载不完整或版本不匹配，请重试"
  exit 1
fi

echo "== 4/4 解密并准备安装 =="
if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$TMP/pkg.enc" -out "$TMP/pkg.tar.gz" -pass pass:"$PASS" 2>/dev/null; then
  openssl enc -d -aes-256-cbc -md sha256 \
    -in "$TMP/pkg.enc" -out "$TMP/pkg.tar.gz" -pass pass:"$PASS"
fi

mkdir -p "$TMP/src"
tar xzf "$TMP/pkg.tar.gz" -C "$TMP/src"
chmod +x "$TMP/src/install.sh" "$TMP/src/check.sh" 2>/dev/null || true

if [ "$DRY" -eq 1 ]; then
  echo ""
  echo "dry-run 完成，包内容正常："
  ls -1 "$TMP/src"
  exit 0
fi

echo ""
echo "-- 环境自检 --"
if ! bash "$TMP/src/check.sh"; then
  echo ""
  echo "!! 自检未通过（上面有 ❌ 项），已停止安装。"
  echo "   请先解决这些硬性条件，或把输出发给管理员。"
  exit 1
fi

cd "$TMP/src"
echo ""
echo "开始安装（API Key 留空则装完后到后台填）..."
exec bash install.sh "${ARGS[@]}"
