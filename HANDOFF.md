# FishPond QQ Bot 项目交接文档

> 更新时间：2026-10-29 04:45（Asia/Shanghai）
> 用途：新会话/新维护者接手时先读这一份。密钥、密码等敏感信息不写入本文件。

---

## 1. 项目概览

- 项目名：FishPond（原 QQ DeepSeek Bot）
- 形态：NapCat（QQ 协议）+ Python aiohttp 桥接 + 单文件 Web 管理后台
- 机器人 QQ：`1571154120`
- 超级管理员 QQ：`2844642318`
- 主群：养鱼（372155636）、蓝色大肥鱼技术分享（243625638）等
- 更新方式：`/opt/qqbot/bridge/updates/latest.json` + 后台一键更新
- 安装包：AES-256-CBC + PBKDF2(200000) 加密，密码不写入本文件

---

## 2. 服务器与访问

| 项目 | 值 |
|---|---|
| 服务器 | `YOUR_SERVER_IP` |
| SSH 用户 | `ubuntu`（sudo 可用；root 密码登录已关闭） |
| 域名 | `https://xrzs.cloud` |
| 后台地址 | `https://xrzs.cloud/xrzs/bot/QQbot/` |
| 后台账号 | `admin`（super）、`心如止水`（super）、`user`（viewer，本地启用） |
| 密码 | 不写入本文件，见密码管理/原会话 |
| 系统 | Ubuntu，2C2G，Caddy 反代 |
| 时区 | Asia/Shanghai |

### 服务

| 服务 | 说明 |
|---|---|
| `qqbot-bridge` | Python 桥接，监听 127.0.0.1:8099（后台/接口） |
| `napcat`（Docker） | OneBot WS 127.0.0.1:3001；WebUI 127.0.0.1:6099 |
| Caddy | 80/443，反代后台、`/stats/*`、`/updates/*`、`/stickers/*` |
| `fishpond-stats` | 独立统计服务 127.0.0.1:8098，后台 `/stats/` |

### 常用目录

```
/opt/qqbot/bridge/
├── bot.py                 # 线上运行代码（发布版或本地版）
├── bot.py.bak*            # 更新备份
├── data.db                # SQLite 主库
├── backups/               # 每日自动备份，保留 7 天
├── updates/               # 更新源：bot.py + latest.json + failure.log
├── stickers/              # 表情包文件
├── config.yaml            # 人设、OneBot、上下文配置
└── venv/                  # Python 依赖
```

工作区源码：

```
/root/Documents/deepseek-harness/default-workspace/qq-deepseek-bot/
├── bridge/bot_admin.py    # 主源码（开发版）
├── deploy/
│   ├── make_release.py    # 生成发布版（VIEWER_FEATURE=False，记忆保留）
│   ├── pack.sh            # 打包 + 加密
│   ├── publish_pkg.sh     # 发布安装包到 /dl
│   ├── bootstrap-install.sh
│   ├── install.sh
│   ├── check.sh
│   └── files/bridge/bot.py # 发布版产物
├── HANDOFF.md
└── ...
```

---

## 3. 版本与发布状态

| 项目 | 值 |
|---|---|
| 当前线上代码 | **3.5.5**（开发版 `bot_admin.py` 直接 scp，含生图 + 自画像模板 + 黑话批量，`VIEWER_FEATURE=True`） |
| 更新源版本 | **3.5.5**（12:10 旧构建，**不含生图、不含黑话批量删除**） |
| 更新源 min_version | **3.5.5** |
| 本地开发版 | **3.5.5**（开发期不动版本号，发布时才 bump；`deploy/files/bridge/bot.py` 已同步为同版本发布版） |
| 安装包 | `https://xrzs.cloud/dl/qqbot-latest.tar.gz.enc` |
| 更新包 | `https://xrzs.cloud/updates/bot.py` |
| 最新 SHA256 | 以 `/updates/latest.json` 为准 |
| app_version | 数据库 settings 里为 3.5.5 |

> 版本号规则见 `RELEASE_POLICY.md`：**开发期间 `APP_VERSION` 一律不动**，只有用户确认发布新版本时才 bump，
> 并与打包、`latest.json`、`app_version` 一次性同步。日常改动只走「改代码 → scp 到线上 → 重启」。

> ⚠️ 2026-10-29 核对：`/updates/bot.py` 与 `/dl` 安装包里的 3.5.5（450200 B，构建于 12:10）**没有生图模块**
> （缺 `generate_image`/`handle_image`/`image_jobs` 表等 12 个函数）也没有 `slang_delete_many`。
> 生图只存在于服务器正在运行的开发版副本里。见第 13 节。

### 发布规则（必须遵守）

1. **用户说“发版/发布”才发**，不要自动 bump 版本。
2. **观察者角色永不发布**：`make_release.py` 强制 `VIEWER_FEATURE=False`。
3. **记忆功能保留发布**（3.5 起），不要再关掉。
4. 发布包不能包含个人后台路径、数据库、密码、统计后台地址。
5. 发版流程：
   ```bash
   cd deploy
   python3 make_release.py
   python3 -m py_compile files/bridge/bot.py
   SSHPASS='***' PACK_PASS='***' bash publish_pkg.sh
   ```
   然后上传 `files/bridge/bot.py` 到 `/opt/qqbot/bridge/updates/bot.py`，写 `latest.json`，同步 `app_version`。

### 强制更新机制（3.5.5 起）

- `latest.json` 的 `min_version` 决定强制范围。
- 3.5.5 有半强制：
  - 顶部红色横幅不可关闭
  - 写操作（POST/PUT/DELETE）返回 426
  - 读操作、QQ 聊天不受影响
  - 右下角悬浮「强制更新」按钮
  - 更新失败 QQ 通知超管 + 写 `updates/failure.log`，旧文件不动
- **老版本（<3.5.5）没有 426 中间件**，只会看到强制提示；真正锁写操作要等下一版强制 3.5.5。
- 已排提醒：`schedule-04bbc6d9-4382-4821-a5fe-d6058bfb6a14`，检查 3.5.5 升级分布后发 3.5.6 并把 min_version 设为 3.5.6。

---

## 4. 当前功能与开关

数据库 `settings` 关键值（2026-10-29）：

| key | 值 | 说明 |
|---|---|---|
| `memory_enabled` | 1 | 记忆开启 |
| `image_enabled` | 1 | 生图开启 |
| `image_model` | `Qwen/Qwen-Image` | 用户已切到高质量模型 |
| `image_steps` | 25 | 非 Turbo 最低 20 |
| `image_enhance` | 1 | 提示词优化开启 |
| `image_scope` | all | 所有人可用 |
| `image_daily_limit` | 5 | 每人每日 5 张 |
| `image_size` | 1024x1024 | |
| `image_api_key` | 已配置 | 硅基流动，不写入文档 |
| `image_self_desc` | 默认蓝发少女 | 画“你自己”时使用 |
| `gender_aware` | 1 | 但 QQ 多数返回 unknown |
| `wake_enabled` | 0/1 视配置 | 休息强制唤醒 |
| `roast_enabled` | 1 | 怼人开启 |
| `roast_mode` | fast/think | 默认 fast |
| `slang_enabled` | 未开/按需 | 黑话模式 |
| `music_enabled` | 1 | 音乐点歌 |
| `reminder_enabled` | 默认 1 | 提醒 |

数据库规模（2026-10-29）：

- `memories`：816 条
- `slang_terms`：约 14 条（会随聊天增长）
- `stickers`：181 条
- `reminders`：若干
- `image_jobs`：有测试记录

功能清单：

- 群聊/私聊 AI 对话、接话模式、限频
- 白名单（群/用户）、黑名单、超管
- 记忆：提取、注入、清理、AI 审核、全量列表
- 黑话：识别、词库、AI 优化、批量删除
- 怼人：快速/思考双模式、三级程度、精确触发词
- 休息模式：时间、白名单、通知、强制唤醒
- 音乐点歌：网易云搜索 + QQ 音乐卡片
- 生图：硅基流动，模型切换、价格提示、提示词优化、人设/记忆/黑话注入
- 提醒：独立类 `ProactiveMessenger`，到点 AI 主动发消息
- 好友申请自动处理
- 统计心跳、更新检查、半强制更新

---

## 5. 代码地图（bot_admin.py）

| 区域 | 说明 |
|---|---|
| `class Store` | SQLite 全部读写、建表、迁移 |
| `class ProactiveMessenger` | 提醒/主动消息：parse/handle/compose/send/loop |
| `class Bridge` | 主逻辑 |
| `Bridge.handle_message` | 消息总入口，触发判断、怼人、音乐、生图、提醒、AI 回复 |
| `Bridge.ask_deepseek` | 组装人设/时间/记忆/黑话/分段，调用模型 |
| `Bridge.llm_complete` | 通用模型调用，兼容推理模型空正文重试 |
| `Bridge.memory_prompt` | 记忆遍历、过滤、相关性注入 |
| `Bridge.extract_memories` | 记忆提取（超管每条同步，普通用户异步） |
| `Bridge.generate_image` | 生图 API + 下载图片 |
| `Bridge.enhance_image_prompt` | 生图提示词优化、人设/记忆/黑话注入 |
| `Bridge.handle_image` | 生图命令、配额、发送 base64 图片 |
| `Bridge.handle_wake` | 休息强制唤醒状态机 |
| `Bridge.roast_user` | 怼人生成（fast/think） |
| `Bridge.update_info` | 检查 latest.json |
| `Bridge.api_update_apply` | 更新：下载、sha、语法预检、备份、替换、失败通知 |
| `start_admin_server` | 后台路由和权限中间件 |

后台单文件页面：

- 导航：状态 / 机器人 / 聊天 / 白名单 / 超级管理员
- 机器人子页：人设、模型、语音、休息、黑话、生图、记忆、设置
- 聊天子页：接话、群聊回复、频率、关键词、前缀、结束语、表情包、无聊模式

---

## 6. 数据库关键表

| 表 | 用途 |
|---|---|
| `admins` | 后台账号、角色、配额、禁用 |
| `settings` | 所有配置 |
| `wl_groups` / `wl_users` | 白名单 |
| `blacklist` | 黑名单 |
| `memories` | 长期记忆（owner_qq/level/content/use_count/permanent） |
| `slang_terms` | 黑话词库 |
| `stickers` | 表情包（含 description） |
| `rest_groups` / `rest_users` / `rest_notify_groups` | 休息配置 |
| `wake_log` | 每日唤醒次数 |
| `wake_replies` | 唤醒回复去重 |
| `reminders` | 提醒/主动消息 |
| `image_jobs` | 生图记录、配额统计 |
| `friend_requests` | 好友申请 |
| `login_logs` | 登录日志、IP 归属地 |
| `providers` | 模型供应商 |

迁移：`Store._init()` 里有 `PRAGMA table_info` 自动补列，已覆盖 `stickers.description`、`admins` 多列、`login_logs.location` 等。

---

## 7. 运维命令

```bash
# 状态
systemctl status qqbot-bridge --no-pager
sudo docker ps
sudo docker logs --tail 100 napcat

# 重启
sudo systemctl restart qqbot-bridge

# 日志
sudo journalctl -u qqbot-bridge -f

# 备份
ls -lh /opt/qqbot/bridge/backups/
# 手动备份
sqlite3 /opt/qqbot/bridge/data.db ".backup '/opt/qqbot/bridge/backups/manual.db'"

# 更新失败日志
cat /opt/qqbot/bridge/updates/failure.log

# 检查更新源
curl -s https://xrzs.cloud/updates/latest.json

# 检查 QQ 在线
curl -s -c /tmp/ck -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"***"}' \
  https://xrzs.cloud/xrzs/bot/QQbot/api/login >/dev/null
curl -s -b /tmp/ck https://xrzs.cloud/xrzs/bot/QQbot/api/status
```

---

## 8. 已知问题与风险

1. **QQ 被踢下线**：NapCat 会要求重新扫码；代码只能退避重连，无法避免。需排查同号多端/风控。
2. **性别感知不可靠**：QQ 多数成员 `sex=unknown`，已加兜底和缓存；不能强行猜。
3. **生图模型能力**：Kolors 免费但复杂构图弱；Qwen-Image 强但慢/贵。非 Turbo 步数低于 20 会被强制抬到 20。
4. **生图依赖第三方**：硅基流动接口、Key 余额、模型名都可能变化。
5. **音乐卡片依赖 NapCat 签名服务**：签名超时会退回文字链接。
6. **更新供应链**：目前只校验 SHA256，没有签名；域名被劫持仍有风险。
7. **无自动化测试**：改动需手工验证关键链路。
8. **密码策略**：最短 6 位，无 2FA；后台暴露公网。
9. **grouped 记忆重复**：提取去重是启发式，可能出现相似条目。
10. **老版本强制更新**：<3.5.5 没有 426，只有提示。

---

## 9. 待办 / 下一版发布清单

- [x] 生图功能完整上线（开发版已部署到线上；发布包尚未含，等确认发版时一起打）
- [x] 黑话词库批量勾选删除（开发版已含，发布包待同步）
- [x] 生图测试提示词 + 页面展示图片（开发版已含）
- [x] 生图人设/记忆/黑话注入（开发版已含 `enhance_image_prompt`）
- [x] 自画像固定形象（Q版鲸鱼女仆，仅作用于「画你自己」，开发版已部署）
- [ ] 确认升级率（10-29 实测 3.5.5 占 2/10，4 个实例滞留 3.3.5×2、3.5.2×2）
- [ ] **等用户确认发版**后再：bump 版本号 → `make_release.py` → 打包 → 上传 `updates/bot.py` + 写 `latest.json`（含 `min_version`）→ 同步 `app_version`
- [ ] 更新说明草稿见 `deploy/latest-3.5.6.draft.json`（版本号/日期/SHA 发布时再填）
- [ ] 发布后验证 `/updates/latest.json`、`/dl/latest.json`、SHA
- [ ] （可选）聊天里自我描述与自画像形象不一致：会说自己「胖鱼、饭碗扣头」，图上却是鲸鱼女仆，需要时可把人设里加一句外观锚点

### 发布前检查

```bash
cd /root/Documents/deepseek-harness/default-workspace/qq-deepseek-bot
python3 deploy/make_release.py
grep -m1 'VIEWER_FEATURE' deploy/files/bridge/bot.py   # 必须是 False
grep -m1 'MEMORY_FEATURE' deploy/files/bridge/bot.py   # 必须是 True
python3 -m py_compile deploy/files/bridge/bot.py
```

---

## 10. 测试矩阵（手工）

| 功能 | 测试 |
|---|---|
| 普通群聊 | @机器人 说话，有上下文 |
| @别人 | 不接话 |
| 私聊 | 正常回复 |
| 记忆 | 超管说重要事件，换个群/私聊能回忆 |
| 黑话 | 发“绝绝子”，能理解；词库可批量删 |
| 怼人 | @目标 发“怼他”，快速/思考都回 |
| 休息唤醒 | 休息时段超管 @，前 N 次装睡 |
| 音乐 | @机器人 播放 歌名，发卡片 |
| 生图 | @机器人 画一只猫，收到图片 |
| 生图自画像 | 画一个你认为的自己，蓝发少女 |
| 提醒 | 提醒我10点…，到点收到 |
| 后台 | 登录、改设置、保存 |
| 更新 | 检查更新、失败通知、旧版保留 |

---

## 11. 安全与密钥

- API Key、后台密码、SSH 密码**不写入本文件**。
- 生图 Key 存在 `settings.image_api_key`，后台只返回 `sk-***`。
- 模型 Key 存在 `providers` 表，后台掩码显示。
- 发布包不应包含 `data.db`、`config.yaml`、个人路径。
- 备份含用户数据，注意权限（当前 `data.db` 640 ubuntu:caddy）。

---

## 12. 交接注意事项

1. 先读本文件，再读 `bridge/bot_admin.py` 的 `handle_message` 和 `ask_deepseek`。
2. 改代码前先备份：
   ```bash
   cp /opt/qqbot/bridge/bot.py /opt/qqbot/bridge/bot.py.bak.$(date +%Y%m%d-%H%M%S)
   cp /opt/qqbot/bridge/data.db /opt/qqbot/bridge/data.db.bak.$(date +%Y%m%d-%H%M%S)
   ```
3. 部署本地改动：scp 到 `/opt/qqbot/bridge/bot_admin.py`，复制为 `bot.py`，重启服务。
4. 发布版从 `deploy/make_release.py` 生成，不要直接改 `deploy/files/bridge/bot.py`。
5. 任何“发版”操作必须得到用户明确同意。

---

## 13. 2026-10-29 接手记录（巡检 + 生图/自画像改动，未发版）

### 当时实测

- `qqbot-bridge` / `fishpond-stats` / `caddy` 全 active，napcat `Up 2 days`，04:51 仍在收消息（QQ 在线）
- `updates/failure.log` 空；`/updates/latest.json` 与 `/dl/latest.json` 的 SHA 下载实测一致
- 线上 `bot.py`（474006 B，04:35）md5 = 本机 `bridge/bot_admin.py`（开发版，含当时已写的生图功能）
- 线上 `VIEWER_FEATURE=True` + `enable_viewer_role=1` + `admins` 有 `user/viewer` → 观察者线上可用
  （**这是设计如此**，见 `RELEASE_POLICY.md`「观察者仅主人服务器保留」；只有发布包必须是 False，不算问题）
