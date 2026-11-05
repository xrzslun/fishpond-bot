#!/usr/bin/env bash
# FishPond 一键部署脚本
# 适用于 Ubuntu 20.04+ / Debian 11+，需要 root 或 sudo
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="${INSTALL_DIR:-/opt/qqbot}"
RUN_USER="${RUN_USER:-${SUDO_USER:-$(id -un)}}"
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

trap 'echo "!! 安装中断，请查看上方错误信息"; exit 1' ERR

# ---------- 非交互参数（供 AI/自动化使用） ----------
DS_KEY="${FISHPOND_DS_KEY:-}"
DS_SET="${FISHPOND_DS_KEY+1}"
ASR_ANS="${FISHPOND_ASR:-}"
ACCESS_MODE="${FISHPOND_MODE:-}"
MODE_SET="${FISHPOND_MODE+1}"
MY_DOMAIN="${FISHPOND_DOMAIN:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --key) DS_KEY="$2"; DS_SET=1; shift 2;;
    --asr) ASR_ANS="$2"; shift 2;;
    --mode) ACCESS_MODE="$2"; MODE_SET=1; shift 2;;
    --domain) MY_DOMAIN="$2"; shift 2;;
    *) shift;;
  esac
done

echo "==============================================="
echo "  FishPond 一键部署"
echo "  ⚠ 本源码完全免费发布，请勿通过购买获取"
echo "  作者 QQ：2844642318   交流群：243625638"
echo "  安装目录: $DIR"
echo "  运行用户: $RUN_USER"
echo "==============================================="

if command -v apt-get >/dev/null 2>&1; then
  OS_APT=1
else
  echo "!! 仅支持 Debian/Ubuntu（需要 apt-get）"
  exit 1
fi

if [ -z "${DS_SET:-}" ] && [ -t 0 ]; then
  read -r -p "DeepSeek API Key（sk-...，可直接回车跳过，之后可补）: " DS_KEY
fi
DS_KEY="${DS_KEY:-}"

echo "[1/7] 安装系统依赖..."
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq curl ca-certificates openssl python3-venv python3-pip ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "!! ffmpeg 安装失败：语音会用纯 Python 去提示音（无法转 mp3），可稍后手动执行 apt-get install -y ffmpeg"
fi

echo "[2/7] 检查 Docker..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | $SUDO sh
else
  echo "  Docker 已安装: $(docker --version)"
fi
if ! $SUDO docker compose version >/dev/null 2>&1; then
  $SUDO apt-get install -y -qq docker-compose-plugin 2>/dev/null || true
fi
if ! $SUDO docker compose version >/dev/null 2>&1; then
  echo "!! docker compose 插件不可用，请手动安装 docker-compose-plugin"
  exit 1
fi

echo "[3/7] 创建目录与配置文件..."
$SUDO mkdir -p "$DIR/bridge/stickers" "$DIR/data/napcat"
if [ -f "$DIR/bridge/config.yaml" ]; then
  $SUDO cp "$DIR/bridge/config.yaml" "$DIR/bridge/config.yaml.bak.$(date +%s)"
  echo "  已有配置已备份"
fi
$SUDO cp "$SCRIPT_DIR/files/compose.yaml" "$DIR/compose.yaml"
$SUDO cp "$SCRIPT_DIR/files/bridge/bot.py" "$DIR/bridge/bot.py"
$SUDO cp "$SCRIPT_DIR/files/bridge/config.yaml.template" "$DIR/bridge/config.yaml"
$SUDO cp "$SCRIPT_DIR/files/bridge/qqbot-bridge.service" /etc/systemd/system/qqbot-bridge.service
$SUDO cp "$SCRIPT_DIR/files/cloudflared-tunnel.service" /etc/systemd/system/cloudflared-tunnel.service

