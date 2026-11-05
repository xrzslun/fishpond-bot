# FishPond 一键部署包

> 官网：https://xrzs.cloud

> ⚠ **本源码完全免费发布，请勿通过购买获取。**
> 作者 QQ：`2844642318`　交流群：`243625638`

## 加密包说明

每次打包会生成两个文件：

- `qqbot-deploy.tar.gz` —— 未加密（自己留着更新用，别外发）
- `qqbot-deploy.tar.gz.enc` —— **AES-256 加密**（发给别人的版本，需要密码才能解压）

解密（对方服务器执行）：

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in qqbot-deploy.tar.gz.enc -out qqbot-deploy.tar.gz \
  -pass pass:你设置的密码
```

加密打包（本机执行）：`bash pack.sh`，会提示设置密码（回车自动随机生成）。


把「QQ 机器人（大肥鱼）」整套系统复制到任意 Ubuntu/Debian 服务器。

包含：NapCat（QQ 协议端，Docker）+ DeepSeek 桥接服务 + 管理后台 + Cloudflare 隧道（公网访问，无需开端口）。

## 服务器要求

- Ubuntu 20.04+ / Debian 11+（x86_64 或 arm64）
- **2 核 2G 内存**起步（脚本会自动加 2G swap）
- 能访问 Docker Hub / GitHub / Cloudflare（国内服务器建议配好 Docker 镜像加速）
- 一张能扫码登录的 QQ 小号（建议不常用的小号）

## 使用方法

1. 把 `qqbot-deploy.tar.gz` 传到服务器：

```bash
scp qqbot-deploy.tar.gz root@你的服务器:/root/
```

2. 解压并执行：

```bash
ssh root@你的服务器
mkdir -p /root/qqbot-deploy
tar xzf /root/qqbot-deploy.tar.gz -C /root/qqbot-deploy
cd /root/qqbot-deploy
sudo bash install.sh
```

3. 按提示输入 DeepSeek API Key（可跳过，之后补）

4. 安装完成后脚本会打印：
   - 管理后台地址（Cloudflare 隧道 URL）
   - 管理员账号密码
   - 下一步操作指引

## 包内不含什么（安全说明）

这个部署包**只包含代码和配置模板**，不含任何账号数据：

- ❌ 不含 DeepSeek API Key（安装时由你输入，写进对方服务器的 `.env`）
- ❌ 不含 QQ 登录态（对方扫码登录，登录态存在对方服务器）
- ❌ 不含管理后台数据库（管理员/白名单/关键词/前缀/频率/表情包记录都是全新生成的）
- ❌ 不含上传的表情包图片
- ❌ 不含你的服务器 IP、隧道地址
- ✅ 每次安装都会随机生成新的 NapCat WebUI Token 和管理员密码
- ✅ 人设、内置语料、结束语词表等模板内容会带过去（这是功能配置，不是隐私）

重新打包：在本目录执行 `bash pack.sh`，脚本会先做密钥扫描，发现疑似 Key/Token 会中止。

## 自定义后台路径

在 `bridge/config.yaml` 里改：

```yaml
webui:
  path: /admin
```

重启后后台地址变为 `https://你的域名/admin`（根路径会 404）。
更新源 `/updates/latest.json` 仍保持在根路径。

## 安装时的访问方式选择

安装脚本会询问管理页面的访问方式：
1. **临时外链**（Cloudflare 隧道，免费、无需域名，地址重启可能变化）
2. **自己的域名**（需解析到本机并开放 80/443，自动申请 HTTPS）
3. **仅本地**（127.0.0.1:8080，用 SSH 隧道访问）

## 安装完成后

1. 打开管理后台 → 用 `admin` + 打印的密码登录
2. 「扫码登录」→「申请扫码二维码」→ 手机 QQ 扫码
3. 「白名单」添加允许机器人回复的群号
4. 按需配置：关键词、回复前缀、群聊回复（按人接话/一直接话/省流模式）、回复频率、表情包、无聊模式

## 常用运维

```bash
sudo systemctl status qqbot-bridge      # 桥接状态
sudo journalctl -u qqbot-bridge -f      # 桥接日志
sudo systemctl restart qqbot-bridge     # 重启桥接
sudo docker logs -f napcat              # NapCat 日志
sudo docker compose -f /opt/qqbot/compose.yaml ps
# 隧道地址（重启服务器后可能变化）
sudo journalctl -u cloudflared-tunnel | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1
```

## 修改配置

- **人设 / 模型 / 触发词种子**：`/opt/qqbot/bridge/config.yaml`，改完 `sudo systemctl restart qqbot-bridge`
- **DeepSeek Key**：两种方式
  - 后台「模型」页（推荐）：添加多个 API（预设或自定义 base_url），每个 API 保存后都有「测试」按钮可验证；点「启用」切换当前使用的模型，立即生效
  - 或安装时输入 / 编辑 `/opt/qqbot/bridge/.env`（600 权限）后重启桥接
- **白名单 / 关键词 / 前缀 / 频率 / 表情包**：都在管理后台里改，立即生效

## 常见问题

- **QQ 被踢下线后要反复扫码**：NapCat 默认没有快速登录账号，被踢后只能扫码。安装时提供机器人 QQ 号即可开启快速登录：
  ```bash
  export NAPCAT_ACCOUNT=你的机器人QQ号
  bash install.sh
  ```
  已经装好的，编辑 `compose.yaml` 在 napcat 的 `environment` 里加一行 `ACCOUNT: "你的QQ号"`，再 `docker compose up -d`。
  注意：腾讯强制要求验证时仍需要扫码，这属于账号风控，不是代码问题。
- **Docker 拉镜像慢/失败**：给 Docker 配镜像加速，或把 `compose.yaml` 里的 `mlikiowa/napcat-docker:latest` 换成 `docker.xuanyuan.run/mlikiowa/napcat-docker:latest`
- **隧道地址变了**：Cloudflare 免费快速隧道的 URL 每次重启会变，用上面的命令取新地址；如需固定域名，请在阿里云/腾讯云防火墙放行 443 并用自有域名 + Caddy 反向代理
- **QQ 掉线**：管理后台 →「扫码登录」重新申请二维码扫码即可
- **封号风险**：个人号协议有风险，务必用小号；控制「回复频率」（每群 3~5 条/分钟、间隔 5~10 秒比较稳）
- **海外服务器**：登录国内 QQ 风控概率更高，建议国内机房

## 安全提醒

- 管理后台密码在安装时随机生成，请登录后改成自己的
- 不要把自己的服务器密码/SSH 密钥告诉他人
- 表情包通过隧道地址公开访问，注意不要上传敏感图片
