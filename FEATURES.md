# FishPond 功能总表

> 版本 3.11.1 · 索引 51 项 · 本表按"功能 → 怎么实现"整理，便于评估与排期。

---

## 一、已实现：对话与人格

| 功能 | 怎么实现 | 入口/文件 | 数据与配置 |
|---|---|---|---|
| 消息接收与回复 | NapCat WebSocket 收事件 → handle_message 判断 @/私聊/关键词 → 拼上下文 → 调 LLM → 分条发送 | `features/chat/dispatch.py` | 会话内存、`reply_*` |
| 触发判断 | 群里默认仅 @ 或关键词触发；私聊直接回；白名单/黑名单过滤 | dispatch | `wl_users`、`blacklist` |
| 回复频率 | 每群/全局最小间隔、每小时上限；超管绕过 | dispatch | `group_rate`、`rate_*` |
| 休息时段 | 配置起止时间，非超管消息静默；可公告 | dispatch | `rest_*` |
| 人设与语气 | 人设文本 + 身份边界 + 性别感知 + 记忆 + 黑话 + 时间 + 分段 + 情绪/关系/人格 + 余额提示，拼成 System Prompt | `features/chat/persona.py` | `personas`、`persona_*` |
| 多模型供应商 | 供应商列表、激活、测试、自动探测；按激活供应商调用 | `features/accounts/service.py` | `providers`、`provider_*` |
| 记忆 | 命中检索 → 注入提示词；对话后异步抽取；定时清理噪声 | `features/chat/memory.py` | `memories`、`memory_*` |
| 情绪值 | 每条消息异步解析（规则 + LLM），更新喜怒哀乐与好感；生成时注入语气 | `features/emotion/service.py` | `emotion`、`affect_log` |
| 恐慌状态机 | 主动联系未回复 → 定时升级 → 阈值发消息 → 100 判被抛弃 → 用户哄回 | emotion | `panic` |
| 无聊值 | 无互动递增、互动递减（超管大减）；≥75 主动找超管 | emotion | `settings` |
| 人格词条 | 每日从交互提炼 2/4/8 字词条，限速 4 单位/天 | emotion | `persona_traits` |
| 关系识别 | 称呼关键词判断父子/兄妹/姐弟/夫妻等，注入关系提示 | emotion | `relationships` |
| 黑话 | 从群聊学习口头禅，按频率使用 | `features/style/service.py` | `slang_terms` |
| 无聊模式 | 冷场时发无聊语句/表情，间隔可配 | style | `bored_lines` |
| 怼人 | 按等级和对象回怼 | style | `roast_*` |
| 唤醒 | 主动开话题的唤醒池、额外池、冷却 | style | `wake_*` |

---

## 二、已实现：群管理

| 功能 | 怎么实现 | 入口/文件 | 数据与配置 |
|---|---|---|---|
| 刷屏巡查 | 滑动窗口统计条数/重复率，超阈值禁言；可选 AI 判定 | `features/group/service.py` | `gm_patrol_*` |
| 踢人/禁言指令 | `@某人 踢出群聊/加入黑名单`、`@某人 十分钟`；校验发送者权限与机器人管理员身份 | group | `gm_kick_*`、`gm_mute_enabled` |
| 进群自动通过/验证 | 申请事件 → 黑名单拒绝；自动通过 → 随机抽题私聊；5 分钟超时 2 次机会 | group | `join_verify`、`gm_questions` |
| 群黑名单 | 按群独立，命中拒绝进群 + 踢出 | group | `group_cfg.gm_blacklist` |
| 关键词频次 | `关键词\|秒数\|条数`，窗口内超限撤回并提示 | group | `gm_kwlimit_rules` |
| 违规词撤回 | 消息命中关键词直接撤回，可通知 | group | `gm_recall_*` |
| 处罚通知 | 禁言/踢人/拉黑后私聊配置的 QQ | group | `gm_punish_qqs` |
| 群面板外链 | 每群独立 token + 账号密码，页面复用后台模板；支持一键登录 | `features/panel/service.py` | `group_panel`、`group_cfg` |

---

## 三、已实现：媒体与娱乐

| 功能 | 怎么实现 | 入口/文件 | 数据与配置 |
|---|---|---|---|
| 表情包发送 | 按概率附带；随机或按语义智能匹配；URL 公开可访问 | `features/sticker/service.py` | `stickers` |
| 表情包导入 | 下载 zip → 解压 → 去重入库 → 状态持久化 + 轮询 | sticker | `sticker_pack_url` |
| 表情收录 | 群里发表情自动收藏（可开关） | sticker | `capture_*` |
| 生图 | 文本/参考图 → 供应商（硅基流动/智谱）→ 返回图片；含自拍提示词 | `features/image/service.py` | `image_*` |
| 语音 | TTS 合成、ASR 转写、波形裁剪、Breeze/智谱引擎 | `features/voice/service.py` | `voice_*` |
| 点歌/唱歌 | 搜索歌曲 → 发音乐卡片；唱歌走 TTS 合成后发送 | `features/music/service.py` | `music_*` |
| 撤回上报 | 监听撤回事件 → 私聊超管（含来源、时间、内容、图片） | `features/recall/service.py` | `recall_*` |
| 剧本杀 | 剧本库、开局、回合制推进、玩家管理、状态存档 | `features/game/service.py` | `scripts`、`runs` |

---

## 四、已实现：B 站

