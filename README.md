# FishPond QQ Bot

一个带“世界引擎”的 QQ 机器人：角色有自己的作息、情绪、钱包、日记和事件，能刷 B 站、发实况照片、自拍，并通过独立后台管理。

> 仅用于学习和个人研究。请遵守 QQ、B 站、NapCat 的使用条款，不要用于骚扰、刷量或商业用途。

## 功能

- **世界引擎**：51 种日常活动、睡眠/工作/吃饭/通勤、工资与账本、日记、随机事件
- **拟人聊天**：角色卡、口头禅、关系记忆、低情绪抑制、打字节奏
- **B 站实况**：扫码 / Cookie 登录，刷推荐、点赞、评论、私信超管、分享视频链接
- **实况照片**：二次元场景图与自拍，按角色外观和当前状态生成
- **生活系统**：任务、承诺提醒、天气、消费、目标
- **管理后台**：Web 面板、账号与权限、模型供应商、表情包、世界状态、更新
- **APP 接口**：登录、聊天、SSO、设备绑定、强制更新

## 技术栈

- Python 3.12 + aiohttp
- SQLite
- NapCat / OneBot 11（WebSocket）
- Caddy（反代）
- systemd

## 快速开始

```bash
git clone https://github.com/xrzslun/fishpond-bot.git
cd fishpond-bot
cp bridge/config.example.yaml bridge/config.yaml   # 按需修改
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python bot.py
```

> `config.yaml`、`data.db`、`.env`、证书和备份不会进入仓库。

## 目录

```
bridge/         入口、后台页面、账号与配置
fishpond/       功能模块（world / bili / biliacct / image / chat / ...）
deploy/         安装、发布、更新脚本
tests/          单元测试
docs/           方案与文档
```

## 开发

```bash
python3 -m compileall -q fishpond bridge
node --check fishpond/web/js/app.js
python3 fishpond/tools/check_index.py
```

## 部署

见 [部署指南](部署指南.md) 与 `deploy/install.sh`。

## 安全

- 不要提交 `data.db`、`config.yaml`、`.env`、密钥
- 后台路径建议改掉默认值
- 公网部署请加 HTTPS 和强密码

## License

MIT