- 更新源/安装包里的 3.5.5 是 12:10 旧构建：无生图、无黑话批量删除，且安装包混入 `__pycache__/bot.cpython-312.pyc`
- stats.db 仅 10 个实例：3.5.5 ×2、3.5.4 ×1、3.5.3 ×1、3.5.2 ×2、3.5.1 ×2、3.3.5 ×2
- data.db：memories 822、slang 110、stickers 181、image_jobs 9、reminders 1

### 已做的备份

```
服务器:
  /opt/qqbot/bridge/bot.py.bak.20261029-045641
  /opt/qqbot/bridge/data.db.bak.20261029-045641
本地:
  .backups/bot_admin.py.bak.20261029-045645
  .backups/bot.py.bak.20261029-045645   （3.5.5 原文发布产物，便于回滚/比对）
```

### 本次本地改动

> 注：曾一度把 `APP_VERSION` 改成 3.5.6，按 `RELEASE_POLICY.md`（开发期不动版本号）已回退为 **3.5.5**。

1. `bridge/bot_admin.py`：`APP_VERSION` 保持 **3.5.5**；新增自画像固定模板（见下）
2. `deploy/make_release.py`：
   - 新增硬性检查：`VIEWER_FEATURE=False`、`MEMORY_FEATURE=True`、`APP_VERSION` 存在、`compile()` 语法预检
   - 新增禁用内容扫描：`xrzs.cloud/xrzs`、`YOUR_SERVER_IP`、`/root/`、`sk-xxxx`、48 位 hex Token
   - 检查不通过直接 `exit 1`，不再产出带问题的产物
3. `deploy/pack.sh`：
   - 新增「脏文件检查」：`*.db` / `*.pyc` / `*.bak*` / `*.log` / `config.yaml` / `__pycache__` 一律中止打包
   - `tar` 增加 `--exclude` 兜底
4. 删除 `deploy/files/bridge/__pycache__`（旧字节码，620741 B）
5. 新增 `deploy/latest-3.5.6.draft.json`：更新说明草稿，版本号/日期/SHA 等发布时再填
6. 重新生成 `deploy/files/bridge/bot.py`（3.5.5，观察者关、记忆留，与开发版仅差 1 行）

### 部署记录（2026-10-29 05:15）

- 按 `RELEASE_POLICY.md` 默认流程：`scp bridge/bot_admin.py → /opt/qqbot/bridge/bot.py` + `systemctl restart qqbot-bridge`
- 备份：`/opt/qqbot/bridge/bot.py.bak.20261029-051459`（前一份 `bot.py.bak.20261029-045641`）
- 重启后日志：`连接 NapCat: ws://127.0.0.1:3001` → `已连接，开始接收消息`，无报错
- 线上版本号仍是 3.5.5，更新源未动

### 3.5.6 产物自检结果

### 产物自检结果（3.5.5 发布版）

- `compile()` OK，9331 行
- 与开发版差异仅 1 行（`VIEWER_FEATURE`），其余完全一致
- 相对上一份 3.5.5 发布产物：新增函数 `enhance_image_prompt`，改动 156 行；再叠加自画像模板
- 生图链路函数齐备：`generate_image` / `handle_image` / `send_image_bytes` / `image_scope_ok` / `image_count_today` / `api_image_test` / `api_image_config`
- 黑话批量：`slang_delete_many` / `api_slang_delete_many`
- 半强制：`status=426`、`report_update_failure`×10、悬浮按钮、`imgtestimg`×2、模型价格文案 `Z-Image-Turbo`×4
- 试打包通过：包内仅 `install.sh / pack.sh / check.sh / files/bridge/{bot.py,config.yaml.template,qqbot-bridge.service} / files/{cloudflared-tunnel.service,compose.yaml} / README.md`，无 pyc/db/备份；试包已删除

### 自画像专项优化（同日追加，仅影响「画你自己」）

用户反馈：线上「画一张你自己」出来是「蓝发少女躺沙发、旁边饭碗和鱼」的插画，预期是 Q 版鲸鱼女仆立绘。

原因定位（三处叠加）：
1. `image_self_desc` 库里没设置 → 用旧默认「水手服、气质慵懒、身边有鱼群元素」，直接把画面推向躺沙发场景
2. `enhance_image_prompt` 命中「你」时会追加「让 AI 先用第一人称自述画面」，生活场景描述覆盖了立绘需求
3. LLM 改写输出被限制「最多 150 字」，画风/构图/服装细节塞不下

改动：
- 新增模块级常量与方法：`SELF_STYLE_DEFAULT`（Q版chibi/三头身/正面全身/纯白背景/赛璐璐平涂）、`SELF_DESC_DEFAULT`（鲸鱼女仆外观定稿）、`SELF_NEGATIVE_DEFAULT`、`is_self_image()`、`self_image_extra()`、`build_self_image_prompt()`
- `enhance_image_prompt`：画「AI 自己」时**直接走固定模板，不经 LLM 改写、不走自述场景**，且**独立于「提示词优化」开关**；普通生图分支保持 3.5.5 原行为不变
- `generate_image`：自画像用 `image_self_negative`（含 写实/坐姿/躺姿/场景/家具/水印 等），普通生图仍用 `image_negative`
- 后台生图页新增两项输入：「自画像画风锁」`image_self_style`、「自画像负面」`image_self_negative`，`/api/image` 与 `/api/image/config` 同步支持
- 判定规则收紧：`is_self_image` 只认 你自己/自画像/你本人/你长什么样/你的样子/你认为的自己/你现在的样子/自我画像/画你；排除「画你们」「画你的房间」「画你说的那个场景」等
- 验证：v1/v2 两张真图（Qwen-Image 25 步，各 ¥0.3）已把鲸鱼女仆形象跑出来，对比图在 `.preview/selftest_self_v1.png`、`.preview/selftest_self_v2.png`；v2 定为默认值
- 注意：`negative_prompt` 只在非 Turbo/Schnell/flux 模型下发，切到 Z-Image-Turbo 时自画像负面不生效

### 自画像升级为「图生图」（同日第二轮，形象锁定）

用户要「以后画 AI 自己就照这张参考图来」。纯文字提示词还原度不够（v4b/v4d 会长出鲸鱼头当耳朵），
改成优先用 `Qwen/Qwen-Image-Edit` 拿参考图做图像编辑，实测还原度最高。

- 新增常量：`SELF_EDIT_MODEL_DEFAULT = "Qwen/Qwen-Image-Edit"`、`SELF_EDIT_PROMPT_DEFAULT`（整理成 Q 版立绘的编辑指令）
- `generate_image`：判定为自画像且配置了 `image_self_ref` 时先走图生图（`_image_call` 抽成公共方法）；
  图生图异常会 `log.warning` 并**回退文字模板**，不影响出图
- 参考图支持两种写法：公网 URL，或服务器本地路径（本地会转 base64 上传）
- 新增设置项：`image_self_ref`（参考图 URL/路径，**默认空**）、`image_self_edit_model`、`image_self_edit_prompt`
- 后台生图页新增「自画像参考图」「图生图模型」两个输入框
- 服务端实况：参考图放在 `/opt/qqbot/bridge/stickers/self_ref.jpg`
  （≈ `https://xrzs.cloud/stickers/self_ref.jpg`，Caddy 可直接访问）；DB 的 `image_self_ref` 指向它
- **发布包默认 `image_self_ref` 为空** → 其他用户拿不到主人服务器的图片地址，自动退回文字模板，符合发布规则
- 验证：`generate_image("画一张你自己")` 端到端跑通，日志 `自画像图生图成功: Qwen/Qwen-Image-Edit`，出图见 `.preview/prod_e2e.png`
- 成本：调参累计约 ¥4.5（v1~v3、v4a~d、v5a/b、edit1~3、线上 e2e），`Qwen-Image-Edit` 同样按张计费
- 结论：参考图 = 用户给的第二张图；文字模板保留为兜底

### 后台「生图」页布局重排（同日第三轮）

按其他页面（记忆/休息）的既有规范重排，不再是一个大卡片堆控件：

- 统一用 `.card` + `<h2 style="font-size:14px;color:#8b93a5">` 小标题 + `.hint` 说明 + `.memgrid > label` 参数格 + `.msg` 提示
- 拆成 6 张卡：**生图**（开关+简介，`.memhead` 风格）/ **接口与模型**（地址、Key、模型下拉、尺寸、步数、限额、可用范围、提示词优化开关）/ **提示词**（通用负面词）/ **自画像（画你自己）**（参考图、图生图模型、画风锁、外观、自画像负面、图生图编辑指令 textarea）/ **测试生图**（提示词+按钮+结果图）/ **保存** / **模型怎么选**（说明）
- 新增前端字段：`imgselfeditprompt`（对应 `image_self_edit_prompt`），已接入 `loadImageCfg` / `saveImage`
- 保存提示改到「保存」卡片的 `imgsavemsg`，测试提示仍在 `imgmsg`
- 校验：标签平衡（div 319/319、label 32/32、select 15/15、textarea 3/3、button 99/99）、JS 引用的 id 无缺失、线上文件同样校验通过
- 已按默认流程部署（未升版本号、未动更新源），重启后 `已连接，开始接收消息`

### 生图额度改为可配置（同日第四轮）

原来「超管不限额」是代码写死的（`if not is_super and ...`）。按用户要求改成开关：

- 新增设置 `image_super_unlimited`，**默认 `"1"`（保持原有行为）**
- `handle_image` 判断改为 `if not (is_super and super_unlimited) and image_count_today >= limit`
  → 关掉开关后超管也按每日限额算
- 页面新增独立卡片「额度与权限」：**每日限额单独一行**（`input imglimit` + 「张/人」+ 按钮 `imgsuperbtn`），
  按钮点一下立即生效（`toggleImageSuperUnlimited()` → POST `{super_unlimited: !cur}` → 重新加载），
  下方保留「可用范围」`imgscope`，并用 hint 说明「限额只统计成功的图」
- `/api/image` 返回 `super_unlimited`；`/api/image/config` 接受并写入
- 校验：标签平衡（div 322/322、label 31/31、select 15/15、textarea 3/3、button 100/100），JS 引用 id 无缺失
- 已部署重启（未升版本号、未动更新源）

### 文案改「AI画像（画AI）」（同日第五轮）

用户要求：后台面向用户的叫法从「自画像（画你自己）」改成「AI画像（画AI）」，并让「画AI」真的能触发。

- 界面：卡片标题改为 **AI画像（画AI）**；卡内说明改为「只有用户说『画AI / AI画像 / 画你自己 / 你长什么样』这类话时才生效」；
  「自画像画风锁 / 自画像负面 / 提示词优化说明 / 测试提示」等文案一并改为「AI画像」或「画AI」，生图页已无「自画像」字样
- 识别词：`SELF_HINTS` 增加 `AI画像`/`ai画像`；新增正则 `画[一1]?[张个幅只]?(ai|a.i.)`（先去空格转小写），
  支持「画AI」「画一张AI」「画个AI」「画 ai」等
- `self_image_extra`：额外剥离 AI 字样，保证「画AI在吃面」→ 剩余要求「在吃面」
- 回归测试：13 条应触发 + 7 条不应触发全部通过（「画你们」「画你的房间」「画你说的那个场景」不误伤）
- 线上实测：「画一张AI」→ 日志 `自画像图生图成功: Qwen/Qwen-Image-Edit`，出图为鲸鱼女仆立绘（`.preview/ai_kw_test.png`，¥0.3）
- 已部署重启（未升版本号、未动更新源）

### 用户侧生图说明（同日第六轮）

用户要求「给用户加个说明」。做成 QQ 里可随时问的帮助，不耗额度：

- 新增 `Bridge.image_help_text(is_super)`：动态读取每日限额与「超管不限制」，超管显示「你这边不限张数」
- 触发词（需 @ 或私聊）：画图帮助 / 生图帮助 / 画图说明 / 画图怎么用 / 怎么画图 / 如何画图 / 画AI帮助 / help
  - 判定会先去掉空格转小写，且**放在生图正则之前**，避免「画图帮助」被当成提示词去画一张“帮助”
  - 生图功能关闭时回「生图功能还没开」
- 内容：触发方式、提示词越具体越准（举例）、「画AI」画固定形象、额度说明（只算成功）、失败会说明原因
- 额度用完的提示追加「想看用法说『画图帮助』」
- 实测文案见会话记录；已部署重启（未升版本号、未动更新源）

### 生图页「分卡片保存」（同日第七轮）

用户反馈：担心别人找不到底部保存按钮，要求每个功能块下面各有保存、且只保存本块内容。

- 四张卡各加「保存本卡片」按钮 + 状态位（用户要求去掉按钮后的说明文字，只留按钮 + `imgsave1~4` 状态）：`imgsave1`(接口与模型) / `imgsave2`(额度与权限) / `imgsave3`(提示词) / `imgsave4`(AI画像)
- 前端新增 `IMG_PART_FIELDS` / `IMG_PART_KEYS` 映射 + `imagePartPayload(part)` + `saveImagePart(part)`；
  只把本卡片字段 POST 给 `/api/image/config`，**不调用 `loadImageCfg()`**，避免把其他卡片未保存的改动冲掉
- 底部保留「保存全部设置」`saveImage()`，由四个 payload 合并而成
- 顺带把 `toggleImage` / `toggleImageSuperUnlimited` 改成点完只更新按钮外观，不再整页重载
- 后端无需改动：`api_image_config` 本来就是「传了哪个 key 才写哪个 key」
- 验证（用 `/tmp/test.db` 副本，不碰生产库）：只存「提示词」卡 → `image_negative` 变、其他 5 项不变；
  只存「额度」卡 → `daily_limit=7`、`image_model` 不变；只存「AI画像」卡 → `self_style` 变、`self_ref` 不变
- 已部署重启（未升版本号、未动更新源）

### 生图接入智谱 + 一键切换供应商（同日第八轮）

需求：想试智谱的生图，且能一键切换。

- 后端 `generate_image` 按 `image_provider` 分流：
  - `zhipu`：`POST {image_zhipu_base}/images/generations`，payload 只有
    `model / prompt / size / quality / watermark_enabled`；`glm-image` 强制 `quality=hd`，其余 `standard`；
    **不发** `num_inference_steps`、`negative_prompt`
  - `siliconflow`：原逻辑不变（`image_size` + `num_inference_steps` + `negative_prompt`）
- 新增设置：`image_provider`（默认 siliconflow）、`image_zhipu_base`（默认 `https://open.bigmodel.cn/api/paas/v4`）、
  `image_api_key_zhipu`；硅基流动仍用 `image_base_url` / `image_api_key`
- AI画像的图生图**固定走硅基流动凭据**（智谱 `/images/generations` 不接受图片输入，不是编辑接口）
- 后台「接口与模型」：顶部 [硅基流动] [智谱] 一键切换按钮；两组 Key/地址分开保存；
  模型下拉按供应商动态生成（`IMG_MODELS`）；切换时自动填该模型默认尺寸/步数并立即保存 provider
- 智谱模型（后台带价格）：`glm-image` ¥0.1/次（1280，文字/海报最强）、`cogview-4` / `cogview-4-250304` ¥0.06/次、
  `cogview-3-flash` 免费。参数依据官方文档 glm-image / cogview-4 页面

**踩坑记录（重要）**：切换按钮第一次上线后点了没反应。
原因是脚本后面原本就有一个 `function fillModelOptions(models)`（供应商页读模型列表用），
我的同名函数被覆盖，传入字符串 `'zhipu'` 时执行 `models.map(...)` 抛 `TypeError`，
切换在发请求前就中断，所以服务端日志里连 POST 都没有。
修复：生图这套函数改名为 `imgFillModels`；`switchImageProvider` 改为幂等（重复点同一家只重绘不发请求）；
前端 JS 用 `node --check` 校验通过。

- 验证（`/tmp/test3.db` 副本，非生产库）：切 zhipu → `image_provider=zhipu`、`image_model=glm-image`、
  `image_size=1280x1280`；`/api/image` 返回 `provider/zhipu_base`；切回 siliconflow 后硅基 Key 仍在
- 拦截请求体验证：智谱分支字段为 `model/size/quality/watermark_enabled`，无步数/负面词；硅基分支仍带步数
- 已部署重启（未升版本号、未动更新源）
- 2026-10-29 13:11 真实出图验证通过（用户已充值 ¥5）：
  - 第一次 Key 只有 32 位（智谱 Key 是 `id.secret` 两段，整串约 65 位含点）→ 三个接口全 401；
    重新粘贴完整 Key（49 位、含点）后通过
  - `cogview-3-flash`（免费，1024x1024）出图正常，约 9 秒
  - `glm-image`（¥0.1，1280x1280）出图正常，约 9 秒，细节/写实感明显强
  - 两张图右下角仍有「AI生成」水印：`watermark_enabled=false` 需在智谱个人中心签免责声明才生效
  - 测试后配置保持 `provider=zhipu / model=glm-image / size=1280x1280`
  - 出图样例：`.preview/zp_glm.jpg`、`.preview/zp_flash.jpg`
- 注意：切换供应商是**全局生效**，所有用户的普通生图都会走当前供应商；AI画像的图生图仍走硅基流动

### 语音：TTS 报错修复 + 接入智谱 GLM-TTS / ASR（2026-10-29 下午）

**用户报错**：后台试听时 `合成失败: 豆包 v3 返回异常 {'code': 45000030, '[resource_id=volc.service_type.10074] requested resource not granted'}`
说明：火山引擎账号没有开通该语音合成资源，不是代码问题。

**顺带发现的坑**：`试听` 用的是数据库里**已保存**的 `voice_tts_provider`，不是下拉框当前值。
用户把下拉改成 Edge 但没保存，点试听照样按库里的豆包去合成 → 看起来像"选了 Edge 还报豆包"。
修复：`/api/voice/preview` 接受 `provider` 参数，前端把当前下拉值带上；`synthesize()` 增加 `provider` 形参。

