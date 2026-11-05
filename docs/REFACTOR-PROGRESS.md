# 模块化重构进度

## 已完成（第 1 步：骨架）
- 新建 `fishpond/` 包结构：core / platforms / features / web / tools
- 后台前端从 Python 内嵌字符串抽出为 `fishpond/web/index.html`（245,606 字符）
- `bot_admin.py` 改为优先读取 `web/index.html`，找不到才用内嵌副本
- 构建脚本自动把前端复制到产物目录 `files/bridge/web/index.html`
- 功能注册表 `fishpond/registry.py` + 索引生成器 `fishpond/tools/make_index.py`
- 生成 `INDEX.md`：33 项功能，含入口/接口/表/配置/页面/文件
- 已部署验证：页面 200，确认从静态文件加载，单测通过

## 待办（按批次）
1. 拆 bili、economy 为独立模块（mixin + api 注册）
2. 拆 emotion（情绪/恐慌/无聊/人格/关系）
3. 拆 group 群管理 + panel 群面板
4. 拆 chat 核心（人设/记忆/回复）
5. 前端拆 js/css，静态托管
6. 更新器改 tar.gz 目录包 + 全量发布

## 第 2 批：B站 + 省钱（已完成）
- `fishpond/features/bili/service.py`：BiliMixin（解析/热门/学习/笔记/自动学习/主动话题/配置接口）
- `fishpond/features/economy/service.py`：EconomyMixin（余额、恐慌提醒、省钱模式、配置接口）
- Bridge 改为 `class Bridge(BiliMixin, EconomyMixin)`
- 构建产物同时输出 `fishpond/` 包；部署需带目录（更新器待改）

验证：单测 66 OK，B站搜索正常，省钱接口正常，页面 200。

## 第 3 批：情绪/恐慌/无聊/人格/关系（已完成）
- `fishpond/features/emotion/service.py`：EmotionMixin + EmotionStoreMixin
- Store 改为 `class Store(EmotionStoreMixin)`，Bridge 增加 EmotionMixin
- 验证：情绪读写、关系识别、恐慌读写、无聊值、页面 200，单测 OK

## 部署现状
- 线上：`/opt/qqbot/bridge/{bot.py, web/, fishpond/}`
- 租户目录同步；权限已修正
- 剩余：group/panel、chat、前端 js 拆分、更新器 tar.gz、全量发布

## 第 4 批：群管理 + 群面板（已完成）
- `fishpond/features/group/service.py`：GroupMixin（巡查/禁言/踢人/验证/黑名单/关键词频次/违规处罚通知）
- `fishpond/features/panel/service.py`：PanelMixin（群面板生成/外链登录/配置/黑名单/一键登录）
- Bridge 继承 GroupMixin、PanelMixin；新增 admin_html() 供面板模块读取后台模板
- 验证：巡查/禁言/踢人/黑名单/验证/限频全部通过，外链页生成正常，后台 200
- 注意：测试发现踢人目标需 5 位以上 QQ（正则 5+），真实 QQ 均满足

## 第 5 批：聊天核心（已完成）
- `fishpond/features/chat/persona.py`：PersonaMixin（人设文本、ask_deepseek、人设增删改查接口）
- `fishpond/features/chat/memory.py`：MemoryMixin + ChatStoreMixin（记忆检索/提取/清理/接口/存储）
- 新增 `fishpond/core/config.py` 承接 MEMORY_FEATURE 等全局开关
- Bridge 增 PersonaMixin、MemoryMixin；Store 增 ChatStoreMixin
- 验证：人设非空、记忆提示正常、超管私聊回复「在呢老大，大半夜的还不睡啊」、单测 OK
- 迁移注意：静态方法里的 Store 引用、NOISE_WORDS、aiohttp 导入三个坑已修

## 第 6 批：前端静态化 + 目录包更新（已完成）
- 内联 <style>/<script> 抽出为 `web/css/app.css`、`web/js/app.js`
- index.html 从 245KB 降到 74KB，页面总大小 87KB
- 新增静态路由 `prefix + /web/{tail}` 与 `admin_css()`，群面板改用同一份 CSS
- 更新器支持 tar.gz 目录包：校验 sha → 解压 → 语法检查 → 备份 → 替换 bot.py/fishpond/web → 重启
- 单文件更新路径保留兼容
- 新增 `fishpond/tools/make_package.py` 打更新包
- 验证：页面 200、CSS/JS 200、外链页正常、单测 OK、沙箱包更新成功且版本解析 3.10.1

