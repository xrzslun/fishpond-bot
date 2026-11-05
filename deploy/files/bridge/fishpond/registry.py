"""功能注册表：全项目功能索引的唯一来源。

每个功能模块用 @feature(...) 注册，tools/make_index.py 扫描后生成 INDEX.md。
重构期间尚未拆分的功能先以静态条目登记，迁移完成后再改成模块注册。
"""

FEATURES: list[dict] = []


def feature(**meta):
    """装饰器：登记一个功能。"""
    def deco(fn):
        item = dict(meta)
        item.setdefault("entry", f"{fn.__module__}:{fn.__name__}")
        item.setdefault("status", "active")
        FEATURES.append(item)
        return fn
    return deco


def add(**meta):
    FEATURES.append(dict(meta))


# ---- 过渡期静态清单（迁移后逐条删除，改由模块注册） ----
_STATIC = [
    # id, name, entry, routes, tables, settings, ui, files
    ("chat.reply", "对话回复", "handle_message / ask_deepseek", [], ["memories"], ["reply_*"], "聊天/接话模式", "bridge/bot_admin.py"),
    ("chat.persona", "人设", "persona_text", [], [], ["persona_*"], "机器人/人设", "bridge/bot_admin.py"),
    ("chat.memory", "记忆", "memory_prompt / mem_add", [], ["memories"], ["memory_*"], "机器人/记忆", "bridge/bot_admin.py"),
    ("chat.voice", "语音", "voice_*", ["/api/voice", "/api/voice/preview"], [], ["voice_*"], "机器人/语音", "bridge/bot_admin.py"),
    ("chat.image", "生图", "image_*", ["/api/image"], [], ["image_*"], "机器人/生图", "bridge/bot_admin.py"),
    ("group.patrol", "刷屏巡查", "gm_patrol", [], ["group_cfg"], ["gm_patrol_*"], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("group.mute", "禁言指令", "handle_mute_command", [], [], ["gm_mute_enabled"], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("group.kick", "踢人指令", "handle_kick_command", [], [], ["gm_kick_*"], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("group.verify", "进群验证", "handle_group_request / handle_verify_reply", [], ["join_verify"], ["gm_verify", "gm_questions"], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("group.blacklist", "群黑名单", "gm_black / group_black_*", [], ["group_cfg.gm_blacklist", "group_blacklist"], [], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("group.kwlimit", "关键词频次", "gm_kwlimit_check", [], [], ["gm_kwlimit_rules"], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("group.recall_kw", "违规词撤回", "handle_message 内联", [], [], ["gm_recall_enabled", "gm_recall_keywords"], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("recall.report", "撤回上报", "handle_recall", [], [], ["recall_*"], "超级管理员/撤回", "bridge/bot_admin.py"),
    ("panel.group", "群面板外链", "gpage_html / api_gcfg / api_glogin / api_gbl", ["/g/{token}/", "/api/gm/groups"], ["group_panel", "group_cfg"], [], "聊天/群聊管理", "bridge/bot_admin.py"),
    ("bili.parse", "B站解析", "handle_bili", [], [], ["bili_enabled"], "机器人/B站", "bridge/bot_admin.py"),
    ("bili.learn", "B站学习", "bili_learn / handle_bili", [], ["bili_notes"], ["bili_count"], "机器人/B站", "bridge/bot_admin.py"),
    ("bili.auto", "B站自动学习", "bili_auto_loop / bili_auto_step", [], ["bili_notes"], ["bili_auto_*"], "机器人/B站", "bridge/bot_admin.py"),
    ("bili.proactive", "主动找话题", "bili_proactive_loop / bili_proactive_step", [], ["bili_notes", "memories"], ["bili_proactive_*"], "机器人/B站", "bridge/bot_admin.py"),
    ("economy.balance", "余额提醒", "balance_panic_loop / balance_alert", [], [], ["ai_balance_*"], "超级管理员/基本设置", "bridge/bot_admin.py"),
    ("economy.savings", "省钱模式", "balance_tight / api_economy_config", ["/api/economy/config"], [], ["economy_*"], "超级管理员/基本设置", "bridge/bot_admin.py"),
    ("emotion.core", "情绪值", "emotion_note / affect_*", [], ["emotion", "affect_log"], [], "（隐藏）", "bridge/bot_admin.py"),
    ("emotion.panic", "恐慌状态机", "panic_loop / panic_step", [], ["panic"], [], "（隐藏）", "bridge/bot_admin.py"),
    ("emotion.boredom", "无聊值", "boredom_loop / boredom_touch", [], ["settings"], [], "（隐藏）", "bridge/bot_admin.py"),
    ("emotion.traits", "人格词条", "traits_* / trait_loop", [], ["persona_traits"], [], "（隐藏）", "bridge/bot_admin.py"),
    ("emotion.relation", "关系识别", "rel_detect / rel_note", [], ["relationships"], [], "（隐藏）", "bridge/bot_admin.py"),
    ("sticker.pack", "表情包导入", "api_stickers_install_pack / _install_sticker_pack", ["/api/stickers/*"], ["stickers"], ["sticker_*"], "聊天/表情包", "bridge/bot_admin.py"),
    ("sticker.capture", "表情收录", "capture_*", [], ["stickers"], ["capture_*"], "超级管理员/表情收录", "bridge/bot_admin.py"),
    ("admin.auth", "后台登录", "api_login / role_middleware", ["/api/login"], ["admins", "login_logs"], [], "登录页", "bridge/bot_admin.py"),
    ("admin.testmode", "测试模式", "api_testmode / test_redirect_target", ["/api/testmode"], ["settings"], ["test_redirect*"], "超级管理员/测试模式", "bridge/bot_admin.py"),
    ("admin.selfcheck", "接口/功能自检", "api_selfcheck / api_featurecheck_run", ["/api/selfcheck/run", "/api/featurecheck/run"], [], [], "超级管理员/自检", "bridge/bot_admin.py"),
    ("game.script", "剧本杀", "game_*", ["/api/game/*"], ["scripts", "runs", "game_contexts"], ["game_*"], "聊天/剧本杀", "bridge/bot_admin.py"),
    ("hosting.tenant", "租户托管", "hosting/admin.py", [], [], [], "租户页", "hosting/admin.py"),
    ("update.release", "自动更新", "api_update_*", ["/updates/{name}"], [], ["app_version"], "超级管理员/更新", "bridge/bot_admin.py"),
]

for _id, _name, _entry, _routes, _tables, _settings, _ui, _files in _STATIC:
    add(id=_id, name=_name, entry=_entry, routes=_routes, tables=_tables,
        settings=_settings, ui=_ui, files=_files, status="legacy")