**接入智谱语音**（用户有智谱 Key）：
- TTS：新增 `synthesize_zhipu()` → `POST {image_zhipu_base}/audio/speech`
  `{model:"glm-tts", input, voice, speed, volume, response_format:"wav"}`，二进制返回；
  兼容 JSON/base64 兜底；Key 默认复用 `image_api_key_zhipu`，也可单独设 `voice_zhipu_key`
- 音色：`voice_zhipu_voice`（默认 `female`；候选 tongtong/xiaochen/chuichui/jam/kazi/douji/luodo）
- 模型：`voice_zhipu_model`（默认 `glm-tts`）
- 后台：语音引擎下拉新增「智谱 GLM-TTS」；切到智谱时显示 Key/音色/模型，隐藏 Edge 音色下拉；切走再显示
- ASR：本来就是 OpenAI 兼容的 `/audio/transcriptions`，智谱可直接用
  `base=https://open.bigmodel.cn/api/paas/v4`、`model=glm-asr-2512`、同一个智谱 Key（页面上已加提示）

**注意**：语音页的 `保存全部语音设置` 才会真正落库；切换引擎后必须先保存再试听（现在试听也会按界面值走了）。

**部署与实测（2026-10-29 15:22）**：
- 备份 `bot.py.bak.20261029-152209`，重启后 active，QQ 正常接收消息
- `voice_tts_provider` 已改为 `edge`（Edge 免费，立即恢复可用）
- Edge-TTS 实测 OK（22464 字节 mp3）
- 智谱 GLM-TTS 实测 OK（270480 字节 wav，单声道 24kHz，5.63 秒）
- 智谱 ASR `glm-asr-2512` 实测 OK：把上面那段 wav 转回文字「你好呀，我是大肥鱼，这是质朴的声音」（"智谱"听成"质朴"，正常误差）
- 服务器 SSH 一度被限流（连续多次连接后 timeout），处理方式：**单次连接 + stdin 传脚本/载荷**，
  避免频繁握手；后续运维尽量合并命令，别连续开多个连接

### 语音引擎「一键切换」（2026-10-29 15:45 已部署）

- 语音页把「语音引擎」下拉改成三个按钮：`[Edge-TTS] [豆包] [智谱 GLM-TTS]`，
  点一下即切并立即保存（`POST /api/voice/config {tts_provider}`），按钮高亮 + 下方显示「当前：xxx」
- 三套参数各自独立、互不覆盖：Edge 用 `voice_tts_voice`；豆包用 `voice_doubao_*`；智谱用 `voice_zhipu_*`
- 切换只控制字段显隐（`paintTtsProvider`），不再整页重载，避免冲掉未保存的输入
- `试听` 现在按界面当前引擎合成（之前按库里的配置，容易看起来"选了 Edge 还报豆包"）
- 部署：备份 `bot.py.bak.20261029-154542`，重启后 active；页面含 `ttspp-zhipu` 按钮
- 代码路径实测：`synthesize(provider="zhipu")` → 239760 字节 wav；`synthesize(provider="edge")` → 12096 字节
- 当前生效：`voice_tts_provider=edge`、TTS 开启、Edge 音色 `zh-CN-XiaoxiaoNeural`；智谱音色未设置时默认 `female`

### SSH 连接不稳的原因（2026-10-29 排查）

- `fail2ban` **未安装/未运行**（`fail2ban-client` 无输出，服务 inactive）
- `sshd` 只有 `UsePAM yes` 显式配置，其余默认；`systemctl restart ssh` 后立即能连
- `iptables` 里有自定义链 `YJ-FIREWALL-INPUT` + ufw 系列链，INPUT 默认策略 `DROP`
- 现象：TCP 22 一直可连，但短时间连续多次 ssh 会卡在 banner 前超时；重启 sshd 或间隔几分钟后恢复
- 应对：**每次操作合并成一次 ssh 会话**（用 stdin 传脚本/载荷，见 `/tmp/deploy2.sh` 那种做法），不要连续开连接

**豆包那套要恢复**：需在火山引擎控制台开通「语音合成」对应资源（`volc.service_type.10074`），
否则永远返回 45000030 requested resource not granted。

### 掉线告警 + 日志降噪（2026-10-29 17:30 已部署）

**背景**：2026-10-29 下午 QQ 被踢下线约 1.5 小时无人知晓。查日志发现 6 小时内 118 条 WARNING 全是同一件事：
`连接异常: Server disconnected，60s 后重连` ×62 + `get_stranger_info 失败` ×42（同一根因）。
NapCat 侧日志 `Login Error, ErrType: 1 ErrCode: 3/1` + 反复「请求刷新二维码」→ 需要重新扫码。

**重要限制**：QQ 掉线时机器人**发不出 QQ 消息**（消息通道就是 NapCat），所以"私聊超管告警"不可行。

**已实现（按用户要求，外部推送已移除）**：
1. 日志降噪：断线首条记 WARNING（带「开始离线」），之后**每 10 分钟**才记一条 `仍未连上（离线约 N 分钟，累计重试 M 次）`；
   重连成功记 `已恢复连接（此前离线约 N 分钟，期间重试 M 次）`
2. 状态接口新增 `offline_minutes` / `need_login`
3. 后台顶部红条（`#offlinebar`）：`need_login` 或离线 ≥2 分钟时显示「已离线 N 分钟，去状态页申请扫码」
4. ~~外部推送（Server酱/Bark/PushPlus）~~ **用户明确不需要，已整套删除**
   （`offline_notify_url`、`offline_watch()`、`push_offline_notice()`、`/api/offline-notify`、状态页卡片全部移除）

**部署验证**：`bot.py.bak.20261029-173046`，重启 active；模拟离线 90 分钟 → `need_login: True`、`offline_minutes: 90`；
降噪与推送代码各就位（`开始离线` 1 处、`仍未连上` 1 处、`offline_watch/push_offline_notice` 5 处）。
当前 QQ 仍处于离线待扫码状态。

### 扫码登录卡死修复（2026-10-29 18:07 已部署）

**现象**：后台「扫码登录」申请二维码很慢，页面显示英文 `QQ Is Logged In`，但账号实际没登录。

**定位**（直接打 NapCat WebUI 接口确认）：
- `POST /api/QQLogin/GetQQLoginInfo` 返回 `{"uin": "", "uid": "", "nick": ""}` —— 全空
- `POST /api/QQLogin/GetQQLoginQrcode` 返回 `{"code": -1, "message": "QQ Is Logined"}`
- `POST /api/QQLogin/RefreshQRcode` 等 **10 秒**后返回「二维码刷新超时」
- 结论：NapCat 内部登录态卡死（自认为已登录、实际会话失效），拒绝出码；原代码先调 Refresh 才慢

**修复**：
1. `api_qr` 改为**先调 `GetQQLoginQrcode`**（毫秒级），失败才兜底 `RefreshQRcode`
2. 识别卡死态：返回 `need_restart: true` + 中文提示「NapCat 登录状态卡死…点重启」
3. `napcat_login_info` 改为按 `uin/uid` 是否为空判断在线，空号不再显示「已登录」（并给出 `stale` 标记）
4. 新增 `POST /api/napcat/restart`（超管）：`sudo -n docker restart napcat`，返回结果；
   二维码页加「重启 NapCat」按钮，重启后自动等 25 秒再申请新码
5. 已实测 `sudo -n docker ps` 可用（ubuntu 有 NOPASSWD），按钮能生效

**现场处置**：先手动 `docker restart napcat` 清掉卡死态 → 立即能拿到 `qrcode` URL；
部署后接口实测 `code:0, 有二维码图片:True`。备份 `bot.py.bak.20261029-180712`。

### 代码体检与修复（2026-10-29 19:38 已部署）

**换了机器人 QQ**：新号 **3446248859**（昵称「心如止水的大肥鱼」）已扫码登录，bridge 已连上。
旧号 1571154120 的 NapCat 配置保留在 `/app/napcat/config/`，想切回还能用。

**静态体检结果**：9902 行；模块级/类内重复定义 0；JS 重复函数 0；`el()` 引用的 id 全部存在；
`<div>` 等标签全平衡；`node --check` 通过；近 2 小时运行时 `Traceback/ERROR` 为 0。

**修掉的问题**：
1. **权限漏洞**：`api_qr`(申请二维码→影响登录态/风控)、`api_voice_preview`(消耗 TTS 费用)、
   `api_voice_config` / `api_rest_config` / `api_seg_config` / `api_bored_config`(改配置) 原来只 `require_auth`，
   viewer 账号也能调 → 统一改 `require_super`
2. **卡住的生图任务**：异常退出会留下 `status='pending'` 行（本次查到 1 条）。
   新增 `Store.image_cleanup_stale(minutes=10)`，启动时自动标 fail，日志「清理了 N 条卡住的生图任务」
3. **提醒补发刷屏**：掉线久了 `reminder_due` 会一次返回全部，原代码 for 循环全发。
   改为「超 24 小时直接作废 + 每轮最多补发 3 条」
4. **模型/供应商不匹配**：切换供应商后残留另一家的模型名会直接报错。
   新增 `IMAGE_SF_MODELS` / `IMAGE_ZHIPU_MODELS` 校验，不匹配自动回退该家默认模型与尺寸
5. **死代码**：`addAdmin()` 引用已删除的 `newuser/newpass/admsg`，调用会 TypeError；已删除（本来也没人调用）

**检测到但未改动（留给后续）**：
- `handle_message` 367 行、`start_admin_server` 174 行，建议拆函数
- 117 处 `except Exception`，部分只 `pass`，关键路径建议补日志
- 无自动化测试；至少可给 `is_self_image` / `build_self_image_prompt` / `version_tuple` 补单测
- `updot` 这个 id 在静态 HTML 与动态重渲染里各出现一次（同一时刻只有一个，无实际影响）

### 代码优化第一轮（2026-10-29 19:42 已部署）

**重构（行为不变，全部有测试覆盖）**
- `handle_message` 367 → 263 行，抽出可测试的纯函数/子流程：
  - `Bridge.parse_segments(ev, self_id)`：OneBot 消息段解析（文本/@/图片/语音/引用）
  - `Bridge.parse_quoted(q)`：被引用消息解析
  - `Bridge.image_command_prompt(text)`：画图指令解析
  - `Bridge.music_command_keyword(text)`：点歌指令解析
  - `Bridge.image_help_requested(text)`：画图帮助识别
  - `Bridge.remember_recent(uid, text)`：最近消息队列
  - `Bridge.handle_super_moderation(...)`：收录表情包 / 拉黑解黑
  - `Bridge.handle_roast(...)`：怼人
  - `Bridge.handle_balance_query(...)`：余额查询
- `start_admin_server` 174 → 21 行：拆出 `role_middleware()`（鉴权中间件）与 `register_admin_routes(app)`（124 条路由）
- 路由条数部署前后都是 **124**，未丢路由

**补日志**：5 处关键静默 `except Exception: pass` 改为 `log.warning`（读记忆去重、私聊超管、语音转码、写 failure.log、更新失败通知）

**单测**：新增 `tests/test_helpers.py`（17 个用例，覆盖自画像判定/模板拼接、画图与点歌指令、帮助识别、消息段解析、引用解析、版本比较）。
在服务器用 venv 运行：`BOT_PY=/opt/qqbot/bridge/bot.py /opt/qqbot/bridge/venv/bin/python3 -m unittest discover -s /opt/qqbot/tests -v` → **17 passed**
（本地无 pip/aiohttp，所以测试在服务器跑；测试文件也会同步到 `/opt/qqbot/tests/`）

**顺手修掉的 bug**：重构中发现并修正一处运算符优先级错误——表情包收录成功但无含义时，消息会拼成
「已收录表情包 ✅\n含义：已收录表情包 ✅（未识别到含义…）」，已改为分支赋值。

**部署验证**：备份 `bot.py.bak.20261029-194246`，服务 active，重启后 10 分钟 `Traceback/ERROR` 为 0。

**注意**：19:42 前后新号 3446248859 又被踢下线（NapCat 登录信息 uin 为空、进入二维码刷新循环），
需要重新扫码。这次登录后不到 2 小时就被踢，佐证「协议客户端 + 境外 IP」的风控问题，不是代码缺陷。

### 发版前完整验收（2026-10-29 19:58）

**单元/逻辑测试**：`tests/test_helpers.py` + `tests/test_bridge_logic.py`，共 **40 个用例全绿**。
服务器运行方式：
```
BOT_PY=/opt/qqbot/bridge/bot.py /opt/qqbot/bridge/venv/bin/python3 -m unittest discover -s /opt/qqbot/tests
```
覆盖：自画像判定与模板、画图/点歌/帮助指令、消息段与引用解析、生图权限/配额/超管不限额、
双供应商请求体（含模型不匹配回退）、配置局部保存、提醒创建/到期/清理、超管与白名单、黑名单、版本比较。

**真实链路自测（发给超管 2844642318）**：
- LLM 调用 2.4s → 返回「消息通道正常，信息已成功接收。」
- 文本消息 `retcode: 0`
- Edge-TTS 语音（23328 字节）`retcode: 0`
- 智谱 glm-image 图片（204411 字节）`retcode: 0`，耗时 **90.6s**（比之前 9s 慢很多，疑似排队/限速）
- 定时提醒：插入 60 秒后的提醒 → 到期自动发出并 `done=1`（`.preview` 无需新增）
- 更新检查：current=3.5.5 / latest=3.5.5 / min=3.5.5 / has_update=False
- 未登录访问 `/api/status|logps|image` → 均 401
- 备份目录最新 `data-20261029-040849.db`

**本轮又修掉的问题**：
1. **提醒空内容**：用户只说「提醒我」时会把 `None` 写进库（历史上留下 1 条脏数据）。
   新增 `ProactiveMessenger.extract_task()`，没说时间也保留任务内容；`reminder_add` 再兜底拒绝空内容；
   历史脏行已清理（删 1 条）。
2. 二维码失效：`RefreshQRcode` 返回字段是 `qrcodeurl`，旧代码读 `qrcode` → 拿不到新码 → 回退 `Get`（永远是旧码）。
   现在兼容两个字段 + 服务端缓存 100 秒 + 强制刷新，实测首次 0.2s 出码、二次命中缓存同码。
3. 发布前自检：`VIEWER_FEATURE=False`、`MEMORY_FEATURE=True`、无密钥/IP/后台路径、与开发版差异仅 1 行、
   试打包干净（无 pyc/db/备份）。

**当前线上**：`3.5.5`（未发版），服务 active，QQ `3446248859` 在线，近 10 分钟 ERROR 0 条，
memories 1219 / slang 164 / stickers 181 / image_jobs 18 / reminders 2 / admins 3。

**仍存在/未解决**：
- QQ 协议登录被腾讯风控（今天多次被踢）→ 需换国内 IP 或走官方 Bot
- 智谱 glm-image 单张 90s（Qwen-Image 之前约 9-30s），高峰期体验差，可考虑默认切回 Qwen 或 CogView
- 无 CI，测试靠手工跑；`handle_message` 仍有 263 行；117 处 `except Exception` 中仍有约 35 处静默

### 语音页修复（2026-10-29 20:04 已部署）

用户反馈三点：试听没反应、保存按钮要拆成两个、豆包是不是不用填 Key。

1. **试听没反应**：三个原因叠加
   - 状态提示 `voicemsg` 原来在页面最底部，点了看不到反馈 → 移到「试听」按钮旁边
   - 智谱 TTS 返回的是 wav，前端一直按 `audio/mpeg` 播放 → 加了 `audio_mime()` 按文件头判断，
     `RIFF/WAVE` → `audio/wav`，`ID3/0xFFFx` → `audio/mpeg`，Ogg 也识别
   - 试听接口现在是超管限定（防烧钱），非超管会 403 → 提示就近显示
   - 实测：Edge `mime=audio/mpeg`（头 `\xff\xf3`）、智谱 `mime=audio/wav`（头 `RIFF`）
2. **保存按钮拆分**：TTS 卡片底部「保存语音合成设置」（`ttssavemsg`）、ASR 卡片底部「保存语音识别设置」
   （`asrmsgsave`），各自只提交本卡片字段（后端 `api_voice_config` 本来就支持局部写入）；
   旧的「保存全部语音设置」卡片已删除。前端导出 `voiceTTSFields()` / `voiceASRFields()` 两个 payload。
3. **Key 归属**：Key 一律存**本机 data.db**，发布包默认全空。别人安装发布版后必须填自己的 Key，
   不会调用你的（这是「每套部署独立」的设计，不是共享）。智谱 TTS 只在**同一部署内**复用生图填的智谱 Key，
   想分开就在「智谱 Key」单独填。豆包 v3 必须填 `X-Api-Key`（字段在切到豆包后显示），留空会报
   「豆包 v3 未配置 X-Api-Key」。

**过程事故（已恢复）**：一次批量替换时锚点取错（切片为空），导致本地 `bot_admin.py` 被插入成 2400 万行。
处理：从服务器已部署的副本 `scp` 回来覆盖（与线上完全一致，md5 相同），再逐条重做改动并加断言校验。
**教训：改文件必须先断言锚点唯一/非空，且改前留一份 /tmp 备份。**

**验证**：41 个测试全绿；服务 active；页面含两个保存按钮。

### 试听体验修复（2026-10-29 20:15 已部署）

用户反馈：合成中提示在上方但没有动画、点试听要等约 8 分钟、生成的语音条放不出声。