WEBUI_TOKEN=$(openssl rand -hex 24)
ADMIN_PASS=$(openssl rand -hex 8)
$SUDO sed -i "s/__WEBUI_TOKEN__/$WEBUI_TOKEN/g" "$DIR/compose.yaml" "$DIR/bridge/config.yaml"
# 机器人 QQ 号（可选）：填了以后被踢下线可自动快速登录，不用每次扫码
$SUDO sed -i "s/__NAPCAT_ACCOUNT__/${NAPCAT_ACCOUNT:-}/g" "$DIR/compose.yaml"
$SUDO sed -i "s/__ADMIN_PASSWORD__/$ADMIN_PASS/g" "$DIR/bridge/config.yaml"
$SUDO sed -i "s|__RUN_USER__|$RUN_USER|g; s|__DIR__|$DIR|g" /etc/systemd/system/qqbot-bridge.service /etc/systemd/system/cloudflared-tunnel.service

if [ -n "$DS_KEY" ]; then
  printf 'DEEPSEEK_API_KEY=%s\n' "$DS_KEY" | $SUDO tee "$DIR/bridge/.env" >/dev/null
elif [ ! -f "$DIR/bridge/.env" ]; then
  $SUDO touch "$DIR/bridge/.env"
fi
$SUDO chmod 600 "$DIR/bridge/.env"

echo ""
if [ -z "${ASR_ANS:-}" ]; then
  if [ -t 0 ]; then
    echo "本地语音识别（Whisper）需要额外下载约 75MB 模型，用于把语音转成文字。"
    read -r -p "是否安装本地语音识别？可跳过，之后也能在后台再装 [Y/n]: " ASR_ANS
  fi
fi
ASR_YES=1
case "${ASR_ANS:-Y}" in [nN]*) ASR_YES=0;; esac

echo "[4/7] 创建 Python 虚拟环境..."
$SUDO python3 -m venv "$DIR/bridge/venv"
$SUDO "$DIR/bridge/venv/bin/pip" install -q --upgrade pip 2>/dev/null || true
PIP_PKGS="aiohttp pyyaml pillow edge-tts qrcode cryptography"
if [ "$ASR_YES" = "1" ]; then
  PIP_PKGS="$PIP_PKGS faster-whisper"
fi
if ! $SUDO "$DIR/bridge/venv/bin/pip" install -q -i https://pypi.tuna.tsinghua.edu.cn/simple $PIP_PKGS 2>/dev/null; then
  $SUDO "$DIR/bridge/venv/bin/pip" install -q $PIP_PKGS
fi

if [ "$ASR_YES" = "1" ]; then
  echo "[4.5/7] 预下载本地语音识别模型（约 75MB，可失败跳过）..."
  $SUDO "$DIR/bridge/venv/bin/python" -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')" 2>/dev/null || echo "  模型预下载失败，首次使用时再下载"
else
  echo "[4.5/7] 已跳过本地语音识别（未安装 faster-whisper 与模型）；需要时重跑安装脚本或在后台启用"
fi

echo "[5/7] 小内存机器补充 swap..."
if ! $SUDO swapon --show 2>/dev/null | grep -q '/swapfile'; then
  MEM=$(free -m | awk '/Mem:/{print $2}')
  if [ "${MEM:-2048}" -lt 1800 ] && [ ! -f /swapfile ]; then
    $SUDO fallocate -l 2G /swapfile 2>/dev/null || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    $SUDO chmod 600 /swapfile && $SUDO mkswap /swapfile >/dev/null && $SUDO swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
    echo "  已创建 2G swap"
  fi
fi

if [ -z "${ACCESS_MODE:-}" ]; then
  if [ -t 0 ]; then
    echo ""
    echo "管理页面访问方式："
    echo "  1) 临时外链（Cloudflare 隧道，免费、无需域名，地址重启可能变化）"
    echo "  2) 自己的域名（需已解析到本机、开放 80/443，自动申请 HTTPS）"
    echo "  3) 仅本地访问（127.0.0.1:8080，用 SSH 隧道访问）"
    read -r -p "请选择 [1/2/3，默认 1]: " ACCESS_MODE
  fi
fi
ACCESS_MODE="${ACCESS_MODE:-1}"

