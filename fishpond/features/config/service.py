"""配置模块：白名单、关键词、前缀、自动回复、频率、休息、好友、黑名单。"""
import asyncio
import json
import re
import time

import aiohttp.web as aiohttp_web

from fishpond.core.config import VIEWER_FEATURE
from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


class ConfigMixin:
    async def api_wl_get(self, request):
        acc = self.require_role(request, "user")
        role = acc.get("role")
        aid = acc.get("id")
        rows = self.store.accounts_all()
        names = {r.get("id"): r.get("username") for r in rows}
        if role in ("super", "admin"):
            gids = self.store.groups(all_rows=True)
            uids = self.store.users(all_rows=True)
        else:
            gids = self.store.groups(created_by=aid)
            uids = self.store.users(created_by=aid)
        my = self.store.account_by_id(aid) or {}
        out_groups = []
        for g in gids:
            owner = self.store.wl_groups_owner(g)
            out_groups.append({"id": g, "owner": names.get(owner, ""), "mine": str(owner) == str(aid)})
        out_users = []
        for u in uids:
            owner = self.store.wl_users_owner(u)
            out_users.append({"id": u, "owner": names.get(owner, ""), "mine": str(owner) == str(aid)})
        return aiohttp_web.json_response({
            "code": 0,
            "role": role,
            "groups": out_groups,
            "users": out_users,
            "quota_groups": my.get("quota_groups"),
            "quota_users": my.get("quota_users"),
            "used_groups": self.store.wl_count("group", aid) if role != "super" else None,
            "used_users": self.store.wl_count("user", aid) if role != "super" else None,
        })

    async def api_wl_add(self, request):
        acc = self.require_role(request, "user")
        data = await request.json()
        kind, value = data.get("type"), str(data.get("value") or "").strip()
        if kind not in ("group", "user") or not value.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "请输入纯数字的群号或QQ号"})
        row = self.store.account_by_id(acc.get("id")) or {}
        limit = row.get("quota_groups") if kind == "group" else row.get("quota_users")
        if acc.get("role") != "super" and limit is not None:
            used = self.store.wl_count(kind, acc.get("id"))
            if used >= int(limit):
                return aiohttp_web.json_response({"code": -1, "message": f"已达到配额上限（{limit} 个）"})
        self.store.add_wl(kind, value, acc.get("id"))
        return aiohttp_web.json_response({"code": 0})

    async def api_wl_remove(self, request):
        acc = self.require_role(request, "user")
        data = await request.json()
        kind = data.get("type")
        value = str(data.get("value") or "").strip()
        if kind not in ("group", "user") or not value.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "参数错误"})
        owner = self.store.wl_groups_owner(value) if kind == "group" else self.store.wl_users_owner(value)
        if acc.get("role") == "user" and str(owner) != str(acc.get("id")):
            return aiohttp_web.json_response({"code": -1, "message": "只能删除自己添加的"})
        self.store.remove_wl(kind, value)
        return aiohttp_web.json_response({"code": 0})

    async def api_wl_update(self, request):
        acc = self.require_role(request, "user")
        data = await request.json()
        kind = data.get("type")
        old = str(data.get("old") or "").strip()
        new = str(data.get("new") or "").strip()
        if kind not in ("group", "user") or not old.isdigit() or not new.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "请输入纯数字"})
        owner = self.store.wl_groups_owner(old) if kind == "group" else self.store.wl_users_owner(old)
        if acc.get("role") == "user" and str(owner) != str(acc.get("id")):
            return aiohttp_web.json_response({"code": -1, "message": "只能修改自己添加的"})
        self.store.update_wl(kind, old, new)
        return aiohttp_web.json_response({"code": 0})

    async def api_kw_get(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({"code": 0, "keywords": self.store.keywords()})

    async def api_kw_add(self, request):
        self.require_auth(request)
        data = await request.json()
        word = str(data.get("word") or "").strip()
        if not word or len(word) > 20:
            return aiohttp_web.json_response({"code": -1, "message": "关键词不能为空且不超过 20 字"})
        self.store.add_keyword(word)
        return aiohttp_web.json_response({"code": 0})

    async def api_kw_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        self.store.remove_keyword(str(data.get("word") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_pf_get(self, request):
        self.require_auth(request)
        m = self.store.prefix_map()
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("prefix_enabled", "1") == "1",
            "prefixes": [{"qq": k, "prefix": v} for k, v in m.items()],
        })

    async def api_pf_toggle(self, request):
        self.require_auth(request)
        data = await request.json()
        enabled = bool(data.get("enabled"))
        self.store.set_setting("prefix_enabled", "1" if enabled else "0")
        return aiohttp_web.json_response({"code": 0, "enabled": enabled})

    async def api_pf_add(self, request):
        self.require_auth(request)
        data = await request.json()
        qq = str(data.get("qq") or "").strip()
        prefix = str(data.get("prefix") or "").strip()
        if not qq.isdigit() or not prefix:
            return aiohttp_web.json_response({"code": -1, "message": "QQ 号需为纯数字，前缀不能为空"})
        self.store.set_prefix(qq, prefix)
        return aiohttp_web.json_response({"code": 0})

    async def api_pf_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        self.store.remove_prefix(str(data.get("qq") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_auto_get(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("auto_reply_enabled", "1") == "1",
            "users": self.store.auto_users(),
        })

    async def api_auto_toggle(self, request):
        self.require_auth(request)
        data = await request.json()
        enabled = bool(data.get("enabled"))
        self.store.set_setting("auto_reply_enabled", "1" if enabled else "0")
        return aiohttp_web.json_response({"code": 0, "enabled": enabled})

    async def api_auto_add(self, request):
        self.require_auth(request)
        data = await request.json()
        qq = str(data.get("qq") or "").strip()
        if not qq.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "QQ 号需为纯数字"})
        self.store.add_auto_user(qq)
        return aiohttp_web.json_response({"code": 0})

    async def api_auto_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        self.store.remove_auto_user(str(data.get("qq") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_convo_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        gid = str(data.get("group_id") or "").strip()
        qq = str(data.get("qq") or "").strip()
        self.active_convos.pop((gid, qq), None)
        return aiohttp_web.json_response({"code": 0})

    async def api_rate_get(self, request):
        self.require_auth(request)
        whitelist = self.store.groups()
        try:
            default_max = int(self.store.get_setting("group_max_replies", str(self.group_max_replies)))
        except ValueError:
            default_max = self.group_max_replies
        default_min = int(self.min_interval)
        rates = []
        for gid in whitelist:
            row = self.store.get_rate(gid)
            if row:
                rates.append({"group_id": gid, "max_per_minute": row[0], "min_interval_seconds": row[1]})
        return aiohttp_web.json_response({
            "code": 0,
            "whitelist_empty": not bool(whitelist),
            "groups": whitelist,
            "default_max": default_max,
            "default_min": default_min,
            "first_delay_ms": int(float(self.store.get_setting("msg_first_delay_ms", "300") or 300)),
            "seg_delay_ms": int(float(self.store.get_setting("multi_msg_delay_ms", "600") or 600)),
            "sticker_delay_ms": int(float(self.store.get_setting("sticker_delay_ms", "800") or 800)),
            "seg_mode": self.store.get_setting("reply_seg_mode", "fixed"),
            "seg_fixed": int(float(self.store.get_setting("reply_seg_fixed", "2") or 2)),
            "seg_min": int(float(self.store.get_setting("reply_seg_min", "1") or 1)),
            "seg_max": int(float(self.store.get_setting("reply_seg_max", "3") or 3)),
            "rates": rates,
        })

    async def api_seg_config(self, request):
        self.require_super(request)   # 写配置统一要求超管
        data = await request.json()
        if data.get("mode") in ("fixed", "random"):
            self.store.set_setting("reply_seg_mode", data["mode"])
        try:
            if "fixed" in data:
                self.store.set_setting("reply_seg_fixed", str(max(1, min(10, int(float(data.get("fixed")))))))
            if "min" in data:
                self.store.set_setting("reply_seg_min", str(max(1, min(10, int(float(data.get("min")))))))
            if "max" in data:
                self.store.set_setting("reply_seg_max", str(max(1, min(10, int(float(data.get("max")))))))
            if "first_delay_ms" in data:
                self.store.set_setting("msg_first_delay_ms", str(max(0, min(10000, int(float(data.get("first_delay_ms")))))))
            if "seg_delay_ms" in data:
                self.store.set_setting("multi_msg_delay_ms", str(max(0, min(10000, int(float(data.get("seg_delay_ms")))))))
            if "sticker_delay_ms" in data:
                self.store.set_setting("sticker_delay_ms", str(max(0, min(10000, int(float(data.get("sticker_delay_ms")))))))
        except (TypeError, ValueError):
            return aiohttp_web.json_response({"code": -1, "message": "参数需为整数"})
        return aiohttp_web.json_response({"code": 0})

    async def api_rate_save(self, request):
        self.require_auth(request)
        data = await request.json()
        gid = str(data.get("group_id") or "").strip()
        if not gid.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "群号需为纯数字"})
        try:
            cap = int(float(data.get("max_per_minute")))
            interval = int(float(data.get("min_interval_seconds")))
        except (TypeError, ValueError):
            return aiohttp_web.json_response({"code": -1, "message": "请输入整数"})
        cap = max(1, min(200, cap))
        interval = max(1, min(3600, interval))
        self.store.set_rate(gid, cap, interval)
        return aiohttp_web.json_response({"code": 0})

    async def api_rate_reset(self, request):
        self.require_auth(request)
        data = await request.json()
        self.store.del_rate(str(data.get("group_id") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_blacklist_get(self, request):
        self.require_super(request)
        items = self.store.blacklist()
        fixed = 0
        for it in items:
            if it.get("nick") or fixed >= 10:
                continue
            try:
                res = await self.onebot_action("get_stranger_info", {"user_id": int(it["qq"])})
                if isinstance(res, dict) and res.get("status") == "ok":
                    nick = str((res.get("data") or {}).get("nick") or "").strip()
                    if nick:
                        self.store.set_black_nick(it["qq"], nick)
                        it["nick"] = nick
                        fixed += 1
            except Exception:
                pass
        return aiohttp_web.json_response({"code": 0, "list": items})

    async def api_blacklist_add(self, request):
        self.require_super(request)
        data = await request.json()
        qq = self.norm_qq(data.get("qq"))
        if not qq or not qq.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "QQ 号需为纯数字"})
        nick = ""
        try:
            res = await self.onebot_action("get_stranger_info", {"user_id": int(qq)})
            if isinstance(res, dict) and res.get("status") == "ok":
                nick = str((res.get("data") or {}).get("nick") or "")
        except Exception:
            pass
        self.store.add_black(qq, nick)
        return aiohttp_web.json_response({"code": 0})

    async def api_blacklist_remove(self, request):
        self.require_super(request)
        data = await request.json()
        qq = self.norm_qq(data.get("qq"))
        self.store.remove_black(qq)
        return aiohttp_web.json_response({"code": 0})

    async def api_rest_get(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("rest_enabled", "0") == "1",
            "start": self.store.get_setting("rest_start", "22:00"),
            "end": self.store.get_setting("rest_end", "08:00"),
            "groups": self.store.rest_groups(),
            "users": self.store.rest_users(),
            "all_groups": self.store.groups(),
            "all_users": self.store.users(),
            "in_rest": self.rest_window(),
            "notify": self.store.get_setting("rest_notify", "1") == "1",
            "notify_groups": self.store.rest_notify_groups(),
        })

    async def api_rest_config(self, request):
        self.require_super(request)   # 写配置统一要求超管
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("rest_enabled", "1" if data.get("enabled") else "0")
        if "notify" in data:
            self.store.set_setting("rest_notify", "1" if data.get("notify") else "0")
        if "start" in data:
            self.store.set_setting("rest_start", str(data.get("start") or "22:00").strip())
        if "end" in data:
            self.store.set_setting("rest_end", str(data.get("end") or "08:00").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_rest_wl(self, request):
        self.require_auth(request)
        data = await request.json()
        kind = data.get("type")
        value = self.norm_qq(data.get("value"))
        if kind not in ("group", "user") or not value.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "请输入纯数字"})
        if data.get("action") == "remove":
            if kind == "group":
                self.store.remove_rest_group(value)
            else:
                self.store.remove_rest_user(value)
        else:
            if kind == "group":
                self.store.add_rest_group(value)
            else:
                self.store.add_rest_user(value)
        return aiohttp_web.json_response({"code": 0})

    async def api_rest_notify_groups(self, request):
        self.require_auth(request)
        data = await request.json()
        value = self.norm_qq(data.get("value"))
        if not value.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "请输入纯数字群号"})
        if data.get("action") == "remove":
            self.store.remove_rest_notify_group(value)
        else:
            self.store.add_rest_notify_group(value)
        return aiohttp_web.json_response({"code": 0})

    async def api_rest_import(self, request):
        self.require_auth(request)
        for g in self.store.groups():
            self.store.add_rest_group(g)
        for u in self.store.users():
            self.store.add_rest_user(u)
        return aiohttp_web.json_response({"code": 0})

    async def api_me(self, request):
        acc = self.require_role(request, "user")
        row = self.store.account_by_id(acc.get("id")) or {}
        return aiohttp_web.json_response({
            "code": 0,
            "id": acc.get("id"),
            "username": acc.get("username"),
            "role": acc.get("role"),
            "quota_groups": row.get("quota_groups"),
            "quota_users": row.get("quota_users"),
            "viewer_enabled": VIEWER_FEATURE and self.store.get_setting("enable_viewer_role", "0") == "1",
        })

    async def api_friend_get(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({
            "code": 0,
            "auto": self.store.get_setting("friend_auto_accept", "0") == "1",
            "notify": self.store.get_setting("friend_notify", "1") == "1",
            "limit": int(self.store.get_setting("friend_daily_limit", "10") or 10),
            "today_accepted": self.store.friend_today("accepted"),
            "today_total": self.store.friend_today("pending") + self.store.friend_today("accepted")
                           + self.store.friend_today("rejected") + self.store.friend_today("overlimit")
                           + self.store.friend_today("failed"),
            "list": self.store.friend_list(50),
        })

    async def api_friend_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "auto" in data:
            self.store.set_setting("friend_auto_accept", "1" if data.get("auto") else "0")
        if "notify" in data:
            self.store.set_setting("friend_notify", "1" if data.get("notify") else "0")
        if "limit" in data:
            try:
                self.store.set_setting("friend_daily_limit", str(max(1, min(200, int(data.get("limit"))))))
            except Exception:
                pass
        return aiohttp_web.json_response({"code": 0})

    async def api_friend_action(self, request):
        self.require_super(request)
        data = await request.json()
        flag = str(data.get("flag") or "")
        approve = bool(data.get("approve"))
        if not flag:
            return aiohttp_web.json_response({"code": -1, "message": "缺少请求标识"})
        res = await self.onebot_action("set_friend_add_request", {"flag": flag, "approve": approve})
        if not res or res.get("status") != "ok":
            return aiohttp_web.json_response({"code": -1, "message": "处理失败，请求可能已过期"})
        self.store.friend_update(flag, "accepted" if approve else "rejected")
        return aiohttp_web.json_response({"code": 0})

    async def api_super_get(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({
            "code": 0,
            "qqs": self.super_admin_qqs(),
            "simp": self.store.get_setting("simp_mode", "0") == "1",
            "exclusive": self.store.get_setting("exclusive_mode", "0") == "1",
            "window_seconds": int(float(self.store.get_setting("exclusive_window_seconds", "60") or 60)),
            "roast": self.store.get_setting("roast_enabled", "1") == "1",
            "roast_level": int(self.store.get_setting("roast_level", "1") or 1),
            "roast_mode": self.store.get_setting("roast_mode", "fast") or "fast",
            "roast_keywords": self.store.get_setting("roast_keywords", "怼") or "怼",
            "balance_keywords": self.store.get_setting("balance_keywords", "") or "",
            "sticker_capture": self.store.get_setting("sticker_capture_enabled", "1") == "1",
            "sticker_capture_keywords": self.store.get_setting("sticker_capture_keywords", "") or "添加表情包,收录,存表情",
        })

    async def api_super_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "qqs" in data:
            raw = str(data.get("qqs") or "")
            parts = []
            for p in raw.replace("，", ",").split(","):
                q = self.norm_qq(p)
                if not q:
                    continue
                if not q.isdigit():
                    return aiohttp_web.json_response({"code": -1, "message": "QQ 号需为纯数字：" + q})
                if q not in parts:
                    parts.append(q)
            self.store.set_setting("super_admin_qqs", ",".join(parts))
        if "simp" in data:
            self.store.set_setting("simp_mode", "1" if data.get("simp") else "0")
        if "exclusive" in data:
            self.store.set_setting("exclusive_mode", "1" if data.get("exclusive") else "0")
        if "roast" in data:
            self.store.set_setting("roast_enabled", "1" if data.get("roast") else "0")
        if "sticker_capture" in data:
            self.store.set_setting("sticker_capture_enabled", "1" if data.get("sticker_capture") else "0")
        if "sticker_capture_keywords" in data:
            words = [w.strip() for w in str(data.get("sticker_capture_keywords") or "").replace("，", ",").split(",") if w.strip()]
            self.store.set_setting("sticker_capture_keywords", ",".join(words))
        if "balance_keywords" in data:
            words = [w.strip() for w in str(data.get("balance_keywords") or "").replace("，", ",").split(",") if w.strip()]
            self.store.set_setting("balance_keywords", ",".join(words))
        if "roast_mode" in data:
            self.store.set_setting("roast_mode", "think" if str(data.get("roast_mode")) == "think" else "fast")
        if "roast_level" in data:
            try:
                self.store.set_setting("roast_level", str(max(0, min(2, int(data.get("roast_level"))))))
            except Exception:
                pass
        if "roast_keywords" in data:
            words = [w.strip() for w in str(data.get("roast_keywords") or "").replace("，", ",").split(",") if w.strip()]
            self.store.set_setting("roast_keywords", ",".join(words) or "怼")
        if "window_seconds" in data:
            try:
                w = max(10, min(3600, int(float(data.get("window_seconds")))))
            except (TypeError, ValueError):
                return aiohttp_web.json_response({"code": -1, "message": "窗口时长需为秒数（≥10）"})
            self.store.set_setting("exclusive_window_seconds", str(w))
        return aiohttp_web.json_response({"code": 0})

    async def api_convos(self, request):
        self.require_auth(request)
        now = time.time()
        items = []
        for (gid, qq), exp in self.active_convos.items():
            if exp > now:
                items.append({"group_id": gid, "qq": qq, "expires_in": int(exp - now)})
        items.sort(key=lambda x: x["expires_in"])
        return aiohttp_web.json_response({
            "code": 0,
            "items": items,
            "cleanup_interval": self.cleanup_interval,
        })


add(id="config.chat", name="聊天规则配置", entry="fishpond.features.config.service:ConfigMixin",
    routes=["/api/whitelist/*", "/api/keywords/*", "/api/prefix/*", "/api/auto/*", "/api/group-rate/*", "/api/rest/*"],
    tables=["wl_groups", "wl_users", "keywords", "prefix_map", "auto_users", "settings"], settings=["*"],
    ui="聊天/白名单等", files="fishpond/features/config/service.py", status="active")