**定位**：后端日志显示 `POST /api/voice/preview` **1~2 秒**就返回了 200（340KB/376KB 响应体），
慢和放不出声都发生在浏览器端：旧实现把整段音频 base64 塞进 JSON（智谱 wav 约 180~400KB，
base64 后膨胀 33%），手机端解析/data URL 解码容易失败且卡顿。

**修复**：
1. **改为「小 JSON + 独立音频地址」**：`/api/voice/preview` 只返回
   `{code, mime, bytes, seconds, url}`，音频存内存缓存（最多 6 条、10 分钟过期），
   由 `GET /api/voice/audio?t=<token>` 按正确 `Content-Type` 返回；实测 184080B / `audio/wav` / 200，
   过期 token 返回 404。
2. **合成动画**：新增 CSS `@keyframes tspin` + `.spin` 旋转圈，点试听后按钮置灰，
   提示行显示「⟳ 正在合成语音… Ns」逐秒递增，90 秒无响应自动超时并提示换引擎。
3. **播放器容错**：`p.load()` 后再 play；`<audio onerror>` 直接把失败原因写到提示行；
   成功时显示「已生成（音色｜用时 Xs｜KB）」。

**实测**：preview 1.0s、audio 200 / audio/wav / 184080 字节 / 头 `RIFF`、41 个测试全绿。

### 语音页字段可读性（2026-10-29 20:20 已部署）

用户问「切换声音下面那个输入框是干啥的」——那是**智谱 TTS 的模型名**（`zttsmodel`，默认 `glm-tts`），
原来只有 placeholder 没有标签，看不出含义。

- 智谱字段区改成三行带标签：**智谱 Key** / **音色**（`zttsvoice` 下拉：female、彤彤、小陈…）/ **模型**（`zttsmodel`）
- 模型由文本框改成下拉：`glm-tts`（默认，情感自然）、`cogtts-1`（旧版，账号未开通会报错）；
  若数据库里存的是自定义模型名，前端会自动补一个 option，避免显示空白
- 加了说明「音色 = 说话的人；模型 = 合成引擎版本，一般保持 glm-tts 不用改」
- 验证：41 测试全绿；试听 `code=0 用时=0.8s / 166800B / audio/wav`

### 语音回复与识别修复（2026-10-29 20:23 已部署）

用户反馈：发语音让它唱歌，它回文字，而且听成了「什么课」。

1. **回复不走语音的真因**：`tts_speak()` 不管用哪家 TTS，都拿 `voice_tts_voice`（Edge 的音色名
   `zh-CN-XiaoxiaoNeural`）去合成 → 智谱返回 400 `{"code":"1214","message":"音色不存在"}`
   → 异常被捕获 → 退回文字回复。日志证据：`语音发送失败: 智谱 TTS HTTP 400 ... 音色不存在`
   **修复**：新增 `tts_voice_for_provider()`：智谱取 `voice_zhipu_voice`、豆包 v3 取 `voice_doubao_speaker`、
   豆包 v1 取 `voice_doubao_voice`、Edge 取 `voice_tts_voice`；`tts_speak` 改用它。
   实测 `tts_speak` 返回 True 并构造 `send_msg` record（226320 字节）。
2. **听错内容**：ASR 用的是本地 `faster-whisper base`（中文很弱，把「唱歌」听成「什么课」）。
   **改为智谱 `glm-asr-2512`**：`voice_asr_engine=api`、base `https://open.bigmodel.cn/api/paas/v4`、
   model `glm-asr-2512`；Key 留空时自动复用智谱 Key（生图/合成那把）。
   实测往返：合成「唱个歌听一下」→ 智谱 ASR 原样识别「唱个歌听一下」。
3. 语音页 ASR 卡片新增「一键填入智谱 ASR（推荐）」按钮；42 个测试全绿。
4. 仍不支持「唱歌」这个能力本身（这是功能缺口，不是 bug）：点歌走「播放 歌名」，唱歌需另做。

### 语音「开头滴咚声」处理（2026-10-29 20:32 已部署）

用户反馈每条语音前面有几声「滴咚」。排查：
- 抓智谱 TTS 原始音频做波形/能量分析，前 3 秒能量分布连续、没有独立提示音段；开头不是纯静音
- 服务端日志确认一条回复只发一条语音（`语音已发送` 单条）
- 结论：声音大概率来自 QQ 客户端播放语音时的提示音，或者 wav 语音在手机端解码时的兼容杂音

**处理（把服务端能控的都排除掉）**：新增 `Bridge.prepare_voice()`，发语音前用 ffmpeg
去首尾静音（`silenceremove` 前后各一次）+ 统一转 24k 单声道 48k mp3；`tts_speak` 调用它。
实测：`188880 字节 wav → 22365 字节 mp3`，真实发送 `288720 → 35037 字节`，`tts_speak` 返回 True。
mp3 体积约 wav 的 1/8，QQ 对 mp3 语音兼容性也更好。ffmpeg 失败时自动回退原始音频，不影响发送。

**如果还有滴咚**：那是 QQ 客户端的播放提示音，只能在微信/QQ 设置里关（或换客户端），与本项目无关。

### 智谱 TTS 开头「嘀」声已自动裁剪（2026-10-29 20:39 已部署）

**确认来源**：对智谱 glm-tts 输出做 FFT 分析，开头有 **2~3 组、每组约 0.4~0.5s 的 560Hz 纯音**
（能量恒定 rms≈0.039、窄带占比 >99%），中间夹静音，持续约 1.8 秒后才开始人声。
这是供应商侧的提示音/水印，不是我们加的，也不是 QQ 的提示音。

**处理**：`Bridge.leading_beep_seconds()` + `prepare_voice()`：
1. 逐 20ms 扫描开头 2.2s：静音跳过；纯音（峰值 480~620Hz、窄带 >50%、RMS>0.008）记为提示音；
   一旦遇到有能量但不像纯音的窗口（人声）立即停止
2. 裁到最后一个纯音窗结束再回退 0.12s；**裁后再复查**：之后 0.4s 内若还有 ≥2 个纯音窗，
   每次往后挪 0.1s（最多 0.6s）
3. 之后 ffmpeg 去首尾静音 + 转 24k 单声道 mp3
4. 保护条件：裁切量需在 0.15~2.4s、剩余 ≥0.8s，否则不裁（避免误伤）

**实测**：`4.19s → 2.26s`，处理前后开头主频对比 `560/560/540…` → `0/2580/220…`（不再有 560 纯音）；
体积 `201360 → 13581` 字节；已向超管发送测试语音。
测试：46 个用例全绿（含合成提示音检测、无误裁两个用例）。

**若以后换音色/模型后仍听到嘀声**：说明供应商换了提示音频率，需调整检测频段；或直接切 Edge-TTS（无提示音）。

### 语音情绪：A（改写）+ C（GLM-4-Voice）（2026-10-29 20:47 已部署）

用户觉得智谱 GLM-TTS 没情绪、豆包更有情绪。查官方 OpenAPI：**GLM-TTS 没有 emotion 参数**，
只有 7 个系统音色 + speed/volume，情绪靠文本推断。

**A：情绪化改写（已上线）**
- 新设置 `voice_emotion_rewrite`（0/1），语音页 TTS 卡片加「情绪化语音」开关按钮
- `Bridge.emotion_rewrite()`：合成前用 `llm_complete` 把回复改写成口语短句（保留原意、可加语气词），
  失败/超长自动回退原文；`zvoice` 供应商跳过（它自己有情绪）
- 实测：「好的，我知道了，今天确实有点累。」→「好嘞，我知道了。今天确实有点累啊。」并发语音成功
- 已为用户把开关打开（`voice_emotion_rewrite=1`）

**C：智谱 GLM-4-Voice（已接入，但性质不符）**
- 新增供应商 `zvoice`：`POST /chat/completions` model=`glm-4-voice`；
  **参数很挑**：`system` 必须是字符串，`user.content` 必须是 `[{"type":"text","text":...}]` 数组，
  否则报 1210；返回 `choices[0].message.audio.data` 是 **44.1kHz 单声道 16bit PCM**，需自己包 WAV 头
- 实测能出声（475950 字节 PCM / 5.40s），但用 ASR 回验发现它**不照读**：
  让它读「你好呀，我是大肥鱼，这是端到端语音测试」，它回的是「你好，我是小智，很高兴认识你…」
- 结论：它是**对话式**语音模型，不能当逐字 TTS 用；UI 上已标注「对话式·不照读」并提示改用 GLM-TTS + 情绪化开关
- 若要真情绪又照读：走 **豆包 TTS**（有 emotion/style 参数，需在火山引擎开通资源 10074）

测试：47 个用例全绿（新增 glm-4-voice 载荷结构用例）。

### 情绪化语音：限定智谱 + 情绪风格（2026-10-29 20:56 已部署）

用户反馈：情绪化按钮应该只在选智谱时出现，否则别的用户会误以为不需要配 Key；另外想调情绪风格/音色。

- `emotwrap` 容器包住「情绪化语音」按钮 + 「情绪风格」下拉，`paintTtsProvider()` 里只有
  `TTS_PROVIDER === 'zhipu'` 时显示（Edge / 豆包 / 智谱 Voice 下隐藏）
- 新增设置 `voice_emotion_style`（自然/开心/撒娇/吐槽/难过/生气），映射到改写提示词：
  `Bridge.EMOTION_STYLES` + `emotion_style_hint()`（纯函数，有单测）
- 音色与情绪是两件事：音色仍在智谱字段的「音色」下拉（tongtong/xiaochen/…），情绪只影响改写措辞
- 实测：
  - 开心 → 「哎呀，今天总算把功能都做完啦！还挺顺的呢！」
  - 撒娇 → 「今天终于把功能都做完啦～还挺顺的嘛，哎呀～」
  - 已用「开心」风格发一条语音给超管
- 测试：48 个用例全绿

### 语音页两处 UI 修复（2026-10-29 21:04 已部署）

1. **切到豆包后 v3 的 Key/模型/音色框不显示**（用户截图）
   原因：`toggleDoubaoFields()` 只在「手动改接口版本」时被调用，切换供应商时没重算，
   而 `dbv3`/`dbv1` 初始是 `display:none` → 切到豆包只出现「接口版本」下拉。
   修复：`paintTtsProvider()` 末尾调用 `toggleDoubaoFields()`；函数改为无条件计算
   （`show && v3` / `show && !v3`），避免残留。
2. **情绪化控件位置**：从保存按钮下方移到**上方**（原来可能被折叠看不到）；
   `emotwrap` 仍然只在 `TTS_PROVIDER === 'zhipu'` 时显示。
3. 通用提示里删掉「智谱 TTS 复用生图 Key」这句（对豆包不适用），挪到智谱字段区的说明里。

**过程事故**：再次出现批量替换把 HTML 区块切坏（保存按钮重复、情绪块丢失）。
处理：从服务器部署副本 `scp` 回来覆盖，再用「精确子串 + 断言」重做顺序调整；
已确认恢复后文件与线上一致、48 测试全绿、`node --check` 通过、标签平衡（div 344/344）。

### 情绪 × 音色联动（2026-10-29 21:12 已部署）

用户问「情绪化不能改音色吗」——其实一直可以（音色在智谱字段区、与情绪独立），只是位置分开不明显。

- 情绪区块里新增一个**音色下拉** `emotvoice`（7 个系统音色），与智谱字段区的 `zttsvoice` 双向联动
  （`syncZhipuVoice('emot'|'main')`），保存时取 `emotvoice` 的值
- 智谱 GLM-TTS 只有 7 个系统音色：tongtong / xiaochen / chuichui / jam / kazi / douji / luodo；
  官方另有 `glm-tts-clone`（3 秒样本声音复刻），要做自定义音色需要再接入
- 智谱 Voice（对话式）没有音色参数（会模仿输入语音），所以该供应商下不显示音色选择
- 实测：tongtong 188880 字节、xiaochen 193680 字节，两者输出不同说明音色生效
- 48 个测试全绿

### 语音引擎结构改为「智谱 + 情绪功能」（2026-10-29 21:22 已部署）

用户要求：不要把「智谱 Voice」做成和 Edge/豆包一样的一级按钮，而是放在智谱下面作为一个「情绪功能」开关，
打开后才出现「情绪指令」。

- **移除**一级按钮 `ttspp-zvoice` 和独立的 `zvoicefields` 区块
- 智谱字段区新增：
  - `#emodbtn`「情绪功能：已开启/已关闭」（`voice_emotion_mode`）
  - `#emodinstrwrap` 情绪指令输入 `#zvstyle`（`voice_zvoice_style`），**只在情绪功能开启时显示**
- 后端 `synthesize()`：`provider == "zhipu"` 时按 `voice_emotion_mode` 分流
  - 关：`synthesize_zhipu()` → GLM-TTS（逐字朗读，音色可选）
  - 开：`synthesize_glm4voice()` → glm-4-voice（端到端，按情绪指令说话，**可能微调措辞**）
- `tts_speak()`：端到端模式跳过「情绪化改写」
- 实测：情绪功能=0 → 199440 字节（GLM-TTS）；=1 → 268122 字节（glm-4-voice，日志 `智谱 Voice 合成: 268078 字节 PCM`）
- 49 个测试全绿

**当前语音设置全貌**（后台 → 机器人 → 语音 → 合成卡片）：
- 引擎：Edge-TTS / 豆包 / 智谱 GLM-TTS（三选一）
- 智谱下：Key、音色、模型、**情绪功能开关**、情绪指令（开启后显示）
- 另有「情绪化语音」开关（GLM-TTS 专用：先把回复改写成口语再念）+ 情绪风格下拉

### 语音页去重 + 开关语义（2026-10-29 21:27 已部署）

用户指出两个问题，已修：

1. **两个音色控件**（智谱字段区一个 + 情绪区一个）→ 删除情绪区那个，只保留智谱字段的「音色」；
   同时删掉 `syncZhipuVoice()` 双向联动和 `emotvoice` 相关读写。
2. **情绪风格的开关语义**：保留「情绪风格」下拉，但由「情绪化语音」开关控制：
   - 开启：显示风格下拉（自然/开心/撒娇/吐槽/难过/生气），按选定风格改写后再朗读
   - 关闭：隐藏风格下拉，**不改写**，交给 GLM-TTS 从原文自行判断情绪
   - `setEmotionUI()` 里控制 `#emotstywrap` 的显隐

实测（同一句话）：
- 关闭 → `今天终于把功能都做完了，还挺顺利的。`（原文，模型自行判断）
- 开启/开心 → `今天终于把功能全做完啦，没想到还挺顺的呢！`
- 开启/撒娇 → `今天终于把功能都做完啦～还挺顺利的呀～`

49 个测试全绿。

### glm-4-voice 语速过快修复（2026-10-29 21:31 已部署）

用户反馈「试听声音速度那么快」。当时 `voice_emotion_mode=1`（走 glm-4-voice），
而 `synthesize_glm4voice()` 按**文档示例**把返回的 PCM 包成 **44100Hz** 的 WAV。

排查（同一段 PCM 用不同采样率假设）：
- 时长：16k→14.2s / 24k→9.5s / 32k→7.1s / 44.1k→5.2s（17 字）
- 基频（自相关）：16k→410Hz / **24k→235Hz** / 32k→352Hz / 44.1k→368Hz
- 24kHz 时基频 235Hz 最符合女声（tongtong），说明模型实际输出是 **24kHz**；
  按 44.1k 播放等于加速 1.84 倍、音调也升高 → 就是用户听到的“太快”

**修复**：`w.setframerate()` 改为读设置 `voice_zvoice_rate`（默认 24000）。
修正后 `你好呀，我是大肥鱼，今天天气不错。` = **8.22s / 24000Hz**，已发试听语音。
（若听感偏慢，说明模型这段本身带停顿较多，可用情绪指令加「语速稍快」调节。）

49 个测试全绿。备份 `bot.py.bak.20261029-2131xx`。

### 语音“结尾太突然 / 听起来假”修复（2026-10-29 21:37 已部署）

用户反馈：AI 发的语音结束太快、听起来很假。原因在 `prepare_voice()` 的后处理：
旧版 `silenceremove` 把**尾部静音全部裁掉**，且没有淡出 → 语音像被硬切；
48kbps 单声道 + 硬切也加重“不自然”。

**重写 `prepare_voice()` + 新增 `polish_pcm()`**：
- 尾部不再全裁：保留到最后一个有声样本，再补 **0.12s 静音**（`polish_pcm` 里做）
- 开头 10ms 淡入、结尾 40ms 淡出，消除“咔哒”
- 码率 **48k → 64k**
- 开头提示音回退余量 0.12s → 0.05s（减少把首字吃掉）

**采样率复核**（用户仍疑“假/快”）：同句「你好呀，我是大肥鱼，今天天气不错。」
- GLM-TTS（已知 24k）：5.27s
- glm-4-voice 按 24k 包：6.38s（合理，情绪化会多停顿）
- 若按 44.1k 包：3.47s（4.9 字/秒，明显偏快）
→ 确认 **24kHz** 是对的。

**过程事故**：重写 `prepare_voice()` 时用「prepare_voice → tts_speak」做切片，
把夹在中间的 `EMOTION_STYLES` / `emotion_style_hint` / `emotion_rewrite` 一起删掉了；
从服务器备份 `bot.py.bak.20261029-213455` 精确恢复并把块插回正确位置，50 个测试全绿。
**教训：切片式替换前必须先确认区间内只有目标方法。**

已向超管发送两条对比语音：A=GLM-TTS+开心改写（逐字、自然），B=端到端（情绪更强、可能改措辞）。

