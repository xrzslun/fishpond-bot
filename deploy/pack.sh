#!/usr/bin/env bash
# 重新打包部署包（代码 + 模板，不含任何账号数据）
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "== 1. 安全检查（防止把密钥/令牌打进包里）=="
if grep -rInE 'sk-[A-Za-z0-9]{20,}' files install.sh README.md 2>/dev/null; then
  echo "!! 发现疑似 DeepSeek API Key，已中止打包"
  exit 1
fi
if grep -rInE '[0-9a-f]{48}' files 2>/dev/null; then
  echo "!! 发现疑似 NapCat WebUI Token（48位hex），已中止打包"
  exit 1
fi
echo "   未发现密钥/令牌"

echo "== 1.5 脏文件检查（数据库/备份/字节码一律不许进包）=="
DIRTY=$(find files -type f \( -name '*.db' -o -name '*.db-*' -o -name '*.sqlite*' \
        -o -name '*.pyc' -o -name '*.bak*' -o -name '*.log' -o -name 'config.yaml' \) 2>/dev/null)
if [ -n "$DIRTY" ]; then
  echo "!! 发布目录内有不该打包的文件，已中止："
  echo "$DIRTY"
  exit 1
fi
if find files -type d -name '__pycache__' 2>/dev/null | grep -q .; then
  echo "!! 发布目录内有 __pycache__，请先删除，已中止"
  find files -type d -name '__pycache__'
  exit 1
fi
echo "   未发现数据库/备份/字节码"

echo "== 2. 打包 =="
tar czf qqbot-deploy.tar.gz \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.bak*' \
  --exclude='*.db' --exclude='config.yaml' --exclude='*.log' \
  install.sh pack.sh check.sh files README.md
ls -la qqbot-deploy.tar.gz
sha256sum qqbot-deploy.tar.gz

echo "== 3. 加密（AES-256）=="
PASS="${PACK_PASS:-}"
if [ -z "$PASS" ] && [ -t 0 ]; then
  read -r -s -p "  设置发出去的压缩包密码（回车自动随机生成）: " PASS
  echo
fi
if [ -z "$PASS" ]; then
  PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 14)
  echo "  已自动生成密码"
fi
if openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -in qqbot-deploy.tar.gz -out qqbot-deploy.tar.gz.enc -pass pass:"$PASS" 2>/dev/null; then
  ENC_OK=1
elif openssl enc -aes-256-cbc -salt -pbkdf2 -in qqbot-deploy.tar.gz -out qqbot-deploy.tar.gz.enc -pass pass:"$PASS"; then
  ENC_OK=1
else
  ENC_OK=0
fi

echo ""
echo "==============================================="
echo " 打包完成"
echo " 明文包：qqbot-deploy.tar.gz      （自己留着，别外发）"
if [ "$ENC_OK" = "1" ]; then
  echo " 加密包：qqbot-deploy.tar.gz.enc  （发给别人这个）"
  echo " 解压密码：$PASS"
  echo ""
  echo " 对方解密命令："
  echo "   openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \\"
  echo "     -in qqbot-deploy.tar.gz.enc -out qqbot-deploy.tar.gz \\"
  echo "     -pass pass:$(printf '%s' "$PASS")"
  sha256sum qqbot-deploy.tar.gz.enc
else
  echo " !! 加密失败，请检查 openssl 是否安装"
fi
echo ""
echo " 提醒：本源码免费，请勿倒卖。作者QQ 2844642318 群 243625638"
echo "==============================================="
