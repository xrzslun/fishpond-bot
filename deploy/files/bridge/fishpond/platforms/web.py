"""平台层：Web 管理后台路由与服务器。"""
import asyncio
import json
import os
import re
import time
from pathlib import Path

import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


def _base_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    if (root / "bot.py").is_file():
        return root
    alt = root / "bridge"
    return alt if alt.is_dir() else root


BASE = _base_dir()


class WebMixin:
    def webui_prefix(self) -> str:
        p = (getattr(self, "webui_path", "/") or "/").strip()
        if p in ("", "/"):
            return ""
        return "/" + p.strip("/")

    def _web_dir(self):
        import pathlib as _pl
        for b in (BASE, _pl.Path(__file__).resolve().parent):
            d = b / "web"
            if d.is_dir():
                return d
        return None

    async def serve_web_file(self, request):
        import mimetypes as _mt
        tail = str(request.match_info.get("tail") or "").lstrip("/")
        d = self._web_dir()
        if not d:
            raise aiohttp_web.HTTPNotFound()
        root = d.resolve()
        target = (d / tail).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            raise aiohttp_web.HTTPNotFound()
        ct = _mt.guess_type(str(target))[0] or "application/octet-stream"
        return aiohttp_web.Response(body=target.read_bytes(), content_type=ct,
                                    headers={"Cache-Control": "no-cache"})

    def register_admin_routes(self, app):
        app.router.add_get("/", self.page_index)
        app.router.add_post("/api/login", self.api_login)
        app.router.add_post("/api/logout", self.api_logout)
        app.router.add_get("/api/me", self.api_me)
        app.router.add_get("/api/accounts", self.api_accounts_get)
        app.router.add_post("/api/accounts/create", self.api_accounts_create)
        app.router.add_post("/api/accounts/update", self.api_accounts_update)
        app.router.add_post("/api/accounts/delete", self.api_accounts_delete)
        app.router.add_get("/api/login-logs", self.api_login_logs)
        app.router.add_get("/api/status", self.api_status)
        app.router.add_get("/api/logs", self.api_logs)
        app.router.add_get("/api/world/state", self.api_world_state)
        app.router.add_get("/api/app/ping", self.api_app_ping)
        app.router.add_get("/api/app/tunnel", self.api_app_tunnel)
        app.router.add_get("/api/app/sso", self.api_app_sso)
        app.router.add_get("/api/app/home", self.api_app_home)
        app.router.add_get("/api/app/chat/history", self.api_app_history)
        app.router.add_post("/api/app/chat/send", self.api_app_send)
        app.router.add_post("/api/world/config", self.api_world_config)
        app.router.add_get("/api/world/check", self.api_world_check)
        app.router.add_get("/api/world/tasks", self.api_world_tasks)
        app.router.add_get("/api/world/trend", self.api_world_trend)
        app.router.add_get("/api/world/summary", self.api_world_summary)
        app.router.add_get("/api/weather", self.api_weather)
        app.router.add_post("/api/weather/loc", self.api_weather_loc)
        app.router.add_get("/api/health", self.api_health)
        app.router.add_get("/api/errors", self.api_errors)
        app.router.add_get("/api/diag/pack", self.api_diag_pack)
        app.router.add_post("/api/rollback", self.api_rollback)
        app.router.add_get("/api/tokens", self.api_tokens)
        app.router.add_get("/api/testmode", self.api_testmode)
        app.router.add_post("/api/test/send", self.api_test_send)
        app.router.add_post("/api/testmode", self.api_testmode)
        app.router.add_post("/api/selfcheck/run", self.api_selfcheck_run)
        app.router.add_post("/api/featurecheck/run", self.api_featurecheck_run)
        app.router.add_post("/api/napcat/restart", self.api_napcat_restart)
        app.router.add_post("/api/qr", self.api_qr)
        app.router.add_get("/api/whitelist", self.api_wl_get)
        app.router.add_post("/api/whitelist/add", self.api_wl_add)
        app.router.add_post("/api/whitelist/remove", self.api_wl_remove)
        app.router.add_post("/api/whitelist/update", self.api_wl_update)
        app.router.add_get("/api/keywords", self.api_kw_get)
        app.router.add_post("/api/keywords/add", self.api_kw_add)
        app.router.add_post("/api/keywords/remove", self.api_kw_remove)
        app.router.add_get("/api/prefix", self.api_pf_get)
        app.router.add_post("/api/prefix/add", self.api_pf_add)
        app.router.add_post("/api/prefix/remove", self.api_pf_remove)
        app.router.add_post("/api/prefix/toggle", self.api_pf_toggle)
        app.router.add_get("/api/auto", self.api_auto_get)
        app.router.add_post("/api/auto/toggle", self.api_auto_toggle)
        app.router.add_post("/api/auto/add", self.api_auto_add)
        app.router.add_post("/api/auto/remove", self.api_auto_remove)
        app.router.add_get("/api/bored", self.api_bored_get)
        app.router.add_post("/api/bored/config", self.api_bored_config)
        app.router.add_get("/api/bored/lines", self.api_bored_lines)
        app.router.add_post("/api/bored/lines/add", self.api_bored_add)
        app.router.add_post("/api/bored/lines/remove", self.api_bored_remove)
        app.router.add_get("/api/group-reply", self.api_gr_get)
        app.router.add_post("/api/group-reply/config", self.api_gr_config)
        app.router.add_post("/api/group-reply/always", self.api_gr_always)
        app.router.add_get("/api/conversations", self.api_convos)
        app.router.add_post("/api/conversations/remove", self.api_convo_remove)
        app.router.add_get("/api/group-rate", self.api_rate_get)
        app.router.add_post("/api/group-rate/save", self.api_rate_save)
        app.router.add_post("/api/group-rate/segconfig", self.api_seg_config)
        app.router.add_post("/api/group-rate/reset", self.api_rate_reset)

        app.router.add_get("/api/update", self.api_update_get)
        app.router.add_post("/api/update/check", self.api_update_check)
        app.router.add_post("/api/update/apply", self.api_update_apply)
        app.router.add_post("/api/update/config", self.api_update_config)
        app.router.add_get("/api/bot-profile", self.api_bot_profile)
        app.router.add_post("/api/bot-profile/nick", self.api_bot_nick)
        app.router.add_post("/api/bot-profile/avatar", self.api_bot_avatar)
        app.router.add_get("/api/blacklist", self.api_blacklist_get)
        app.router.add_post("/api/blacklist/add", self.api_blacklist_add)
        app.router.add_post("/api/blacklist/remove", self.api_blacklist_remove)
        app.router.add_get("/api/rest", self.api_rest_get)
        app.router.add_post("/api/rest/wl", self.api_rest_wl)
        app.router.add_post("/api/rest/import", self.api_rest_import)
        app.router.add_post("/api/rest/notify-groups", self.api_rest_notify_groups)
        app.router.add_post("/api/rest/config", self.api_rest_config)
        app.router.add_get("/api/super", self.api_super_get)
        app.router.add_get("/api/friend", self.api_friend_get)
        app.router.add_get("/api/wake", self.api_wake_get)
        app.router.add_get("/api/slang", self.api_slang_get)
        app.router.add_get("/api/image", self.api_image_get)
        app.router.add_post("/api/image/config", self.api_image_config)
        app.router.add_post("/api/image/test", self.api_image_test)
        app.router.add_get("/api/music", self.api_music_get)
        app.router.add_post("/api/music/config", self.api_music_config)
        app.router.add_post("/api/slang/config", self.api_slang_config)
        app.router.add_post("/api/slang/add", self.api_slang_add)
        app.router.add_post("/api/slang/delete", self.api_slang_delete)
        app.router.add_post("/api/slang/update", self.api_slang_update)
        app.router.add_post("/api/slang/delete_many", self.api_slang_delete_many)
        app.router.add_post("/api/slang/optimize", self.api_slang_optimize)
        app.router.add_post("/api/wake/config", self.api_wake_config)
        app.router.add_post("/api/friend/config", self.api_friend_config)
        app.router.add_post("/api/friend/action", self.api_friend_action)
        app.router.add_post("/api/super/config", self.api_super_config)
        app.router.add_get("/api/personas", self.api_personas_get)
        app.router.add_post("/api/personas/save", self.api_personas_save)
        app.router.add_post("/api/personas/delete", self.api_personas_delete)
        app.router.add_post("/api/personas/activate", self.api_personas_activate)
        app.router.add_get("/api/persona", self.api_persona_get)
        app.router.add_post("/api/persona/save", self.api_persona_save)
        app.router.add_post("/api/persona/gender", self.api_persona_gender)
        app.router.add_get("/api/memory", self.api_memory_get)
        app.router.add_get("/api/memory/noise_preview", self.api_memory_noise_preview)
        app.router.add_get("/api/memory/ai_review", self.api_memory_ai_review)
        app.router.add_get("/api/memory/ai_review/status", self.api_memory_review_status)
        app.router.add_post("/api/memory/delete_many", self.api_memory_delete_many)
        app.router.add_post("/api/memory/clean_noise", self.api_memory_clean_noise)
        app.router.add_post("/api/memory/add", self.api_memory_add)
        app.router.add_post("/api/memory/update", self.api_memory_update)
        app.router.add_post("/api/memory/delete", self.api_memory_delete)
        app.router.add_post("/api/memory/config", self.api_memory_config)
        app.router.add_post("/api/persona/reset", self.api_persona_reset)
        app.router.add_get("/api/voice", self.api_voice_get)
        app.router.add_post("/api/master/set_admin_password", self.api_master_set_admin_password)
        app.router.add_get("/api/hosting/list", self.api_hosting_list)
        app.router.add_get("/api/hosting/nodes", self.api_hosting_nodes)
        app.router.add_post("/api/hosting/add_node", self.api_hosting_add_node)
        app.router.add_post("/api/hosting/passwd", self.api_hosting_passwd)
        app.router.add_post("/api/hosting/create", self.api_hosting_create)
        app.router.add_post("/api/hosting/action", self.api_hosting_action)
        app.router.add_post("/api/hosting/qr", self.api_hosting_qr)
        app.router.add_post("/api/hosting/deploy_server", self.api_hosting_deploy_server)
        app.router.add_post("/api/game/rest_bypass", self.api_game_rest_bypass)
        app.router.add_get("/api/game/contexts", self.api_game_contexts)
        app.router.add_post("/api/game/context/kick", self.api_game_context_kick)
        app.router.add_get("/api/game/overview", self.api_game_overview)
        app.router.add_post("/api/game/player", self.api_game_player)
        app.router.add_get("/api/game/runs", self.api_game_runs)
        app.router.add_post("/api/game/run/select", self.api_game_run_select)
        app.router.add_get("/api/game/messages", self.api_game_messages)
        app.router.add_post("/api/game/script/save", self.api_game_script_save)
        app.router.add_post("/api/game/script/manage", self.api_game_script_manage)
        app.router.add_route("*", "/api/game/settings", self.api_game_settings)
        app.router.add_get("/api/scripts/public/list", self.api_scripts_public_list)
        app.router.add_get("/api/scripts/public/get/{sid}", self.api_scripts_public_get)
        app.router.add_post("/api/voice/keytest", self.api_voice_keytest)
        app.router.add_post("/api/voice/diag", self.api_voice_diag)
        app.router.add_post("/api/voice/preview", self.api_voice_preview)
        app.router.add_get("/api/voice/audio", self.api_voice_audio)
        app.router.add_post("/api/voice/config", self.api_voice_config)
        app.router.add_get("/api/providers", self.api_providers_get)
        app.router.add_get("/api/providers/balances", self.api_provider_balances)
        app.router.add_post("/api/providers/models", self.api_provider_models)
        app.router.add_post("/api/providers/save", self.api_providers_save)
        app.router.add_post("/api/providers/delete", self.api_providers_delete)
        app.router.add_post("/api/providers/activate", self.api_providers_activate)
        app.router.add_post("/api/providers/test", self.api_providers_test)
        app.router.add_post("/api/providers/autodetect", self.api_providers_autodetect)
        app.router.add_get("/api/apikey", self.api_apikey_get)
        app.router.add_post("/api/apikey/save", self.api_apikey_save)
        app.router.add_post("/api/apikey/test", self.api_apikey_test)
        app.router.add_get("/api/end-phrase", self.api_end_get)
        app.router.add_post("/api/end-phrase/config", self.api_end_config)
        app.router.add_post("/api/end-phrase/add", self.api_end_add)
        app.router.add_post("/api/end-phrase/remove", self.api_end_remove)
        app.router.add_get("/api/stickers", self.api_stickers)
        app.router.add_get("/api/stickerpack/info", self.api_stickerpack_info)
        app.router.add_get("/api/stickerpack/list", self.api_stickerpack_list)
        app.router.add_get("/api/stickerpack/file", self.api_stickerpack_file)
        app.router.add_post("/api/stickers/import_remote", self.api_stickers_import_remote)
        app.router.add_get("/api/stickers/import_status", self.api_stickers_import_status)
        app.router.add_post("/api/stickers/repair", self.api_stickers_repair)
        app.router.add_post("/api/stickers/upload", self.api_sticker_upload)
        app.router.add_post("/api/stickers/install_pack", self.api_stickers_install_pack)
        app.router.add_get("/api/stickers/install_status", self.api_stickers_install_status)
        app.router.add_get("/api/economy/config", self.api_economy_config)
        app.router.add_post("/api/economy/config", self.api_economy_config)
        app.router.add_get("/api/bili/config", self.api_bili_config)
        app.router.add_post("/api/bili/config", self.api_bili_config)
        app.router.add_get("/api/bili/account/status", self.api_bili_acct_status)
        app.router.add_post("/api/bili/account/config", self.api_bili_acct_config)
        app.router.add_get("/api/bili/account/qr", self.api_bili_acct_qr)
        app.router.add_get("/api/bili/account/qr/poll", self.api_bili_acct_qr_poll)
        app.router.add_post("/api/bili/account/cookies", self.api_bili_acct_cookies)
        app.router.add_post("/api/bili/account/action", self.api_bili_acct_action)
        app.router.add_get("/api/bili/account/logs", self.api_bili_acct_logs)
        app.router.add_get("/api/gm/groups", self.api_gm_groups)
        app.router.add_post("/api/gm/groups", self.api_gm_groups)
        app.router.add_get("/api/gm/blacklist", self.api_gm_blacklist)
        app.router.add_post("/api/gm/blacklist", self.api_gm_blacklist)
        app.router.add_get("/api/gm/config", self.api_gm_config)
        app.router.add_post("/api/gm/config", self.api_gm_config)
        app.router.add_get("/api/recall/config", self.api_recall_config)
        app.router.add_post("/api/recall/config", self.api_recall_config)
        app.router.add_post("/api/stickers/upload_many", self.api_sticker_upload_many)
        app.router.add_post("/api/stickers/add_urls", self.api_sticker_add_urls)
        app.router.add_post("/api/stickers/remove", self.api_sticker_remove)
        app.router.add_post("/api/stickers/desc", self.api_sticker_desc)
        app.router.add_post("/api/stickers/config", self.api_sticker_config)

        app.router.add_get("/api/admins", self.api_admins)
        app.router.add_post("/api/admins/add", self.api_admin_add)
        app.router.add_post("/api/admins/remove", self.api_admin_remove)

    async def start_admin_server(self):
        sub = aiohttp_web.Application()

        sub.middlewares.append(self.role_middleware())
        app = sub
        self.register_admin_routes(app)
        prefix = self.webui_prefix()
        if prefix:
            parent = aiohttp_web.Application()
            parent.add_subapp(prefix, sub)
            async def _redirect(request):
                raise aiohttp_web.HTTPFound(prefix + "/")
            parent.router.add_get(prefix, _redirect)
            app = parent
        app.router.add_get(prefix + "/web/{tail:.*}", self.serve_web_file)
        app.router.add_get(prefix + "/g/{token}/", self.gpage)
        app.router.add_post(prefix + "/g/{token}/login", self.api_glogin)
        app.router.add_get(prefix + "/g/{token}/api/config", self.api_gcfg)
        app.router.add_post(prefix + "/g/{token}/api/config", self.api_gcfg)
        app.router.add_get(prefix + "/g/{token}/admin_login", self.gadmin_login)
        app.router.add_get(prefix + "/g/{token}/api/blacklist", self.api_gbl)
        app.router.add_post(prefix + "/g/{token}/api/blacklist", self.api_gbl)
        app.router.add_get("/updates/{name}", self.api_update_file)
        app.router.add_get("/stickers/{name}", self.serve_sticker)

        try:
            _paths = set()
            for _r in app.router.routes():
                _res = getattr(_r, "resource", None)
                _can = str(getattr(_res, "canonical", "") or "")
                if _can.startswith("/api/"):
                    _paths.add(_can)
            self._route_total = len(_paths)
        except Exception:
            self._route_total = 0
        runner = aiohttp_web.AppRunner(app)
        await runner.setup()
        host = os.environ.get("FISHPOND_ADMIN_HOST", "127.0.0.1")
        port = int(os.environ.get("FISHPOND_ADMIN_PORT", "8099"))
        site = aiohttp_web.TCPSite(runner, host, port)
        await site.start()
        log.info("管理后台: http://%s:%s/", host, port)


add(id="platform.web", name="管理后台服务", entry="fishpond.platforms.web:WebMixin",
    routes=["/"], tables=[], settings=["webui_*"], ui="后台整体",
    files="fishpond/platforms/web.py", status="active")