### 真实发送通道与 A/B 对比语音（2026-10-29 21:42）

**重要教训**：之前几次“发送测试语音”用的是**假 WebSocket**（只打印不真正发），
所以用户其实收不到——必须连真实的 OneBot WS（`ws://127.0.0.1:3001`，access_token 为空）
并用 `echo` + future 等 `retcode` 才算真发。本次已按真实通道发送，两条都 `retcode=0`。

发送脚本要点（可复用）：
```python
ws = await session.ws_connect("ws://127.0.0.1:3001")
# 后台 reader 把 echo 对应的响应塞进 futures
await ws.send_str(json.dumps({"action":"send_msg","params":{...},"echo":echo}))
# 等 futures[echo]
```

**A/B 对比**（同一句「今天终于把功能都做完了，还挺顺利的。」）：
- A：GLM-TTS + 情绪化改写(开心) → 21 字改写「哎呀，今天总算把功能全搞定啦，还挺顺的呢！」→ 30957 字节
- B：智谱 Voice 端到端（情绪指令“语速稍快一点”）→ 49389 字节

**另修**：`emotion_rewrite` 现在会校验改写结果长度（≥原文 50%），过短则回退原文，
避免模型偶发只吐半句导致语音内容缺失。

### 语音方案定为 B（2026-10-29 21:44）

用户对比后选 B（智谱 Voice 端到端），评价「更像真人」。已把线上配置固定为：

| 设置 | 值 |
|---|---|
| `voice_tts_provider` | `zhipu` |
| `voice_emotion_mode` | `1`（走 glm-4-voice 端到端） |
| `voice_emotion_rewrite` | `0`（端到端模式本来就跳过改写） |
| `voice_zvoice_style` | `用自然、有情绪起伏的语气说话，语速稍快一点。` |
| `voice_zhipu_voice` | `tongtong`（端到端模型不吃这个参数，保留而已） |

已发确认语音（`retcode=0`，36909 字节）。

**注意**：B 模式可能微调措辞（不逐字）；若哪天文案必须精确，关闭「情绪功能」即回到 A（GLM-TTS 逐字）。
另外 B 模式下当前是「只发语音、不发文字」，如果希望语音+文字一起发，需要另加开关。

### 语音模块精简：只留智谱端到端（2026-10-29 21:50 已部署）

用户要求「只保留现在这套语音配置，其他语音功能直接删掉」。已按“直接删代码”执行：

**删掉的后端**：`synthesize_zhipu`（GLM-TTS）、`synthesize_doubao` / `synthesize_doubao_v3`（豆包）、
`tts_voice_for_provider`、`emotion_rewrite`、`EMOTION_STYLES`、`emotion_style_hint`，
以及 `synthesize()` 里的供应商分支（现在只调 `synthesize_glm4voice`）。

**删掉的界面**：语音引擎按钮组（Edge/豆包/智谱/智谱Voice）、豆包 v1/v3 字段区、智谱 GLM-TTS 字段区、
音色下拉、模型下拉、「情绪功能」开关、「情绪化语音」开关、情绪风格下拉、以及对应的 JS
（`paintTtsProvider`/`switchTtsProvider`/`toggleDoubaoFields`/`currentSpeaker`/`toggleSpeakerCustom`/
`paintEmotionMode`/`toggleEmotionMode`/`setEmotionUI`/`toggleEmotionRewrite`）。

**保留的**：
- TTS：智谱 Key（留空复用生图 Key）、情绪指令（默认“用自然、有情绪起伏的语气说话，语速稍快一点。”）、
  TTS 开关、模式（跟随语音/全部回复）、试听（动画+直链播放）、保存
- ASR：开关、引擎（本地/API）、一键填入智谱 ASR、识别 Key、保存
- 后处理：去开头提示音、保留尾音、淡入淡出、24k/64k mp3

**API 精简**：`api_voice_get` 只返回 tts_enabled/tts_mode/zvoice_*/asr_*；
`api_voice_preview` 不再接受 provider/voice；`api_voice_config` 只接受
tts_enabled/tts_mode/zvoice_key/zvoice_style/asr_*。

**验证**：47 个测试全绿；页面里 `Edge-TTS`/`豆包`/`智谱 GLM-TTS`/`情绪功能`/`情绪化语音` 均 0 处；
真实发送语音 `retcode=0`（33453 字节）。

### 超管文字回语音 + AI 唱几句（2026-10-29 22:00 已部署）

1. **新模式 `super`**（下拉「仅超管文字也回语音」）：语义是「跟随语音 + 超管发文字也回语音」，
   普通用户仍只有发语音才回语音。判断抽成 `Bridge.voice_wanted(had_voice, user_id, user_text)`：
   `always` → 全回；`voice_in` → 只有发语音；`super` → 发语音 **或** 超管文字；任何模式含「发语音」也回。
   线上已设为 `voice_tts_mode=super`。
2. **唱歌 `handle_sing()`**：`sing_request()` 解析「唱一首《X》/ 唱个歌 / 唱两句 / 来一首 X」，
   取书名号或去掉触发词后的歌名（最多 12 字）；由 LLM 生成**2~4 句**（高潮/副歌，不整首），
   TTS 开则直接发语音，否则发文字 `🎵 《X》：歌词`。实测《孤勇者》发语音成功（105645 字节，29 字歌词）。
3. 测试：50 个用例全绿（新增 `sing_request` 解析 7 例、`voice_wanted` 各模式 6 例）。

**过程事故**：一次部署时把 gzip 二进制直接写进 bot.py，服务进 activating；
用 `.bak.20261029-215910` 恢复后按 `base64 -d | gunzip` 正确流程重发，50 测试全绿。

### 超管回语音改为独立开关（2026-10-29 22:04 已部署）

用户指出：把「超管文字也回语音」做成**模式选项**会和「跟随语音/全部回复」互斥，影响正常使用。
改成**独立开关**：

- 模式下拉回到两项：`跟随语音` / `全部回复`
- 新增按钮 `#suptextbtn`「超管文字也回语音：已开启/已关闭」（设置 `voice_super_text`），
  可与两种模式**叠加**
- `voice_wanted()`：`always` → 全回；`voice_in` → 发语音才回；
  `voice_super_text=1` 且发送者是超管 → 文字也回；任何模式含「发语音」也回
- API：`api_voice_get` 多返回 `super_text`；`api_voice_config` 接受 `super_text`，
  且 `tts_mode` 只接受 `voice_in`/`always`

线上配置：`voice_tts_mode=voice_in`、`voice_super_text=1`（即：普通用户发语音才回，超管发文字也回）。
测试 50 个全绿。

### 语音结尾“半句”修复（2026-10-29 22:13 已部署）

用户反馈最后 1~2 个字像只说了一半。原因在 `polish_pcm()`：
- 只在最后一个有声样本后保留 **0.15s**，且**淡出 40ms 作用在真实语音上** → 收尾被削
- 末尾补静音仅 0.12s，mp3 编码器可能丢最后一帧

**改为**：
- 最后有声样本后保留 **0.30s**（保留字尾自然衰减）
- 淡入 10ms 只作用于开头；**淡出 30ms 只作用于补出来的静音段**，不再削语音
- 末尾补 **0.25s** 静音，保证编码器刷出最后几帧
- 静音判定阈值 300 → 200（更晚才认为结束）

实测末段 RMS：`0.18, 0.20, 0.07, 0.15, 0.16, 0.0002, 0, 0`（语音后接干净静音，不再在字中间切断）。
已发试听语音（`retcode=0`，38445 字节）。50 个测试全绿。

**若仍觉得收尾仓促**：那是端到端模型自己收尾，可在「情绪指令」里加一句“每句话都完整说完，不要突然停”。

### 结尾停顿加长（2026-10-29 22:15 已部署）

用户说「加油」说完了，但希望后面再多零点几秒，更拟人。

- `polish_pcm()` 末尾补静音 **0.25s → 0.50s**（语音自然衰减 0.30s 保留不变）
- 实测：处理后 7.63s，末尾 0.1/0.25/0.4/0.5 秒内最大幅度均为 0.0000（干净静音）
- 已发试听语音（`retcode=0`，61101 字节）；50 个测试全绿

如需再长（0.7~1.0s），改一个数字即可。

### 情绪指令加入“说完再停”（2026-10-29 22:18 已部署）

用户同意后，把默认情绪指令改为：
`用自然、有情绪起伏的语气说话，语速稍快一点。每句话都完整说完，不要突然停下。`

- 代码里 6 处默认值/占位符统一替换（`build_glm4voice_payload` 兜底、api 默认值、输入框 placeholder 等）
- 线上 `voice_zvoice_style` 已更新为同一条
- 已发验证语音（`retcode=0`，28077 字节）；50 个测试全绿

### 语音注入人设/记忆/黑话（2026-10-29 22:22 已部署）

用户反馈：语音回复感觉没有用上记忆模式和黑话模式。

**原因**：端到端模型 `glm-4-voice` 的调用把「待朗读的回复」放在 user 消息里，system 只有情绪指令，
模型会把这句当成「对话输入」→ 自己重新组织语言，注入到文字回复里的记忆/黑话细节被洗掉。

**修复**：
- 新增 `Bridge.voice_context(memory_text, slang_text)`：拼装 人设(`persona_text`) + 黑话 + 记忆
- `build_glm4voice_payload(text, style, context="")`：system 里依次放
  `【你的设定与记忆】…`、`请把用户给你的这句话用上面的口吻自然说出来…不要回答它、不要加新内容`、`【语气要求】…`
- 调用链透传：`handle_message` 的语音回复传 `voice_context(mem_text, slang_text)`；
  `handle_sing` 传 `voice_context()`（只带人设）
- 实测：上下文 1641 字符（含人设），合成 665902 字节 PCM → 102189 字节 mp3，已发试听（`retcode=0`）
- 测试 51 个全绿（新增「上下文注入到 system」用例）

### 唱歌请求无响应的 bug（2026-10-29 22:25 已修复）

用户反馈「给我唱首歌听一下」AI 不回语音。日志：

```
handle_message → handle_sing(ws, ev, mtype, user_id, sing_song)   # ✗ 参数顺序错
handle_sing → tts_speak(ws, mtype, ev, ...)                       # ev 收到的是字符串
WARNING 语音发送失败: 'str' object has no attribute 'get'
ERROR 后台任务失败: handle_message
```

**原因**：`handle_sing` 的签名是 `(ws, mtype, ev, user_id, song)`，调用时把 `ev` 和 `mtype`
写反了 → `tts_speak` 里 `ev.get(...)` 拿到字符串 → 异常 → 语音没发出去，文字兜底也崩。

**修复**：调用改为 `self.handle_sing(ws, mtype, ev, user_id, sing_song)`。
**回归测试**：新增 `TestHandleSingArgs.test_args_order`（走 handle_sing，断言 ev 仍是 dict、有文字兜底）。

**端到端验证**（模拟真实消息）：
`handle_message` 收到「给我唱首歌听一下」→ 生成歌词 27 字 → 语音已发送 60525 字节。
52 个测试全绿。

### 唱歌把歌词当“诗”点评 + 可追溯（2026-10-29 22:28 已部署）

用户截图：机器人发了一条 7" 语音后，又发文字「哦，这诗好短，不过很有意境，你觉得这首诗是在表达什么感情呀？」。

**排查**：该时段（22:25）服务端日志里**没有任何收到消息的记录**，说明这条点评不是正常消息循环产生的，
而是测试时注入的模拟消息触发的流程留下的；那轮生成的歌词偏长、像一首诗，模型就顺着“点评诗”往下说了。

**处理**：
1. `handle_sing()` 歌词强制收敛：最多 **4 行 / 80 字**（超了截断）
2. 歌词提示词收紧：`每行不超过 12 个字，最多 4 行，不要解释、不要评论`
3. `send()` 增加外发日志 `发送文字[mtype]: 前60字`，以后机器人说的每句话都能在
   `journalctl -u qqbot-bridge` 里追溯来源
4. 52 个测试全绿

### 乱答/听不懂的疑似自回环（2026-10-29 22:36 已部署防护）

用户反馈：机器人答非所问（对它自己发的内容做点评），怀疑读不到用户文字。

**日志证据**：22:31:46 服务端只记录了 `唱歌：随便唱两句（35 字）` + `语音已发送`，
之后那句文字**没有 `发送文字` 日志**（send() 已在 22:28 加了日志）→ 说明那条文字不是走 normal 流程发的。
结合前一次「这诗好短」（正好是对上一条语音歌词的点评），判断为**自回环**：
机器人把自己发出去的语音又当成用户消息收回来，ASR 转写后当作用户输入 → 对着自己的话乱答。

**已加防护**：
1. `remember_outgoing()` / `looks_like_self_echo()`：发出文字/语音内容都记入最近 40 条；
   收到消息若与 180 秒内发出的内容相似度 ≥ 0.8，直接忽略并记日志 `忽略疑似自回环消息`
2. 「收到」日志提前到分支判断之前（`收到[private] xxx: '...' (语音=False, 图片=0)`），
   这样唱歌、问答、被过滤的消息都能看到到底收到了什么
3. `notify_super` 也加日志
4. 53 个测试全绿（新增自回环用例）

**待验证**：请用户再发一条消息，看日志里 `收到[...]` 的实际内容判断是否还有问题。

### 语音“答非所问”真因：端到端模型不照读（2026-10-29 22:43 已修复）

**两个关键结论**：

1. **用户看到的“文字”其实是 QQ 的语音自动转写字幕，不是机器人发的消息。**
   用 `get_group_msg_history` / `get_friend_msg_history` 核对：机器人那一轮只发了 `[语音]`（和 `[图片]`），
   **没有任何文字消息**。所以“读不到用户文字”不成立——日志 `收到[private] ... '今天天气不错，1+1=几啊？'`
   说明文字是正常收到的。

2. **glm-4-voice 不照读，会自己编内容。** 同一句输入做对照：
   - LLM 生成文本：`2 啊，这问题也太基础了吧😂 天气好你倒是出去走走啊`
   - 语音实际内容（ASR 回验）：`嘿，我也想出去走走，但一直呆在家里也没法帮你看天气…`
   换回 GLM-TTS 后：文本 `1+1=2啊，这跟天气有啥关系哈哈`
   → 语音 `一加一等于二啊，这跟天气有啥关系？哈哈`（一致）

**修复**：
- 从备份恢复 `synthesize_zhipu()`（GLM-TTS 逐字朗读）
- `synthesize()` 按设置 `voice_engine` 分流：`tts`（默认，准确）/ `voice`（端到端，可能改措辞）
- 语音页新增「合成方式」和「音色」两个下拉；`api_voice_get/config` 增加 `engine`、`voice_name`
- 线上默认：`voice_engine=tts`、`voice_zhipu_voice=tongtong`
- 53 个测试全绿；已发试听语音（`retcode=0`）

### 全部功能提示词审计（2026-10-29 22:50 已部署）

逐个核对了 12 处 LLM 提示词，修掉 5 个会出问题的点：

| 提示词 | 位置 | 问题 | 处理 |
|---|---|---|---|
| 提醒文案 | `ProactiveMessenger.compose` | 提示词写“不超 30 字”但没兜底，模型可能超长 | 强制压缩空白、截断 30 字、去尾部标点 |
| 生图改写 | `enhance_image_prompt` | 写“最多 150 字”没截断；模型可能带「画面描述：」前缀 | 截断 150 字、去标签前缀、压缩空白 |
| 记忆提取（普通级） | `extract_memories` | 禁记项比高级版少了“验证码” | 两级统一为 手机号/密码/身份证/住址/银行卡/验证码 |
| 黑话收录 | `slang_learn` | 可能把整句话当黑话收录 | 追加“词条必须 2~8 个字，禁收完整句子/标点/表情” |
| 表情包识别 | `describe_sticker` | 返回长度不设限，可能几百字 | 压缩空白 + 截断 60 字 |

其余检查通过（未改动）：主 persona 基础提示词、唤醒提示词、群聊回复判定、表情包挑选、怼人三档（均自带底线）、
唱歌歌词、语音上下文注入、自画像图生图模板、记忆注入过滤噪声词。

**实测**：提醒文案 9 字「老大，记得买牛奶啊」；生图提示词 68 字（主体/动作/环境/光线/镜头齐全）。
53 个测试全绿。

### 🚀 3.6.0 已发布（2026-10-29 22:54）

**发布产物**
| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.6.0"`（开发版与发布版一致；发布版 `VIEWER_FEATURE=False`、`MEMORY_FEATURE=True`） |
| 发布版 bot.py | 526822 字节，sha256 `4ce4f3dd…f8532b45` |
| 更新源 | `https://xrzs.cloud/updates/latest.json` → 3.6.0，`min_version: ""`（未强制） |
| 安装包 | `https://xrzs.cloud/dl/qqbot-latest.tar.gz.enc`，sha256 `4c68c32f…e115c06`，133136 字节 |
| 版本化包 | `qqbot-3.6.0.tar.gz.enc` 已生成 |
| 服务器 | 已换成 3.6.0 发布版并重启，`app_version=3.6.0`；备份 `bot.py.bak.<时间戳>` |

**验证**
- 更新检查（模拟旧客户端 3.5.5）：`current=3.5.5 latest=3.6.0 has_update=True force=False`
- 全量测试 53 项全绿
- 公网：`latest.json` 200、`updates/bot.py` 200（526822B）、`dl 包` 200（133136B）、`install.sh` 200，下载包 sha 与元数据一致