| 功能 | 怎么实现 | 入口/文件 | 数据与配置 |
|---|---|---|---|
| BV/链接解析 | 正则取 BV；短链跟随跳转；调 view 接口取标题/UP/播放/封面 | `features/bili/service.py` | `bili_enabled` |
| 热门 | 调 popular 接口取前 5 | bili | — |
| B站学习 | 搜索 → 取前 N → 拉详情与字幕 → LLM 总结 → 存笔记 | bili | `bili_count`、`bili_notes` |
| 自动学习 | 时间窗口 + 主题轮换 + 按视频时长控制节奏 + 每日上限 | bili | `bili_auto_*` |
| 主动找话题 | 学习笔记 → 按用户活跃时段私聊搭话 | bili | `bili_proactive_*` |
| 笔记查询 | 按关键词检索笔记并回复 | bili | `bili_notes` |

---

## 五、已实现：后台与运维

| 功能 | 怎么实现 | 入口/文件 | 数据与配置 |
|---|---|---|---|
| 登录与权限 | 账号密码哈希校验 → 会话 Cookie → 角色（super/admin/user）路由拦截 | `platforms/admin.py` | `admins`、`login_logs` |
| 静态单页后台 | index.html + css + js，按钮调 `/api/*` | `web/` | — |
| 接口自检 | 52 个接口逐个请求并报告失败项 | admin | — |
| 功能自检 | 14 项真实功能验证（记忆/白名单/关键词/解析/连通性） | admin | — |
| 测试模式 | 开启后所有出站消息改发超管，加前缀标识 | admin | `test_redirect*` |
| 版本更新 | 检查 latest.json → 下载 → sha 校验 → 目录包/单文件更新 → 重启 | admin + `platforms/web.py` | `update_*` |
| 账号与供应商 | 多管理员、多供应商、API Key、端点管理 | `features/accounts/service.py` | `providers` |
| 聊天规则配置 | 白名单、关键词、前缀、自动回复、频率、休息、好友、黑名单 | `features/config/service.py` | 多表 |
| 租户托管 | 创建租户容器、启动/停止、二维码、密码、远程部署 | `features/hosting/service.py` | `hosting_*` |
| 省钱模式 | 余额低于阈值自动精简回复、暂停非必要调用；后台可手动开关 | `features/economy/service.py` | `economy_*` |
| 余额提醒 | 余额分级提醒超管充值，充值后恢复 | economy | `ai_balance_*` |
| 运行与备份 | 定时备份数据库、清理过期数据、统计与令牌用量 | `features/runtime/service.py` | — |

---

## 六、已实现：工程能力

| 能力 | 实现 |
|---|---|
| 模块化 | `fishpond/{core,platforms,features,web}`，18 个功能模块，入口 bot.py 90KB |
| 功能索引 | `registry` 注册 + 自动生成 `INDEX.md`（51 项） |
| 构建校验 | `check_index.py`：入口/路由/表/模块/INDEX/前端/包完整性，错误阻断构建 |
| 发布冒烟 | `smoke_http.py`：临时实例 + 假登录 + 并发 GET 51 接口，5xx/401 阻断发布 |
| 目录包更新 | tar.gz 校验/解压/备份/回滚；单文件版内嵌模块包兼容老版本 |
| 不打包工具 | 构建排除 `fishpond/tools`，用户包只有运行代码 |

---

## 七、计划实现（尚未做）

| 功能 | 实现方式 | 依赖 | 工作量 | 风险/说明 |
|---|---|---|---|---|
| B站扫码登录 | 生成二维码 → 轮询扫码状态 → 保存 Cookie → 用于追番/历史/收藏 | B站 passport 接口 | 2~3 天 | 账号安全，建议只给超管 |
| 追番/历史/动态 | 用登录 Cookie 调对应接口，定时推送更新 | 上一条 | 1~2 天 | 接口变动风险中 |
| 抖音链接解析 | 短链跳转取 aweme_id → 调详情接口 → 标题/作者/封面/描述摘要 | 抖音接口 | 1 天 | 无官方 API，可能失效 |
| 抖音搜索/热门 | 需要签名参数，稳定性差 | 逆向签名 | 2~3 天 | 不建议优先做 |
| 世界引擎 P0 | 世界时钟 + 地点 + 日程 + 事件日志 + 只读面板 | 现有存储/LLM | 1~2 周 | 与情绪系统打通需设计 |
| 世界引擎 P1 | 需求/目标、3~5 个 NPC、信息边界、世界驱动主动行为 | P0 | 2~3 周 | 成本与一致性控制 |
| 校验增强 | 反向路由检查、提醒升级阻断、git pre-commit、CI | 现有工具 | 0.5~1 天 | 低风险 |
| 冒烟扩展 | POST 接口、权限矩阵（viewer/admin）、真实 OneBot 连通冒烟 | 现有工具 | 1~2 天 | 需要隔离测试数据 |
| 群管理增强 | 投票、定时公告、入群欢迎图/语音 | 现有群模块 | 3~5 天 | 需求待确认 |
| 省钱模式细化 | 按各模型单价和剩余额度动态阈值 | 供应商价格表 | 1~2 天 | 价格需维护 |
| 空间发说说 | 网页 Cookie + `p_skey/g_tk` 模拟发布 | 用户 Cookie | 2~3 天 | **高风险，不建议给机器人号** |

---

## 八、建议优先级

1. **校验增强 + 冒烟扩展**（1~2 天，直接减少线上故障）
2. **B站扫码登录 + 追番**（3~5 天，用户可感知）
3. **群管理增强**（按你实际需求挑）
4. **世界引擎 P0**（1~2 周，大工程，先出详细设计再动手）
5. 抖音/空间：低优先或不做

---

> 说明：本表基于 3.11.1 实际代码与 `INDEX.md` 整理；`INDEX.md` 由工具自动生成，如与代码不一致，构建会直接失败。