## 第 7 批：表情包/生图/语音/撤回（已完成）
- `features/sticker/service.py`：StickerMixin + StickerStoreMixin
- `features/image/service.py`：ImageMixin（含 is_self_image/self_image_extra 与模型常量）
- `features/voice/service.py`：VoiceMixin（TTS/ASR/配置/诊断）
- `features/recall/service.py`：RecallMixin（撤回上报与配置）
- Bridge 继承对应 mixin；单文件 657KB
- 验证：单测 66 OK、表情 184 张、语音开关、生图接口、撤回配置、页面 200
- 迁移坑：random/is_self_image/SELF_HINTS 常量需随模块带走

## 第 8 批：剧本杀（已完成）
- `features/game/service.py`：GameMixin + GameStoreMixin（剧本库/开局/回合/玩家/后台接口）
- Bridge 继承 GameMixin，Store 继承 GameStoreMixin
- 常量 GAME_PROMPT / SCRIPT_HUB 随模块
- 单文件降到 618KB
- 验证：单测 66 OK、剧本概览/列表接口 200、settings 按 SCRIPT_HUB 关闭返回 403（符合预期）、页面 200

## 第 9 批：后台平台层（已完成）
- `fishpond/platforms/admin.py`：AdminMixin（登录/鉴权/日志/自检/版本更新/目录包应用）
- 密码校验 hash_password/verify_password 随模块；BASE/APP_VERSION/LOG_RING/LOGIN_HTML/STICKER_DIR 通过辅助方法解耦
- 验证：登录 200、status/logs/admins 200、页面 200、单测 66 OK

## 第 10 批：Web 平台层（已完成）
- `fishpond/platforms/web.py`：WebMixin（后台路由装配、aiohttp 服务、静态文件、WebUI 前缀）
- Bridge 继承 WebMixin；单文件降到 571KB
- 验证：登录 200、页面 200、CSS 200、状态 200、单测 66 OK

## 第 11 批：OneBot 平台层（已完成）
- `fishpond/platforms/onebot.py`：OneBotMixin（连接、动作调用、发送、断线重连）
- Bridge 继承 OneBotMixin；单文件降到 573KB
- 修复模块缺失导入：sticker(random/secrets)、voice(secrets/subprocess)、onebot(hashlib/secrets)
- 验证：NapCat 已连接、私聊回复「在呢老大，大半夜的还不睡？」、页面 200

## 第 12 批：风格 + 音乐（已完成）
- `features/style/service.py`：StyleMixin（黑话/无聊/怼人/唤醒 + 后台接口）
- `features/music/service.py`：MusicMixin（点歌/唱歌/音乐卡片 + 接口）
- 语音合成/转写并入 `features/voice/service.py`（含静态 leading_beep 修复）
- 单文件降到 507KB，INDEX 43 项
- 验证：单测 66 OK、slang/bored/wake/music/voice 接口 200、页面 200

## 第 13 批：配置接口群（已完成）
- `features/config/service.py`：ConfigMixin（白名单/关键词/前缀/自动回复/频率/休息/好友/黑名单/会话）
- 依赖 VIEWER_FEATURE 从 core.config 引入
- 单文件降到约 470KB
- 验证：单测 66 OK、keywords/prefix/auto/rest/friend/blacklist/me 接口 200、页面 200

## 第 14 批：账号/供应商/托管（已完成）
- `features/accounts/service.py`：AccountsMixin（账号、模型供应商、API Key、余额、端点）
- `features/hosting/service.py`：HostingMixin（租户、节点、部署、二维码、远程 SSH）
- 依赖 PROVIDER_PRESETS / VIEWER_FEATURE / secrets 已补齐
- 单文件降到 455KB，INDEX 46 项
- 验证：单测 66 OK、accounts/providers/apikey/hosting 接口 200、页面 200

## 第 15 批：聊天调度 + 运行时（已完成）
- `features/chat/dispatch.py`：ChatMixin（消息解析、回复决策、LLM 调用、休息/频率、撤回关联）
- `features/runtime/service.py`：RuntimeMixin（启动循环、备份、统计、状态/令牌接口、后台辅助）
- 注入 Store / ProactiveMessenger 解决循环依赖；补齐 deque/sqlite3/timedelta/hash_password/
  build_self_image_prompt/audio_mime 等依赖
- 单文件降到 352KB（主要剩内嵌 HTML 兜底与启动 main）
- 验证：单测 66 OK、私聊回复「在啊，这么晚还没睡？」、页面 200

## 发布工具（3.11.1 起）
- `fishpond/tools/check_index.py`：入口/路由/表/模块/INDEX/前端/包完整性，error 阻断构建
- `fishpond/tools/smoke_http.py`：临时实例 + 假登录 + 并发 GET 51 接口，5xx/401 阻断发布
- 两个工具均不进入用户安装包（构建排除 tools）
- 首次冒烟抓到并修复 `/api/tokens` 500（timedelta 未导入）