**3.6.0 说明（更新源 notes 同步）**：语音双引擎（GLM-TTS 逐字 / glm-4-voice 情感）、去提示音+尾音停顿、
人设/记忆/黑话注入语音、超管文字回语音开关、唱歌几句、智谱 ASR、生图正式版、提示词兜底、十余处 bug 修复。

### 初始账号角色修复（2026-10-29 23:23，已同步 3.6.0 发布文件与安装包）

**检查结论：原来确实有 bug。**
- `admins` 表的 `role` 列默认值是 `'admin'`（普通管理员），而首次启动创建账号用的是 `add_admin()`，
  它不写 role → 新部署的初始账号**不是超级管理员**。
- 旧代码里只有一条 `UPDATE admins SET role='super' WHERE username IN ('admin','心如止水')`，
  而且它在建号**之前**执行 → 首次启动的 `admin` 账号要等**第二次重启**才会变成超管；
  若用户在 `config.yaml` 里自定义了 `default_admin.username`（不是 admin/心如止水），则永远不是超管。

**修复**：
1. `Bridge.ensure_default_admin()`：首次启动直接用 `create_account(..., "super")` 建号；
   已存在同名账号时兜底 `add_admin` + `set_account_role_by_name(..., "super")`
2. 数据库初始化保底：**只要库里一个 super 都没有，就把最早创建的账号提升为 super**
3. 新增 `Store.set_account_role_by_name()`

**验证**：
- 全新库模拟（`/tmp/fresh_test.db` + `default_admin: demo/demo123`）→ 账号 `demo`，角色 **super**，日志「已创建默认超级管理员 demo」
- 56 个测试全绿（新增：首个账号必为超管、`ensure_default_admin`、按名设角色）
- 3.6.0 发布文件与安装包已用热修版重新上传：bot.py sha `6dd9e06a…`，包 sha `87e27e07…`（133456 字节）
- 已修复一次部署事故：方法误插到 `Store` 类导致服务启动失败，已移入 `Bridge` 并重启验证（23:23 后 0 错误）

**注意**：版本号仍是 3.6.0，已经更新过 3.6.0 的用户不会再收到这次热修，需要发 3.6.1 才能推送给他们。

### 🚀 3.6.1 已发布（2026-10-29 23:25）

用户要求：升 3.6.1 把初始超管修复推给已装 3.6.0 的用户，但**更新说明保持 3.6.0 原文，不加修复说明**。

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.6.1"`（开发版与发布版一致，`VIEWER_FEATURE=False`、`MEMORY_FEATURE=True`） |
| 发布版 bot.py | 527997 字节，sha256 `70c4a509…e7474128` |
| 更新源 | `latest.json` version=3.6.1，**notes 与 3.6.0 完全相同（不含“热修”字样）**，`min_version: ""` |
| 安装包 | `qqbot-latest.tar.gz.enc` sha256 `78b56169…311e7a9f`，133456 字节；版本化包 `qqbot-3.6.1.tar.gz.enc` 已生成 |
| 服务器 | 已部署 3.6.1 并重启，`app_version=3.6.1`；备份 `bot.py.bak.<时间戳>` |

**验证**：56 个测试全绿；更新源/安装包/install.sh 均 200；服务 active；近 5 分钟 ERROR 0。
**说明**：3.6.1 内容 = 3.6.0 + 初始账号超管修复；更新说明刻意沿用 3.6.0 文案。

### 表情包关键词截断修复（2026-10-29 23:52，已同步 3.6.1 发布文件/安装包）

用户反馈：后台关键词设了「保存表情包」，@机器人「保存表情包 思考」后，含义变成「包 思考」。

**原因**：`handle_super_moderation()` 用 `next(w for w in cap_kws if w in user_text)` 取**第一个**命中词；
默认关键词列表里有「存表情」，而「保存表情包」包含「存表情」→ 先命中短词，
`user_text.split("存表情",1)[1]` 剩「包 思考」，于是含义多了个「包」。

**修复**：新增 `Bridge.match_capture_keyword()`。第一版按「取最长命中」修，
用户指出含义本身也可能很长、可能包含别的关键词 → 改为 **位置优先、长度次之**：
取在消息里出现位置最靠前的命中词，同位置再取更长的（命令词正常都在 @ 之后、含义之前）。
`handle_super_moderation()` 改用它。
**验证**：`保存表情包 思考` → 命中「保存表情包」含义「思考」；`收录 这是一个很长的思考过程` → 命中「收录」含义完整；
`存表情 生气` → 命中「存表情」含义「生气」。57 个测试全绿。
3.6.1 发布文件（sha `38e55c7e…`）与安装包（sha `4fae8d93…`，133728 字节）已覆盖更新，版本号与说明均未变。

### 私聊末世文字冒险（2026-10-30 00:32，3.6.1 热修部署）

依据 `赤月2039-末世提示词.md` 实现**私聊版**（群聊版后续再做）：

- **存档表**：`game_saves(qq PK, active, state, updated_at)`；`state` 里存最近 40 条对话历史
- **提示词**：`GAME_PROMPT`（世界观/固定结构/精简卡/规则/800 字限制），见 PROMPTS.md 第 16 条
- **命令**（仅私聊）：`开始末世`（也可「开始游戏/末世生存/赤月2039」）、`存档`、`继续游戏`/`读档`/`继续`、
  `退出游戏`、`重置存档`
- **路由**：`handle_message` 在唱歌判断之前调用 `handle_game`，命中返回 True 直接结束；
  游戏模式不注入记忆/黑话、不发语音、不进群聊
- **实测**：模拟私聊「开始末世」→ 建档卡 439 字正常发出，存档 active=1、历史 2 条
- **测试**：60 个用例全绿（新增开局/命令流转/重置/群聊不启用）

**注意**：这次是 3.6.1 同版本热修，未升版本；更新源与安装包已覆盖（含本功能）。

### 剧本杀系统（后台聊天子标签 + 远程剧本分发）（2026-10-30 01:00，3.6.1 热修部署）

**数据表**：`scripts`（剧本库，只存在自己服务器）、`players`（QQ→剧本+开关）、
`runs`（每开一次一局，run_no 即“第几次玩”）、`messages`（每局每条对话）。
旧 `game_saves` 保留但不再使用。

**后台**（聊天 → 剧本杀）：
- 添加玩家：填 QQ + 选剧本 → 保存后**主动私聊**该玩家；只填 QQ 不选剧本时，玩家发消息会被告知
  “联系超级管理员 QQ xxx 添加剧本”
- 玩家列表：显示脚本/第几次/回合数/局数/更新时间，可开关、重开（新建一局并推送建档卡）、
  看历史局、删除
- 历史局：可切到任意一局继续；可查看该局完整对话
- 剧本库：粘贴提示词上传（≥50 字），可启用/停用/删除
- 剧本接口：`game_api_url`（用户部署填你的地址）、`game_api_token`（拉取 token）、
  `game_dist_token`（你这台服务器生成，发给用户）
- 统计：剧本数 / 玩家数 / 总局数 / 对话条数

**远程分发（防窃取）**：
- `GET /api/scripts/public/list?token=`、`GET /api/scripts/public/get/<id>?token=`；token 不对直接 403
- 用户部署拉取后**只内存缓存 10 分钟**，不写数据库、不落盘；后台不展示剧本正文
- 每次下发在提示词中间插入**零宽水印**（token 的 sha256 编码成 U+200B/U+200C），泄露可溯源
- 说明：客户端要运行必须拿到提示词进内存，无法 100% 防止逆向；以上保证“不能顺手导出/复制”和“可追责”

**玩家侧命令**：`开始`、`我的存档`/`存档`/`进度`、`玩第N次`、`退出游戏`、`继续游戏`

**验证**：63 个测试全绿；真实私聊「开始」→ 建档卡已发、`runs` 1 局、`messages` 2 条；
分发接口 list/get 正常、错误 token 403、水印存在。

### 后台 JS 故障修复 + 独立剧本库站点（2026-10-30 01:10）

**故障**：用户反馈管理后台“加载不出来数据”。排查：页面返回 200，但浏览器没有发出任何 API 请求
→ 前端脚本整段未执行。从线上页面提取 JS 用 `node --check` 发现两处转义错误：
1. `onclick="gameToggle(\'QQ\',...)"` 在 Python 三引号里 `\'` 被还原成 `'`，JS 语法错；
   → 改用 HTML 实体 `&apos;` 拼 onclick
2. `.replace(/\n/g,...)` 被 Python 还原成真换行，正则断裂；
   → 改用 `split(String.fromCharCode(10)).join('<br>')`
修复后从线上页面重新提取 JS 校验通过（121435 字符，node --check OK）。

**独立剧本库站点**（与机器人后台分离）：
- 代码：`/opt/scripts_web/app.py`（aiohttp，端口 8091）
- 服务：`fishpond-scripts.service`（环境变量 `SCRIPT_ADMIN_PASS`、`SCRIPT_DIST_TOKEN`）
- 路由：Caddy `handle_path /scripts/*` → 127.0.0.1:8091（注意用 handle_path 才能剥前缀）
- 地址：`https://xrzs.cloud/scripts/`
- 功能：登录、剧本列表、上传（≥50 字）、启用/停用、删除、统计（读机器人库的 runs/players/messages 总数）
- 分发：`/api/scripts/public/list?token=`、`/api/scripts/public/get/<id>?token=`，token 错误 403，
  下发内容带零宽水印
- **按需求把剧本从机器人库里迁到独立站并删除本机副本**，机器人改为远程拉取：
  `game_api_url=https://xrzs.cloud/scripts`、`game_api_token=<分发 token>`；
  实测远程列表返回「赤月2039」、解析提示词 1170 字且含水印
- 机器人后台的「剧本杀」页现在只负责玩家/存档/对话；剧本下拉来自独立站

**未做**：独立站暂不支持“编辑剧本”（只能删了重传）和“改密码页面”（改 systemd 环境变量后 restart）。

### 独立站账号登录 + 用户端隐藏剧本库（2026-10-30 01:20）

1. **独立剧本库改成账号+密码**：`SCRIPT_ADMIN_USER`（默认 admin）+ `SCRIPT_ADMIN_PASS`，
   登录页两个输入框；实测 正确 302、错账号 200、错密码 200。
2. **机器人后台剧本杀的「剧本库（仅本机）」和「剧本接口」两块整块删除**（HTML + 相关 JS 函数），
   页面只剩：添加玩家 / 玩家列表 / 历史局 / 对话 / 统计。
3. **新增发布开关 `SCRIPT_HUB`**（dev=True / 发布版 False，由 make_release 强制并校验）：
   - `api_game_script_save` / `api_game_script_manage` / `api_game_settings` → 403
   - `api_scripts_public_list/get` → 不对外（401/404）
   - overview 不再吐 `dist_token`
   这样即使打包出去，用户部署也没有剧本上传/分发能力。

**实测**：线上页面 `剧本库（仅本机）`、`剧本接口` 残留 0；页面 JS `node --check` 通过；
上传接口 403、分发接口 401；63 个测试全绿；机器人仍能从 `https://xrzs.cloud/scripts` 拉到
「赤月2039」（1170 字，含水印）。

### 剧本库登录对接 AI 控制台（2026-10-30 01:28）

- 独立站登录不再用独立密码，改为**校验 AI 控制台的 `admins` 表**（同一套 PBKDF2 哈希）：
  用 `gameadmin` / 自己的超管账号密码即可登录剧本库，改密码在 AI 后台改，两边同时生效。
- **SSO**：登录 AI 控制台后浏览器带着 `qb_sid`，直接打开 `https://xrzs.cloud/scripts/dashboard`
  会调用内部 `/api/status` 校验会话并放行（实测 200）；AI 后台退出后该会话失效。
- 环境变量 `SCRIPT_ADMIN_USER/PASS` 保留为兜底（AI 后台库不可读时仍能进）。
- 实测：AI 后台账号 302 成功、错密码/错账号 200 提示、SSO 直开 dashboard 200。

### 语音 Key 401 排查 + 「测试 Key」按钮（2026-10-30 01:30）

用户反馈：输入智谱 Key `ad62d4…bqVPu` 后提示 `401 令牌已过期或验证不正确`。

**排查**：直接拿这把 Key 打智谱接口——
- GLM-TTS（/audio/speech）：**200**，122640 字节音频
- glm-4-voice（/chat/completions）：**200**，216538 字节音频
→ Key 本身完全有效。401 是因为当时保存/使用的是**另一把旧 Key**（截图里「已保存 c210e****33ca」），
新 Key 没保存成功就点了试听。

**改进**：新增 `POST /api/voice/keytest`（超管）+ 语音页「测试 Key」按钮：
- 不保存，直接用输入框里的 Key 打一次最小请求
- 按当前「合成方式」分别测 glm-tts 或 glm-4-voice
- 返回 `✅ Key 可用（N 字节音频）` 或 `❌ HTTP 401: …`
实测：用户 Key 两种方式均 200；`bad.key` 返回 `401 身份验证失败`。63 个测试全绿。

### 语音 Key 保存不上（2026-10-30 01:40，未升版本）

用户定位：语音页保存 Key 时被“生图那边的”影响，保存不上，一直用旧 Key → 401。

**根因**：语音页的 Key 字段历经重构（`zhipu_key` → `zvoice_key`），
旧页面缓存仍发旧字段名，服务端已不识别 → 静默不保存；页面又显示生图 Key 的掩码，
所以看起来“保存了但没用”。生图 Key 与语音 Key 必须彻底分开。

**修复**：
1. 服务端 `api_voice_config` 同时接受 `zvoice_key` / `zhipu_key` / `voice_key`，
   统一写入 `voice_zvoice_key`（不碰 `image_api_key_zhipu`）
2. 保存后返回 `voice_key_masked`，前端把输入框占位符更新为 `已保存：ad62d****qVPu`
3. 输入框提示改为「语音专用 Key（留空则临时复用生图 Key）」

**实测**：新字段、旧字段都能保存；`voice_zvoice_key` 49 字（ad62d4…qVPu），
`image_api_key_zhipu` 仍是原值（d30b88…f1sG）未被改写；63 个测试全绿。
**按要求先不发版本**（仍 3.6.1，仅服务器实时代码）。

### 开头提示音检测放宽（2026-10-30 01:45，未升版本）

用户反馈：用户部署的选项和自己一样（代码已新），但语音开头仍有「滴咚」，且声音像没调过。

**原因**：旧检测只认 **480~620Hz、窄带占比 >50%** 的纯音（针对智谱 560Hz）。
不同音色/模型产出的提示音频段可能不同（900Hz、1200Hz 等），旧逻辑直接漏检 → 听起来“没处理过”。

**修复**：`leading_beep_seconds()` 判定放宽为 **峰值 300~1400Hz、窄带占比 > 0.35**；
未命中时记日志 `未检测到开头提示音（tone=N）`，方便用户侧排查。
**验证**：560/900/1200Hz 三组合成提示音分别裁掉 1.05/0.95/0.95 秒；噪声模拟人声不误裁；
63 个测试全绿（测试信号从“纯音人声”改为噪声，避免被新阈值误判）。

**说明**：Key / TTS 开关 / 音色 / 合成方式是每台部署自己的数据，不会共享；
代码里的去提示音、尾音、mp3 处理随版本。用户要拿到本次放宽需要发 3.6.2。

### 🚀 3.6.2 已发布（2026-10-30 01:44）

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.6.2"`（发布版 `VIEWER_FEATURE=False`、`SCRIPT_HUB=False`、`MEMORY_FEATURE=True`） |
| 发布版 bot.py | 572798 字节，sha256 `09eafff5…0579a090` |
| 更新源 | version 3.6.2，`min_version: ""`（不强制），说明含剧本杀/语音/界面/修复四块 |
| 安装包 | `qqbot-latest.tar.gz.enc` sha256 `1f90bc08…cb67388`，144688 字节；版本化包 `qqbot-3.6.2.tar.gz.enc` 已生成 |
| 服务器 | 已部署 3.6.2 并重启，`app_version=3.6.2`；备份 `bot.py.bak.<时间戳>` |

**验证**：63 个测试全绿；`updates/bot.py` 200（572798B）、`dl` 包 200（144688B）、`install.sh` 200；
模拟 3.6.1 客户端检查更新 → `latest=3.6.2, has_update=True, force=False`；服务 active，近 5 分钟 ERROR 0。

**3.6.2 内容**：剧本杀（按 QQ 分配剧本/开关/重开/选历史局/对话留存，剧本只在作者服务器、用户端拉取不落盘、内嵌水印）；
语音去提示音检测放宽到 300~1400Hz、尾音与停顿、测试 Key 按钮、语音 Key 保存与生图分离；
用户端移除剧本库/剧本接口；提示词长度兜底、自回环过滤等。

### 开头裁剪过头（切到人声）修复（2026-10-30 01:54，未升版本）

用户反馈 3.6.2 后「前面几个字听不到了」。原因：上一版把提示音判据放宽到 300~1400Hz、
窄带 >0.35，人声元音也被当成纯音，`last_tone` 越界到人声里 → 裁掉开头。

**重写 `leading_beep_seconds()`**：
1. 先扫前 2.5s，逐 20ms 记录峰值/RMS/是否纯音
2. 找**人声起点**：连续 3 个有声窗、至少 1 个不是纯音、且峰值频率跨度 > 40Hz（说明在变化）
3. 裁切点 = 人声起点 - 0.12s（保护首字），范围 0.1~2.2s
4. 找不到人声才退回“最后一个纯音窗结束 - 0.05s”

**实测**：两段句子均裁 1.81/1.82s；处理后开头 0.4s 峰值 300/317Hz（人声，不再是 560Hz 纯音）；
63 个测试全绿；已发测试语音（`retcode=0`，47085 字节）。

