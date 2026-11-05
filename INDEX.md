# 功能索引（自动生成，勿手改）

共 58 项。修改功能请同步 registry。

| 功能 ID | 名称 | 入口 | 接口 | 数据表 | 配置键 | 页面 | 文件 |
|---|---|---|---|---|---|---|---|
| accounts.providers | 账号与模型供应商 | `fishpond.features.accounts.service:AccountsMixin` | /api/accounts/*<br>/api/providers/*<br>/api/apikey/*<br>/api/end-phrase/* | providers | provider_* | 账号/模型 | `fishpond/features/accounts/service.py` |
| admin.rollback | 升级回滚 | `fishpond.platforms.admin:AdminMixin` | /api/rollback | — | — | 超级管理员/基本设置 | `fishpond/platforms/admin.py` |
| admin.update | 版本更新 | `fishpond.platforms.admin:AdminMixin` | /api/update/* | — | update_*<br>app_version | 超级管理员/更新 | `fishpond/platforms/admin.py` |
| appapi | App 客户端接口 | `fishpond/features/appapi/service.py` | /api/app/home<br>/api/app/chat/history<br>/api/app/chat/send | app_chat | — | App 原生客户端 | `fishpond/features/appapi/service.py` |
| bili.account | B站账号实况 | `fishpond/features/biliacct/service.py` | /api/bili/account/status<br>/api/bili/account/config<br>/api/bili/account/qr<br>/api/bili/account/qr/poll<br>/api/bili/account/action<br>/api/bili/account/logs<br>/api/bili/account/cookies | — | bili_acct_* | 机器人/B站 | `['fishpond/features/biliacct/service.py']` |
| bili.auto | B站自动学习 | `fishpond.features.bili.service:bili_auto_loop` | — | bili_notes | bili_auto_* | 机器人/B站 | `fishpond/features/bili/service.py` |
| bili.config | B站配置接口 | `fishpond.features.bili.service:api_bili_config` | /api/bili/config | — | bili_* | 机器人/B站 | `fishpond/features/bili/service.py` |
| bili.learn | B站学习 | `fishpond.features.bili.service:bili_learn` | — | bili_notes | bili_count | 机器人/B站 | `fishpond/features/bili/service.py` |
| bili.parse | B站解析 | `fishpond.features.bili.service:handle_bili` | — | — | bili_enabled | 机器人/B站 | `fishpond/features/bili/service.py` |
| bili.proactive | 主动找话题 | `fishpond.features.bili.service:bili_proactive_loop` | — | bili_notes<br>memories | bili_proactive_* | 机器人/B站 | `fishpond/features/bili/service.py` |
| chat.dispatch | 消息调度 | `fishpond.features.chat.dispatch:handle_message` | — | — | reply_*<br>rest_* | （核心） | `fishpond/features/chat/dispatch.py` |
| chat.memory | 记忆系统 | `fishpond.features.chat.memory:memory_prompt` | /api/memory/* | memories | memory_* | 机器人/记忆 | `fishpond/features/chat/memory.py` |
| chat.persona | 人设与对话 | `fishpond.features.chat.persona:ask_deepseek` | /api/personas/*<br>/api/persona/* | personas | persona_* | 机器人/人设 | `fishpond/features/chat/persona.py` |
| config.chat | 聊天规则配置 | `fishpond.features.config.service:ConfigMixin` | /api/whitelist/*<br>/api/keywords/*<br>/api/prefix/*<br>/api/auto/*<br>/api/group-rate/*<br>/api/rest/* | wl_groups<br>wl_users<br>keywords<br>prefix_map<br>auto_users<br>settings | * | 聊天/白名单等 | `fishpond/features/config/service.py` |
| core.runtime | 运行与备份 | `fishpond.features.runtime.service:run` | /api/status<br>/api/tokens | — | app_version | （核心） | `fishpond/features/runtime/service.py` |
| economy.balance | 余额提醒 | `fishpond.features.economy.service:balance_panic_loop` | — | — | ai_balance_* | 超级管理员/基本设置 | `fishpond/features/economy/service.py` |
| economy.savings | 省钱模式 | `fishpond.features.economy.service:balance_tight` | /api/economy/config | — | economy_* | 超级管理员/基本设置 | `fishpond/features/economy/service.py` |
| emotion.boredom | 无聊值 | `fishpond.features.emotion.service:boredom_loop` | — | settings | — | （隐藏） | `fishpond/features/emotion/service.py` |
| emotion.core | 情绪值 | `fishpond.features.emotion.service:affect_process` | — | emotion<br>affect_log | — | （隐藏） | `fishpond/features/emotion/service.py` |
| emotion.panic | 恐慌状态机 | `fishpond.features.emotion.service:panic_loop` | — | panic | — | （隐藏） | `fishpond/features/emotion/service.py` |
| emotion.relation | 关系识别 | `fishpond.features.emotion.service:rel_detect` | — | relationships | — | （隐藏） | `fishpond/features/emotion/service.py` |
| emotion.traits | 人格词条 | `fishpond.features.emotion.service:trait_loop` | — | persona_traits | — | （隐藏） | `fishpond/features/emotion/service.py` |
| game.script | 剧本杀 | `fishpond.features.game.service:game_turn` | /api/game/* | scripts<br>runs<br>game_contexts | game_* | 聊天/剧本杀 | `fishpond/features/game/service.py` |
| group.blacklist | 群黑名单 | `fishpond.features.group.service:gm_black` | /api/gm/blacklist | group_blacklist<br>group_cfg | — | 聊天/群聊管理 | `fishpond/features/group/service.py` |
| group.kick | 踢人与禁言 | `fishpond.features.group.service:handle_kick_command` | — | — | gm_kick_*<br>gm_mute_enabled | 聊天/群聊管理 | `fishpond/features/group/service.py` |
| group.kwlimit | 关键词频次 | `fishpond.features.group.service:gm_kwlimit_check` | — | — | gm_kwlimit_rules | 聊天/群聊管理 | `fishpond/features/group/service.py` |
| group.patrol | 刷屏巡查 | `fishpond.features.group.service:gm_patrol` | — | group_cfg | gm_patrol_* | 聊天/群聊管理 | `fishpond/features/group/service.py` |
| group.verify | 进群验证 | `fishpond.features.group.service:handle_group_request` | — | join_verify | gm_verify<br>gm_questions | 聊天/群聊管理 | `fishpond/features/group/service.py` |
| hosting.nodes | 托管节点 | `fishpond.features.hosting.service:HostingMixin` | /api/hosting/* | — | hosting_* | 租户 | `fishpond/features/hosting/service.py` |
| image.core | 生图 | `fishpond.features.image.service:prepare_images` | — | — | image_* | 机器人/生图 | `fishpond/features/image/service.py` |
| music.core | 点歌与唱歌 | `fishpond.features.music.service:handle_music` | /api/music<br>/api/music/config | — | music_* | 聊天/接话模式 | `fishpond/features/music/service.py` |
| panel.group | 群面板外链 | `fishpond.features.panel.service:gpage_html` | /g/{token}/<br>/api/gm/groups<br>/api/gm/config | group_panel<br>group_cfg | — | 聊天/群聊管理 | `fishpond/features/panel/service.py` |
| platform.onebot | OneBot 连接 | `fishpond.platforms.onebot:OneBotMixin` | — | — | onebot_* | 后台整体 | `fishpond/platforms/onebot.py` |
| platform.web | 管理后台服务 | `fishpond.platforms.web:WebMixin` | / | — | webui_* | 后台整体 | `fishpond/platforms/web.py` |
| recall.core | 撤回上报 | `fishpond.features.recall.service:recall_window_ok` | — | — | recall_* | 机器人/超级管理员/撤回 | `fishpond/features/recall/service.py` |
| runtime.diag | 诊断包 | `fishpond.features.runtime.service:api_diag_pack` | /api/diag/pack | — | — | 超级管理员/基本设置 | `fishpond/features/runtime/service.py` |
| runtime.errors | 错误面板 | `fishpond.features.runtime.service:api_errors` | /api/errors | — | — | 超级管理员/基本设置 | `fishpond/features/runtime/service.py` |
| runtime.health | 健康巡检 | `fishpond.features.runtime.service:health_loop` | /api/health | — | — | 超级管理员/基本设置 | `fishpond/features/runtime/service.py` |
| sticker.pack | 表情包导入 | `fishpond.features.sticker.service:_install_sticker_pack` | /api/stickers/install_pack | stickers | sticker_pack_url | 聊天/表情包 | `fishpond/features/sticker/service.py` |
| sticker.send | 表情包发送 | `fishpond.features.sticker.service:maybe_send_sticker` | /api/stickers<br>/api/stickers/* | stickers | sticker_* | 聊天/表情包 | `fishpond/features/sticker/service.py` |
| style.bored | 无聊模式 | `fishpond.features.style.service:bored_loop` | /api/bored/* | bored_lines | bored_* | 聊天/无聊模式 | `fishpond/features/style/service.py` |
| style.roast | 怼人 | `fishpond.features.style.service:handle_roast` | — | — | roast_* | 机器人/人设 | `fishpond/features/style/service.py` |
| style.slang | 黑话 | `fishpond.features.style.service:slang_learn` | /api/slang/* | slang_terms | slang_* | 机器人/黑话 | `fishpond/features/style/service.py` |
| style.wake | 唤醒 | `fishpond.features.style.service:handle_wake` | /api/wake/* | — | wake_* | 聊天/接话模式 | `fishpond/features/style/service.py` |
| voice.core | 语音 | `fishpond.features.voice.service:voice_context` | — | — | voice_* | 机器人/语音 | `fishpond/features/voice/service.py` |
| world.engine | 世界引擎 | `fishpond.features.world.service:WorldMixin` | /api/world/state<br>/api/world/config<br>/api/world/tasks<br>/api/world/check<br>/api/world/trend<br>/api/world/summary<br>/api/weather<br>/api/weather/loc<br>/api/bili/account/status<br>/api/bili/account/config<br>/api/bili/account/qr<br>/api/bili/account/qr/poll<br>/api/bili/account/action<br>/api/bili/account/logs | world_state<br>world_events | world_enabled<br>world_scale | 机器人/世界 | `fishpond/features/world/service.py` |
| admin.auth | 后台登录 | `api_login / role_middleware` | /api/login | admins<br>login_logs | — | 登录页 | `bridge/bot_admin.py` |
| admin.selfcheck | 接口/功能自检 | `api_selfcheck / api_featurecheck_run` | /api/selfcheck/run<br>/api/featurecheck/run | — | — | 超级管理员/自检 | `bridge/bot_admin.py` |
| admin.testmode | 测试模式 | `api_testmode / test_redirect_target` | /api/testmode | settings | test_redirect* | 超级管理员/测试模式 | `bridge/bot_admin.py` |
| chat.image | 生图 | `image_*` | /api/image | — | image_* | 机器人/生图 | `bridge/bot_admin.py` |
| chat.reply | 对话回复 | `handle_message / ask_deepseek` | — | memories | reply_* | 聊天/接话模式 | `bridge/bot_admin.py` |
| chat.voice | 语音 | `voice_*` | /api/voice<br>/api/voice/preview | — | voice_* | 机器人/语音 | `bridge/bot_admin.py` |
| group.mute | 禁言指令 | `handle_mute_command` | — | — | gm_mute_enabled | 聊天/群聊管理 | `bridge/bot_admin.py` |
| group.recall_kw | 违规词撤回 | `handle_message 内联` | — | — | gm_recall_enabled<br>gm_recall_keywords | 聊天/群聊管理 | `bridge/bot_admin.py` |
| hosting.tenant | 租户托管 | `hosting/admin.py` | — | — | — | 租户页 | `hosting/admin.py` |
| recall.report | 撤回上报 | `handle_recall` | — | — | recall_* | 超级管理员/撤回 | `bridge/bot_admin.py` |
| sticker.capture | 表情收录 | `capture_*` | — | stickers | capture_* | 超级管理员/表情收录 | `bridge/bot_admin.py` |
| update.release | 自动更新 | `api_update_*` | /updates/{name} | — | app_version | 超级管理员/更新 | `bridge/bot_admin.py` |

> 状态 `legacy` 表示仍在单文件里，迁移后会变为 `active` 并由模块注册。