if [ "$ACCESS_MODE" = "1" ]; then
  echo "[6/7] 安装 cloudflared 临时隧道..."
  if ! command -v cloudflared >/dev/null 2>&1; then
    curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    $SUDO install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
  fi
elif [ "$ACCESS_MODE" = "2" ]; then
  echo "[6/7] 配置 Caddy + 自定义域名..."
  if [ -z "${MY_DOMAIN:-}" ] && [ -t 0 ]; then
    read -r -p "请输入你的域名（如 bot.example.com）: " MY_DOMAIN
  fi
  MY_DOMAIN="${MY_DOMAIN:-}"
  if [ -z "$MY_DOMAIN" ]; then echo "!! 未输入域名，改为仅本地访问"; ACCESS_MODE=3; fi
  if [ "$ACCESS_MODE" = "2" ]; then
    $SUDO apt-get install -y -qq caddy >/dev/null 2>&1 || true
    $SUDO tee /etc/caddy/Caddyfile >/dev/null <<EOF
{
	admin off
}

$MY_DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8099
}
EOF
  fi
else
  echo "[6/7] 仅本地访问，跳过外链和域名配置"
fi

$SUDO chown -R "$RUN_USER":"$RUN_USER" "$DIR"

echo "[7/7] 启动服务..."
cd "$DIR"
$SUDO docker compose up -d
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now qqbot-bridge
if [ "$ACCESS_MODE" = "1" ]; then
  $SUDO systemctl enable --now cloudflared-tunnel
fi
if [ "$ACCESS_MODE" = "2" ]; then
  $SUDO systemctl restart caddy
fi

echo "等待服务就绪..."
sleep 12
URL=""
if [ "$ACCESS_MODE" = "1" ]; then
  URL=$($SUDO journalctl -u cloudflared-tunnel --no-pager 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)
fi

echo ""
echo "==============================================="
echo " ✅ 部署完成"
echo ""
if [ "$ACCESS_MODE" = "1" ] && [ -n "$URL" ]; then
  echo " 管理后台:      $URL"
elif [ "$ACCESS_MODE" = "1" ]; then
  echo " 管理后台:      隧道地址获取失败，稍后执行："
  echo "   sudo journalctl -u cloudflared-tunnel | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1"
elif [ "$ACCESS_MODE" = "2" ]; then
  echo " 管理后台:      https://$MY_DOMAIN （证书自动申请，首次打开可能需要几秒）"
else
  echo " 管理后台:      http://127.0.0.1:8080 （本地访问，SSH 转发：ssh -L 8080:127.0.0.1:8080 用户@服务器）"
fi
echo " 管理员账号:    admin"
echo " 管理员密码:    $ADMIN_PASS"
echo " NapCat Token:   $WEBUI_TOKEN"
echo ""
echo " 下一步："
echo "   1. 打开上面的管理后台，用 admin / $ADMIN_PASS 登录"
echo "   2. 点「扫码登录」→「申请扫码二维码」，用手机 QQ 扫码（建议用小号）"
echo "   3. 到「白名单」添加允许机器人回复的群号"
echo "   4. 到「关键词」「回复前缀」「群聊回复」按需配置"
echo ""
if [ "$ASR_YES" = "0" ]; then
  echo " ℹ️  本地语音识别未安装：语音转文字功能不可用（后台 ASR 自动关闭），TTS 语音回复仍可用"
fi
if [ -z "$DS_KEY" ]; then
  echo " ⚠️  未配置 DeepSeek Key：编辑 $DIR/bridge/.env 填入 DEEPSEEK_API_KEY=sk-xxx"
  echo "     然后执行 sudo systemctl restart qqbot-bridge"
fi
echo ""
echo " ⚠ 本源码完全免费发布，请勿通过购买获取"
echo "   作者 QQ：2844642318   交流群：243625638"
echo ""
echo " 常用命令："
echo "   sudo systemctl status qqbot-bridge"
echo "   sudo journalctl -u qqbot-bridge -f"
echo "   sudo docker logs -f napcat"
echo "==============================================="