**注意**：3.6.2 已发布且含旧检测，用户端需要 3.6.3 才能拿到本次修复。

### 作者预设配置打包（2026-10-30 02:05，未升版本）

需求：除密钥外，把作者的配置打包给新部署用户。

实现：
1. `deploy/presets.json`：从作者 `data.db` 导出 **97 项**非密钥配置（人设、语音引擎/音色/情绪指令/模式、
   生图参数、记忆策略、黑话设置、回复分段、关键词、表情概率、休息时间等）
2. 发布版注入 `PRESET_SETTINGS`（make_release 自动注入并校验不能含密钥）
3. `Store._apply_presets()`：**只对全新数据库** `INSERT OR IGNORE`，老用户升级不受影响
4. 排除项：所有 API Key / token / 分发 token / 管理员密码 / 服务器地址 / install_id / app_version /
   `image_self_ref` / `game_api_url` / `enable_viewer_role` / `public_base_url`
5. 新部署默认 `voice_tts_enabled=0`、`voice_asr_enabled=0`、`image_enabled=0`（没配 Key 不报错）

**顺带修正**：作者库里的 `voice_zvoice_style` 之前被误存成示例文本（带反引号），已改回正式情绪指令。

**验证**：空库模拟 → 写入 97 条、含 persona、无密钥、情绪指令正确、三个功能开关为 0；63 个测试全绿。
**注意**：3.6.2 已发布且不含预设，用户要拿到需要发 3.6.3。

### 🚀 3.6.3 已发布（2026-10-30 02:12）

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.6.3"`（`VIEWER_FEATURE=False`、`SCRIPT_HUB=False`、`MEMORY_FEATURE=True`） |
| 发布版 bot.py | 578079 字节，sha256 `41c4b9c6…46e7c64c` |
| 更新源 | 3.6.3，`min_version: ""`，说明含开头裁剪修复 + 预设配置 |
| 安装包 | `qqbot-latest.tar.gz.enc` sha256 `cbcafcff…eb73276`，146896 字节；`qqbot-3.6.3.tar.gz.enc` 已生成 |
| 服务器 | 已部署 3.6.3 并重启，`app_version=3.6.3`；备份 `bot.py.bak.<时间戳>` |

**验证**：63 个测试全绿；更新源/安装包/install.sh 均 200；模拟 3.6.2 客户端 → has_update=True；
服务 active、近 5 分钟 ERROR 0。

**3.6.3 内容**：①开头裁剪改为“先识别人声起点”，不再切掉首字；②新部署内置 97 项非密钥预设
（人设/语音/生图/记忆/回复等），老用户升级不覆盖；③保留剧本杀、去提示音、测试 Key 等。

**打包小坑**：`deploy/files/bridge/__pycache__` 导致 pack.sh 中止，已删除并重新打包。

### 🚀 3.6.4 已发布（2026-10-30 02:20）

**改动**：`leading_beep_seconds()` 改为「裁到人声起点」——把稳定纯音/静音都当前缀，
遇到连续 2 个非稳定纯音的有能量窗即认定人声开始，裁到它前 0.12s。
不再依赖提示音频率（560/900/1200/2000/3000Hz 实测都能裁），纯人声不裁。

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.6.4"`（VIEWER/SCRIPT_HUB 关闭、记忆保留、预设保留） |
| 发布版 bot.py | 577852 字节，sha256 `dc2f9cac…` |
| 更新源 | 3.6.4，`min_version: ""` |
| 安装包 | sha256 `bb45da93…`，146784 字节；`qqbot-3.6.4.tar.gz.enc` 已生成 |

**验证**：560/900/1200/2000/3000Hz 提示音均能被裁到人声起点；纯人声裁 0；
真实智谱音频裁 1.82/1.84s，裁后开头峰值 286/330Hz（人声）；63 个测试全绿；
模拟 3.6.3 客户端 → has_update=True；服务 active、ERROR 0。

### 🚀 3.6.5 已发布（2026-10-30 02:22）——语音去提示音不再依赖 ffmpeg

**用户更新 3.6.4 后仍没效果的排查结论**：更新源文件本身正确（sha 与发布版一致、修复代码在包内），
真正原因是**用户机器可能没有 ffmpeg**：旧 `prepare_voice()` 在 ffmpeg 解码失败时直接回退**原始音频**，
所以提示音根本不会被裁；作者服务器装了 ffmpeg 所以一切正常。

**修复**：
1. 新增 `Bridge.trim_wav_pure()`：纯 Python 解析 WAV，裁掉开头提示音 + 补 0.3s 静音，返回 WAV
2. `prepare_voice()`：ffmpeg 缺失/解码失败/异常 → 走纯 Python 裁剪，不再退回原始音频
3. 启动日志新增：`启动版本 x.y.z | ffmpeg=ok/missing | 语音引擎=...`
4. 语音页新增「音视频处理」状态提示（已就绪 / ⚠ 未安装 ffmpeg）
5. `api_voice_get` 返回 `ffmpeg_ok`

**实测**：真实智谱音频纯 Python 裁剪 4.35s → 2.83s，开头峰值 310Hz（人声）；63 个测试全绿（新增纯裁剪用例）。

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.6.5"` |
| 发布版 bot.py | 579798 字节，sha256 `d4ec6967…` |
| 更新源 | 3.6.5，min_version 空 |
| 安装包 | sha256 `879a0253…`，147472 字节 |

**验证**：模拟 3.6.4 客户端 → has_update=True；服务 active、ERROR 0。

### 🚀 3.6.6 已发布（2026-10-30 02:26）——自动补 ffmpeg 依赖

- `Bridge.install_ffmpeg()`：启动时若缺 ffmpeg 且 `sudo -n true` 可用，依次尝试
  `apt-get/dnf/apk install ffmpeg`（超时 240s）；失败只告警，语音继续走纯 Python 去提示音
- 放在后台任务执行，不阻塞启动
- `install.sh` 安装 ffmpeg 后增加可用性校验与提示；`check.sh` 增加 ffmpeg 检查项
- 语音页提示补充手动安装命令

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.6.6"` |
| 发布版 bot.py | 581345 字节，sha256 `1586412d…` |
| 更新源 | 3.6.6，min_version 空 |
| 安装包 | sha256 `e5a300cf…`，147984 字节 |

**验证**：模拟 3.6.5 客户端 → has_update=True；`install_ffmpeg()` 返回 True；63 个测试全绿；
服务 active，启动日志显示 `3.6.6 | ffmpeg=ok`。

### 🚀 3.6.7 已发布（2026-10-30 03:11）——语音诊断

用户反复反馈“用户端语音开头还有滴声”，作者端已确认处理后的音频无 560Hz 前导音
（逐窗峰值在变、是人声）。为了定位到底卡在哪一步，新增诊断：

- `POST /api/voice/diag`（超管）：同一句合成两段音频——①原始合成 ②后处理（去提示音）
- 语音页「语音诊断」按钮：直接显示两段播放器 + 版本/ffmpeg/引擎/字节数
- 判断方法：②没有滴声但实际消息还有 → 声音来自 QQ 客户端播放提示音；
  ②仍有滴声 → 该部署没跑新代码或处理失败（看启动日志版本与 ffmpeg）

| 项目 | 值 |
|---|---|
| 版本 | `3.6.7`，发布版 584187 字节，sha256 `5796bd76…` |
| 更新源 | 3.6.7，min_version 空 |
| 安装包 | sha256 `d7c4aa32…`，已发布 |

**验证**：作者端诊断接口返回原始 397200B / 处理后 56109B；处理后开头 0.4s 逐窗峰值在变（无 560Hz 纯音）；
63 个测试全绿；服务 active。

### 🚀 3.6.8 已发布（2026-10-30 17:05）——语音页 Key 与 GLM-TTS 不互通

用户截图：语音页显示「已保存 2a484****9ZkF」，点试听却报「智谱 TTS 未配置 API Key」。

**根因**：`synthesize_zhipu()` 的取值顺序是 `voice_zhipu_key → image_api_key_zhipu`，
**漏了语音页实际写入的 `voice_zvoice_key`**；而页面掩码是按 `voice_zvoice_key` 显示的。
所以“看起来存了、实际用不上”。

**修复**：`synthesize_zhipu()` 改为
`voice_zvoice_key → voice_zhipu_key → image_api_key_zhipu`，与页面/试听/诊断保持一致；
错误提示也改成“请在语音页填智谱 Key，或复用生图 Key”。

**验证**：模拟「生图 Key 为空、只填语音 Key」→ 合成成功 153360 字节；
线上试听接口返回 `code:0, bytes:331920, 1.7s`；63 个测试全绿。

| 项目 | 值 |
|---|---|
| 版本 | 3.6.8，发布版 584379 字节，sha256 `a3916136…` |
| 更新源 | 3.6.8，min_version 空 |
| 安装包 | sha256 `c859a125…`，148768 字节 |

### 🚀 3.6.9 已发布（2026-10-30 17:50）——语音语速 + 音质 + Key 报错收口

对方 AI 的诊断：链路正常（合成→裁剪 1.84s→转码），提示音是服务商固定片头；报错来自
「逐字朗读分支没读语音页的 Key」。3.6.8 已修该取值顺序，3.6.9 再补两项体验：

1. **语速可调** `voice_zhipu_speed`（0.9/1.0/1.1/1.2/1.3），逐字朗读传给智谱 `speed`；UI 下拉可选
2. **音质提升**：mp3 64k→**96k**，编码前加 `loudnorm=I=-16:TP=-1.5:LRA=11` 响度归一化
3. 开头提示音仍按人声起点裁剪（不依赖频率）

**验证**：语速 1.0 原始 6.23s→处理后 4.97s；语速 1.2 原始 5.50s→4.27s；
63 个测试全绿。

| 项目 | 值 |
|---|---|
| 版本 | 3.6.9，发布版 585568 字节，sha256 `a7d56438…` |
| 更新源 | 3.6.9，min_version 空 |
| 安装包 | sha256 `a8c85dae…`，149024 字节 |

### QQ 频繁掉线排查 + 快速登录修复（2026-10-30 17:54）

**结论：不是代码问题**。NapCat 日志显示腾讯主动下发
`[KickedOffLine] [下线通知] 你的账号当前登录已失效`，随后 Worker 重启；
因为容器启动时**没有 `ACCOUNT` 环境变量**，NapCat 只能走二维码登录
（日志：`没有 -q 指令指定快速登录，将使用二维码登录方式`），之后每 2 分钟报一次
`Login Error ErrType:1 ErrCode:3`，直到有人扫码。

**代码层的影响（次要）**：过去 24 小时 bridge 被重启 **88 次**（连续修 bug 频繁部署导致）。
重启本身不会让 QQ 下线，但每次都会重连，且掉线时更容易撞上“要扫码”的状态。

**修复**：重建 NapCat 容器，补上 `-e ACCOUNT=3446248859`（其余参数、挂载、端口保持不变）：
```
正在快速登录 3446248859
login info: {'online': True, 'uin': '3446248859', 'nick': '心如止水的大肥鱼'}
```
以后被踢或 Worker 重启会自动快速登录，不再每次都要扫码（若腾讯要求验证仍需扫码）。

**后续优化建议**：① 合并部署减少重启；② 掉线看门狗 + 后台横幅；
③ 根治仍是官方 Bot / 国内 IP（协议端 + 海外 IP 是风控主因）。

### 稳定性优化（2026-10-30 18:00）

- **快速登录**：NapCat 容器补 `ACCOUNT=3446248859`，被踢/Worker 重启后自动快速登录（已验证 online）
- **安装模板**：`compose.yaml` 增加 `ACCOUNT: "__NAPCAT_ACCOUNT__"`；`install.sh` 支持
  `export NAPCAT_ACCOUNT=QQ号` 后安装即启用；README 补充说明
- **智能部署**：新增 `deploy/deploy.sh`——生成发布版后对比线上 sha，**代码没变就跳过上传和重启**，
  避免无意义重连；`--force` 可强制。实测：本地/线上 sha 相同 → 输出“跳过上传和重启”
- **工作方式**：以后把多个修复合并成一次部署，不再每改一处就重启

### 原创剧本《雪隐山庄》入库（2026-10-30 18:10）

- 文件：`scripts_library/雪隐山庄.md`（15292 字符，中文 10003 字，5 章）
- 结构：世界观/核心真相、境界体系（未入流→大宗师）与成长白名单、初始面板、
  事件表、线索表（含误导）、NPC 表、5 个结局、章节计划、GM 回合格式、
  场景扩写、台词本、跑团示例、判定速查表、开店自检
- 真凶与手法固定：沈清漪（听雪楼遗孤）·冰针+寒髓散·麻线造假密室；陆忠包庇
- 已通过 `/api/admin/save` 上传到独立剧本库（id=2，名称「雪隐山庄」），公开列表可见，
  可直接在后台「剧本杀」里分配给玩家

### 🚀 3.6.10 已发布（2026-10-30 20:55）——试听也去提示音

用户反馈“更新到最新版还是有滴咚”。排查发现：**`/api/voice/preview`（试听）只做 synthesize，
没走 `prepare_voice`**，所以试听听的是带 560Hz 前导音的原始音频；正式消息路径是裁剪过的。
判断失误多半来自“点试听”。

**修复**：试听改为 `synthesize → prepare_voice → 播放`，与正式发送完全一致。
**验证**：试听返回 mpeg 67437B，开头 50ms 峰值序列 `2080/180/200/300/680/…`（变化，无恒定纯音）。

| 项目 | 值 |
|---|---|
| 版本 | 3.6.10，发布版 585709 字节，sha256 `17b4d9bb…` |
| 更新源 | 3.6.10，min_version 空 |
| 安装包 | sha256 `fcb64705…`，149408 字节 |

### 剧本杀机制升级（2026-10-30 22:30，未升版本）

1. **服务端暗骰**：每回合生成 `d100` 写入系统提示，GM 必须据此判定（70+成功 / 30-69险成带代价 / ≤29失败但推进），
   且不得向玩家展示数值——解决模型“永远成功”的问题
2. **前情摘要**：`runs.summary` 新列；每 10 回合把对话压缩成 ≤300 字摘要，后续上下文 = 系统提示 + 摘要 + 最近对话
   （字符预算 5200），长局不再丢前情；摘要空返回会自动重试
3. **上下文预算**：历史消息按字符预算从近到远取，单条上限 1500 字，避免 token 爆炸
4. **新指令**：`状态`（只输出面板）、`重开本局`（新开一局并设为当前）、原有 `存档 / 玩第N次 / 退出游戏`
5. **输出清洗**：去掉 `##`、`**`、压缩空行，适配 QQ 纯文本阅读
6. **失败兜底**：LLM 空返回重试一次，仍失败给提示语，不卡死

**实测**：两回合输出 659/917 字，无 Markdown 标记；摘要 113 字写入成功；测试数据已清理。

### 剧本杀第二轮升级（2026-10-30 22:37，未升版本）

1. **结构化状态**：`runs.state_json` 新列；每回合要求 GM 在末尾附 `<<STATE {json}>>`（玩家不可见），
   代码解析后落库，并作为下一回合的「权威状态」注入；玩家可见文本会剔除该块
2. **分段发送**：`game_split()` 按【叙事】【选择】等段落切分，最长 900 字/条、最多 3 条，
   条间 0.8s 间隔，避免 QQ 长文挤成一坨
3. **主动投骰**：玩家发「判定 武力/感知/智谋/魅力」→ 代码掷 d100 + 属性×5，先回报结果，再让 GM 叙事；
   骰值同样不写进剧情
4. **修复 token 截断（关键）**：当前模型 `deepseek-flash` 每次思考约 900 reasoning tokens，
   原 `max_tokens=1200/1500` 被吃光导致正文断在半句（实测 finish_reason=length、内容仅 188~407 字）。
   回合预算提到 **3200**、摘要提到 **900**，实测回合输出 1033 字完整收尾、STATE 成功入库
5. 上下文预算 5200 字 + 每 10 回合摘要（沿用）

**未做**：多剧本并行（需要在后台加「一人多本」分配与切换 UI，涉及表结构与页面改造，留待下轮）

### 剧本杀·群聊接入（2026-10-30 22:59，未升版本）

按用户决策实现：①群内必须 @机器人；②同一玩家只有最后接入的群生效；③其他人只能旁观不能推进。

- 新表 `game_contexts(qq, group_id, script_id, active, updated_at)`，`Store` 增加
  `ctx_set/ctx_get/ctx_deactivate/ctx_active/ctx_list`
- `handle_game` 支持 group：白名单群 + `@机器人 继续游戏` 才接入；`结束游戏` 断开；
  未接入时的普通消息照常走聊天（不会被剧本吞掉）；未接入却发游戏指令会提示先接入
- 进度共用：群聊和私聊读同一个 `runs`，上下文/摘要/状态连续
- 群消息分发：`(private or (group and at_me))` 时才进 `handle_game`
- 后台「剧本杀」新增「群内接入」卡片：列出 QQ/群/剧本/状态/时间，可断开；接口
  `GET /api/game/contexts`、`POST /api/game/context/kick`
- 测试：新增 `TestGameContexts`（后接入群生效、断开），65 个测试全绿

**实测**：群里「继续游戏」→ 接入成功并提示第 1 次/1 回合；「结束游戏」→ 断开且进度保留；
未接入发普通消息返回 False（不影响正常聊天）。

### 修复：休息模式吞掉剧本玩家私聊（2026-10-30 23:15，未升版本）

用户 248183616 私聊发「开始」无反应。查 NapCat 日志消息**已到达**，但 bridge 连「收到」日志都没有：
22:00–08:00 是休息时段（`rest_enabled=1`），非超管私聊在 `rest_allows` 处直接 return，
剧本玩家也被一起挡掉。

**修复**：`handle_message` 增加 `game_pass`——已分配剧本的玩家私聊、以及已接入该群的玩家，
在休息时段照常处理，不再被静默丢弃。
**验证**：休息时段模拟私聊「开始」→ 日志出现「收到」，回复两条（叙事+面板），新局回合=1。
已给该用户发私信说明，请其重发「开始」。

### 剧本杀「休息时段放行」开关（2026-10-30 23:37，未升版本）

- 新设置 `game_rest_bypass`（默认 `1` 开启）：控制休息时段是否放行剧本玩家
- `handle_message` 里的 `game_pass` 判断改为受该开关控制
- 后台「剧本杀」首张卡片新增按钮：「休息时段放行剧本玩家：已开启/已关闭」，点击即切换
- 接口：`POST /api/game/rest_bypass {enabled:true/false}`；`GET /api/game/overview` 返回 `rest_bypass`
- 实测（强制休息时段）：关闭 → 私聊「开始」0 局（被拦）；开启 → 1 局（正常回复）；测试后已还原
  `rest_enabled`（原本是 0，即休息模式本身未开）

### 剧本杀「删除玩家」修复（2026-10-30 23:53，未升版本）

**问题**：删除只执行 `DELETE FROM players`，留下 `runs`（还是 active）、`messages`、`game_contexts`。
表现为“删了还在/重加接旧进度/群接入列表有幽灵记录”。库里实测 248183616 被删后仍有 1 局 active、6 条对话。

**修复（默认彻底删除）**：
- `Store.player_delete(qq, purge=True)`：清 `game_contexts` → `messages`(按 runs) → `runs` → `players`，
  返回各表删除条数；`purge=False` 时保留存档、只把局置 finished 并解绑
- API `POST /api/game/player {action:"delete", purge:true}`，返回 `deleted:{runs,messages,contexts}`
- 前端确认文案改为「存档、对话记录、群内接入都会一起删除，无法恢复」，删除后弹窗显示删除统计并刷新
- 测试：新增 `TestGameDelete`（purge 全清 / keep 保留并结束），**66 个测试全绿**
- 已清理线上孤儿：248183616 → 删除 1 局、6 条对话；现在只剩房主 3 局、18 条对话

### 后台「不出数据」修复（2026-10-31 00:52，未升版本）

**现象**：后台页面空白/无数据，但接口都 200（status/overview/contexts/voice 正常）。

**根因**：`gameDelete` 的确认文案在源码里写了 `\n`，Python 三引号字符串会把它**转义成真实换行**，
嵌入 JS 单引号字符串后语法错误，整页脚本不执行 → 看起来“没数据”。
（之前用源码切片校验，看到的是字面量 `\n`，所以漏过了。）

**修复**：源码改为 `\\n`（HTML 里保留 `\n` 转义）。
**防复发**：`make_release.py` 新增校验——用 `ast.literal_eval` 取**解析后的 ADMIN_HTML**，
抽取 `<script>` 跑 `node --check`，失败直接中止发布（实测注入坏行会报
「后台页面 JS 语法错误（会导致整页无数据）」并 exit 1）。

**验证**：线上页面 `node --check` 通过；接口均 200；发布校验可拦截同类错误。

### 后台状态误报在线修复（2026-10-31 00:56，未升版本）

**现象**：QQ 实际掉线（发送返回 `retcode 1200 EventChecker Failed`），后台仍显示在线。

**原因**：`napcat_login_info()` 只要返回里有 uin 就判定 online；NapCat 在会话失效后仍报
`online:true`（僵尸态），所以状态页一直显示在线。桥接 WS 也没断，`bridge_connected=true`。

**修复**：
1. `send()` 的 echo 改为 `snd...`，`ws_loop` 收到该 echo 的返回若 retcode 非 0/1 → 记录
   `_send_fail{at,code,msg}`，日志告警“发送失败（判定 QQ 可能已掉线）”
2. `api_status` 结合 `_send_fail`（10 分钟内）：`qq.online=false`、`need_login=true`，并返回
   `send_failed/send_error`
3. `need_login` 纳入 `not qq.online`；前端横幅条件加 `qq.online === false`

**验证**：当前账号确实掉线 → `need_login=true, online=false, bridge=false`；
NapCat 重启后快速登录失败，已生成二维码待扫（`/api/qr`）。

### 🚚 NapCat 迁移到上海服务器（2026-10-31 02:32）

**架构**：
```
上海服务器（地址与密码已移除）
  └ NapCat 容器（ACCOUNT=3446248859，只监听 127.0.0.1:3001 / 6099）
  └ autossh 反向隧道 → 香港 127.0.0.1:3011 → 上海 3001；香港 127.0.0.1:6099 → 上海 6099
  └ 2G swap；Docker 镜像加速 docker.xuanyuan.run
香港 YOUR_SERVER_IP
  └ bot.py / data.db / 后台 / 更新源 / 剧本库（全部不变，无需备案）
  └ config.yaml: ws_url=ws://127.0.0.1:3011, webui_token=b39f9839…
  └ 旧 NapCat 容器已 stop + restart=no（避免同号双登）
```

**隧道服务**（上海）：`/etc/systemd/system/napcat-tunnel.service`
```
autossh -M 0 -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes   -R 127.0.0.1:3011:127.0.0.1:3001 -R 127.0.0.1:6099:127.0.0.1:6099   ubuntu@YOUR_SERVER_IP
```

**验证**：发送 retcode 0；status `online=True, uin=3446248859, bridge=True, need_login=False`。

**回滚**：香港 `docker update --restart=unless-stopped napcat && docker start napcat`，
config 改回 `ws://127.0.0.1:3001` + 旧 token `d261001b…`，`systemctl restart qqbot-bridge`，停上海隧道。

**发布流程不变**：代码/打包/更新源仍全在香港。

### 🏠 托管模式一期（2026-10-31 02:52）

**双节点**：
- 香港（程序服务器）：`https://xrzs.cloud/host/`（owner / 090b360d57521ca9）——给普通用户托管
- 上海（YOUR_SERVER_IP_2）：`https://xrzs.cloud/shost/`（owner / shb91f60d6ee89）——给你的号托管
- 租户入口统一 `https://xrzs.cloud/t/<token>/`；香港主控对未知 token 回退到上海 8092

**每个租户** = 1 个 NapCat 容器（`--memory=900m --cpus=1`，仅 127.0.0.1 端口）
\+ 1 个 bot 进程（systemd `fishpond-tenant-<id>`，`FISHPOND_HOME` 独立数据目录 + 独立后台端口）
**目录**：`/opt/fishpond/{app,hosting,venv,tenants/<id>}`；主控 `fishpond-host.service`（8090）
**隧道**：上海 autossh `-R 3011/6099`（NapCat）、`-R 8092:8090`（上海主控）
**Caddy**：`/host/*`→8090（香港）、`/shost/*`→8092（上海）、`/t/*`→8090（香港）
**计费字段**：meta.json `plan/price/days/expires_at`；续期 `tenant.py renew`；到期未自动停（下一期做）

**已验证**：创建 t1/t2 → 租户页 200 → 二维码生成 → 删除清理；三站 200。

**坑**：8091 是剧本库端口，不能复用；上海主控用 8092；SH 主控需 `FISHPOND_ADMIN_PREFIX=/shost`。

**下一期**：到期自动停机、配额（消息/天数）、备份、支付/自助开通。

### 🚀 3.8.0 已发布（2026-10-31 03:50）

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.8.0"`（VIEWER False / SCRIPT_HUB False / 记忆保留） |
| 发布版 bot.py | 637982 字节，sha256 `1c544af9…` |
| 更新源 | 3.8.0，`min_version: ""`，说明含托管/群聊剧本杀/沙盒/语音/修复 |
| 安装包 | `qqbot-latest.tar.gz.enc` sha256 `869aa108…`，162192 字节；`qqbot-3.8.0.tar.gz.enc` 已生成 |
| 服务器 | 已部署 3.8.0 并重启；`/opt/fishpond/app/bot.py` 同步；`app_version=3.8.0` |

**发布内容**：托管租户（创建/账号密码/一键远程部署/群内接入）、剧本杀群聊模式、
沙盒剧本《轮回修仙模拟器》《末世避难所》、语音试听去提示音/Key 修复/96k、
删除残留修复、页面 JS 校验、休息时段放行剧本玩家、状态误报在线修复。

**验证**：66 测试全绿；更新源/安装包/版本化包 200；模拟 3.6.10 客户端 has_update=True；
启动日志 `3.8.0 | ffmpeg=ok`；已给作者 QQ 发发布通知。

### 🚀 3.8.1 已发布（2026-10-31 12:45）

| 项目 | 值 |
|---|---|
| 版本 | `APP_VERSION = "3.8.1"` |
| 发布版 bot.py | 638347 字节，sha256 `85795df2…` |
| 更新源 | 3.8.1，min_version 空 |
| 安装包 | sha256 `b0f73729…`，162320 字节 |

**内容**：心跳 24h → **10 分钟**（失败 2 分钟重试，可配 `stats_heartbeat_seconds`）；
统计新增「实时在线(15分钟)」「1小时内在线」卡片；`checkins` 明细每小时最多一条防膨胀。

**验证**：66 测试全绿；更新源/安装包 200；3.8.0 客户端 has_update=True；
启动日志 `3.8.1`；通知 retcode 0。部署时 SSH 曾断一次，已核对后重做，最终状态正确。

### 🚀 3.9.0 已发布（2026-10-31 14:16）——修复更新校验失败 + Breeze 语音

**事故**：3.8.1 发布后又多次热改 `updates/bot.py`（Breeze、按钮、尾音等），但 `latest.json` 的 sha
仍是 3.8.1 的旧值 → 用户更新时报「sha256 不匹配，自动更新失败，旧版本未改动」。

**处理**：发布 3.9.0，重新生成 latest.json 并核对下载文件 sha 与声明一致；`deploy.sh` 增加防呆：
版本号未变但更新源文件变了会打印警告，避免再次出现同版本 sha 漂移。

| 项目 | 值 |
|---|---|
| 版本 | 3.9.0 |
| 更新源 sha | `2484f740…`（下载实测一致） |
| 安装包 | sha256 `3e425903…`，164464 字节 |
| 内容 | Breeze Blue 语音引擎（按钮切换、开头 120ms 保护、结尾 1.2s 静音+0.4s 淡出）、怼人发语音、修复更新校验 |

**验证**：3.8.1 客户端 → has_update=True；下载文件 sha 与 latest.json 一致；服务 active。

### 🚀 3.9.2 已发布（2026-10-31 14:52）——一键表情包

| 项目 | 值 |
|---|---|
| 版本 | 3.9.2 |
| 更新源 sha | `3bb554e2…`（下载实测一致） |
| 安装包 | sha256 `3d0f26b3…`，165600 字节 |

**内容**：表情包页新增「一键获取群主表情包」——下载 `https://xrzs.cloud/dl/stickers-pack.zip`
（184 张、16.3MB、带 manifest 描述），按文件名去重导入；修复按钮 JS `async async` 语法错误；
`deploy.sh` 不再自动覆盖 `updates/bot.py`（此前导致同版本 sha 漂移、用户更新校验失败）。

**验证**：3.9.1 客户端 → has_update=True；下载 sha 与声明一致；服务 active；通知 retcode 0。

### 🚀 3.9.4 已发布（2026-11-01 12:2x）——撤回上报

| 项目 | 值 |
|---|---|
| 版本 | 3.9.4 |
| 更新源 sha | `d3317c82…`（下载实测一致） |
| 安装包 | 167840 字节，sha `80e96658…` |
| 冒烟 | 通过（服务 / 表情图 200 / sha 一致 / 页面 200） |

**内容**：`group_recall` / `friend_recall` 上报超管（撤回信息 / 账号 / 时间 / 来自）；
超管页「黑名单」后新增「撤回」三级页：总开关、时间段（支持跨午夜）、回发到群开关。

**注意**：撤回内容缓存在内存（最多 500 条），重启后旧消息撤回显示“未缓存”。
发布时 SSH 断过一次，核对后确认部署已完成，未重复执行。

### 🚀 3.9.5 已发布（2026-11-01 21:1x）

| 项目 | 值 |
|---|---|
| 版本 | 3.9.5 |
| 更新源 sha | `e99fb373…`（下载实测一致） |
| 安装包 | 197280 字节，sha `22441802…` |

**更新日志（仅可见功能）**：群聊管理重构（多群面板/外链/验证/踢人/禁言/巡查/关键词/黑名单）、
B站（解析/热门/学习/笔记/自动学习/分享）、撤回上报。
**内部注意**：本次同步上线了未写入更新日志的隐藏系统，细节见代码，不在对外说明中体现。

### 🚀 3.9.7 已发布（2026-11-02 13:1x）

| 项目 | 值 |
|---|---|
| 版本 | 3.9.7 |
| 更新源 sha | `934ef464…`（下载实测一致） |
| 安装包 | 198768 字节，sha `05f1b610…` |

日志：省钱模式（超管后台余额+开关）、余额低自动精简、余额提醒/恢复、B站主动找话题保存修复、死代码清理。
说明：不含任何隐藏系统描述。

### 🚀 3.11.0 已发布（2026-11-03 03:0x）

| 项目 | 值 |
|---|---|
| 版本 | 3.11.0（模块化版） |
| 更新源 | `598b449f…`（单文件发行版，内含模块包，旧版 updater 可升级） |
| 目录包 | `bot-package.tar.gz` 220KB，sha `04a5faf3…` |
| 安装包 | 708800 字节，sha `3fd9ef6d…` |

结构：fishpond/{core,platforms,features,web} + bot.py 薄入口；INDEX.md 47 项功能索引。

### 🚀 3.11.1 已发布（2026-11-03 03:2x）

| 项目 | 值 |
|---|---|
| 版本 | 3.11.1 |
| 更新源 sha | `3b2b7040…`（单文件发行版，内含模块包） |
| 目录包 | `bot-package.tar.gz` 223KB，sha `672b6166…` |
| 安装包 | 703936 字节，sha `80b154b8…` |

修复：`/api/tokens` 500（runtime 缺 timedelta）。
新增：`check_index.py`（构建阻断）、`smoke_http.py`（发布前置 HTTP 冒烟，51 接口 0.1s，不进用户包）。

### 🚀 3.12.0 已发布（2026-11-03 03:3x）

| 项目 | 值 |
|---|---|
| 版本 | 3.12.0 |
| 更新源 sha | `f63baee8…` |
| 目录包 | `bot-package.tar.gz` 226KB |
| 安装包 | 714432 字节，sha `29ef993a…` |

新增：运维面板（健康/错误/诊断包/回滚）、升级前快照、DB 报告；
构建新增安全审计门禁；发布新增 HTTP 冒烟（54 接口）。

### 🚨 3.12.0 更新事故与 3.12.1 修复（2026-11-03）

- 现象：后台点更新后服务崩溃循环、站点 502（服务器未重启）。
- 根因：更新处理函数已迁入 `fishpond/platforms/admin.py`，但仍用 `Path(__file__)` 当作程序入口，
  导致把新 bot.py 写进了 admin.py 自身。
- 恢复：从升级前快照 `snapshots/20261103-033127` 恢复 admin.py，服务恢复。
- 修复：更新目标与重启入口都固定为 `BASE/bot.py`；`check_index.py` 增加入口回归检查（错误级）。
- 发布：3.12.1（更新源 `46880665…`，安装包 714512 字节）。

### 🔐 3.13.0 已发布（2026-11-03 04:0x）

| 项目 | 值 |
|---|---|
| 版本 | 3.13.0 |
| 更新源 sha | `5dbd1e87…` |
| 目录包 | 229KB |
| 安装包 | 723120 字节，sha `8f306dd1…` |

新增：schema_version + 迁移框架、secrets 表（AES-GCM）、config.yaml 加密迁移后删除、
密钥文件 /etc/fishpond/secret.key（600）。
老用户升级演练：v0 库 + 明文配置 → 自动迁移 v1/v2、配置删除、记忆 1687 条保留、密钥读回正常。

### 发布时还需做（等用户明确说“发版”才做）

1. **先 bump 版本号**：`bridge/bot_admin.py` 的 `APP_VERSION` 改成新版本（版本号只在这一步改）
2. 重新生成发布版 `python3 deploy/make_release.py`，再用新版本号更新 `deploy/latest-3.5.6.draft.json` 的 `version`/`date`/`sha256`（版本号以当时定为准，文件名只是占位）
3. 备份线上 `bot.py` / `data.db`（每次发版前重新备份）
4. `PACK_PASS` 打包：`SSHPASS=… PACK_PASS=… bash publish_pkg.sh`（会顺带更新 `bootstrap-install.sh` 的 fallback SHA）
5. 上传 `deploy/files/bridge/bot.py` 到 `/opt/qqbot/bridge/updates/bot.py`，把填好的 json 写成 `/opt/qqbot/bridge/updates/latest.json`
6. 同步 `settings.app_version`；线上 `bot.py` 换成发布版（发布版 `VIEWER_FEATURE=False`；主人自己的服务器日常可保留开发版）
7. 验证两个 latest.json 的 version/sha、下载实测 SHA、`systemctl is-active qqbot-bridge`、QQ 在线
8. 注意：`min_version` 一旦指到新版本，旧版本会立刻进 426 状态，后台写操作被挡到更新完成为止
