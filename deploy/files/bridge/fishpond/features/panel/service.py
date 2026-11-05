"""群面板模块：每群独立面板、外链登录、配置与黑名单接口。"""
import asyncio
import hashlib
import json
import re
import secrets
import time

import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


class PanelMixin:
    def db_panel_by_token(self, token: str):
        try:
            with self.store._conn() as c:
                return c.execute("SELECT * FROM group_panel WHERE token=?", (str(token),)).fetchone()
        except Exception:
            return None

    async def api_glogin(self, request):
        token = str(request.match_info.get("token") or "")
        row = self.db_panel_by_token(token)
        if not row or int(row["enabled"] or 0) == 0:
            return aiohttp_web.json_response({"code": -1, "message": "链接无效或已停用"})
        d = await request.json()
        import hashlib as _hl
        pw = str(d.get("password") or "")
        try:
            salt, h = str(row["pass_hash"] or "").split("$", 1)
        except Exception:
            return aiohttp_web.json_response({"code": -1, "message": "账号未初始化"})
        if str(d.get("username") or "") != str(row["username"] or "") or \
           _hl.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex() != h:
            return aiohttp_web.json_response({"code": -1, "message": "账号或密码错误"})
        sid = secrets.token_urlsafe(24)
        sess = getattr(self, "_gp_sess", None)
        if sess is None:
            sess = {}; self._gp_sess = sess
        sess[sid] = (token, time.time() + 7 * 86400)
        resp = aiohttp_web.json_response({"code": 0})
        resp.set_cookie("fp_gp_sid", sid, max_age=7 * 86400, httponly=True, samesite="Lax", path="/")
        return resp

    async def api_gbl(self, request):
        token = str(request.match_info.get("token") or "")
        row = self._gp_ok(request, token)
        if not row:
            return aiohttp_web.json_response({"code": -1, "message": "请先登录"}, status=401)
        gid = str(row["group_id"])
        try:
            items = json.loads(self.store.group_cfg_get(gid, "gm_blacklist", "") or "[]")
        except Exception:
            items = []
        if request.method == "GET":
            return aiohttp_web.json_response({"code": 0, "items": items})
        d = await request.json()
        act = str(d.get("action") or "")
        qq = str(d.get("qq") or "").strip()
        old = str(d.get("old_qq") or qq).strip()
        if act == "remove":
            items = [x for x in items if str(x.get("qq")) != old]
        elif act == "update":
            items = [x for x in items if str(x.get("qq")) not in (old, qq)]
            items.append({"qq": qq, "nick": str(d.get("nick") or "")[:40]})
        else:
            if not qq.isdigit():
                return aiohttp_web.json_response({"code": -1, "message": "QQ 号无效"})
            items = [x for x in items if str(x.get("qq")) != qq]
            items.append({"qq": qq, "nick": str(d.get("nick") or "")[:40]})
        self.store.group_cfg_set(gid, "gm_blacklist", json.dumps(items, ensure_ascii=False))
        return aiohttp_web.json_response({"code": 0})

    async def api_gcfg(self, request):
        token = str(request.match_info.get("token") or "")
        row = self._gp_ok(request, token)
        if not row:
            return aiohttp_web.json_response({"code": -1, "message": "请先登录"}, status=401)
        gid = str(row["group_id"])
        if request.method == "GET":
            out = {k: self.gm_get(k, gid, "") for k in self.GP_KEYS}
            return aiohttp_web.json_response({"code": 0, "group_id": gid, **out})
        d = await request.json()
        for k in self.GP_KEYS:
            if k in d:
                self.store.group_cfg_set(gid, k, str(d.get(k) or ""))
        return aiohttp_web.json_response({"code": 0})

    def gpage_html(self, token: str, prefix: str) -> str:
        import re as _re
        base = f"{prefix}/g/{token}"
        css = self.admin_css()
        i = self.admin_html().index('<div id="gm"')
        depth = 0; j = i; tag = _re.compile(r'<div\b|</div>')
        while True:
            mm = tag.search(self.admin_html(), j)
            depth += 1 if mm.group(0).startswith('<div') else -1
            j = mm.end()
            if depth == 0:
                break
        block = self.admin_html()[i:j].replace('class="hidden"', '')
        return self.PAGE_TMPL.replace("__CSS__", css).replace("__BLOCK__", block).replace("__BASE__", base)

    async def gpage(self, request):
        token = str(request.match_info.get("token") or "")
        return aiohttp_web.Response(text=self.gpage_html(token, self.webui_prefix()),
                                    content_type="text/html", charset="utf-8")

    async def api_gm_groups(self, request):
        self.require_super(request)
        if request.method == "GET":
            items = self.store.group_panels()
            for it in items:
                it["password"] = ""
                it["has_password"] = True
            return aiohttp_web.json_response({"code": 0, "items": items})
        d = await request.json()
        act = str(d.get("action") or "")
        gid = str(d.get("group_id") or "").strip()
        if not gid.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "群号无效"})
        import hashlib as _hl, secrets as _sec
        def _hash(pw, salt):
            return salt + "$" + _hl.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
        if act == "create" or act == "reset":
            pw = str(d.get("password") or "").strip() or _sec.token_urlsafe(9)
            uname = str(d.get("username") or "").strip() or ("g" + gid[-6:])
            salt = _sec.token_hex(8)
            row = self.store.group_panel_get(gid)
            token = row["token"] if row and row["token"] else _sec.token_urlsafe(18)
            self.store.group_panel_add(gid, uname, _hash(pw, salt), token, "")
            return aiohttp_web.json_response({"code": 0, "username": uname, "password": pw,
                                              "token": token, "group_id": gid})
        row = self.store.group_panel_get(gid)
        if not row:
            return aiohttp_web.json_response({"code": -1, "message": "该群未创建面板"})
        if act == "toggle":
            self.store.group_panel_update(gid, enabled=0 if int(row["enabled"] or 0) else 1)
        elif act == "delete":
            self.store.group_panel_del(gid)
        elif act == "login_link":
            codes = getattr(self, "_gp_codes", None)
            if codes is None:
                codes = {}; self._gp_codes = codes
            code = secrets.token_urlsafe(18)
            codes[code] = (row["token"], time.time() + 60)
            path = f"{self.webui_prefix()}/g/{row['token']}/admin_login?code={code}"
            return aiohttp_web.json_response({"code": 0, "path": path})
        elif act == "save":
            uname = str(d.get("username") or "").strip()
            pw = str(d.get("password") or "").strip()
            if not uname:
                return aiohttp_web.json_response({"code": -1, "message": "账号不能为空"})
            if pw:
                salt = _sec.token_hex(8)
                self.store.group_panel_update(gid, username=uname, pass_hash=_hash(pw, salt), pass_plain="")
            else:
                self.store.group_panel_update(gid, username=uname)
        elif act == "rename":
            uname = str(d.get("username") or "").strip()
            if uname:
                self.store.group_panel_update(gid, username=uname)
        else:
            return aiohttp_web.json_response({"code": -1, "message": "未知操作"})
        return aiohttp_web.json_response({"code": 0})

    async def api_gm_config(self, request):
        self.require_super(request)
        keys = ("gm_groups", "gm_auto_approve", "gm_verify", "gm_verify_mode", "gm_question",
                "gm_answer", "gm_questions", "gm_timeout_min", "gm_welcome", "gm_kick_enabled", "gm_blacklist_kick", "gm_mute_enabled", "gm_kick_qqs",
                "gm_patrol_enabled", "gm_patrol_rate", "gm_patrol_mute_min", "gm_patrol_warn",
                "gm_ai_patrol", "gm_ai_context", "gm_ai_action", "gm_silent",
                "gm_kick_keywords", "gm_blacklist_keywords", "gm_recall_keywords", "gm_recall_enabled",
                "gm_kwlimit_rules", "gm_punish_qqs")
        defaults = {"gm_auto_approve": "0", "gm_verify": "0", "gm_verify_mode": "private",
                    "gm_question": "请回答：1+1 等于几？", "gm_answer": "2",
                    "gm_timeout_min": "5", "gm_kick_enabled": "1",
                    "gm_patrol_rate": "10", "gm_patrol_mute_min": "10",
                    "gm_patrol_warn": "检测到刷屏，已禁言 {minute} 分钟，请注意发言频率。",
                    "gm_ai_context": "6", "gm_ai_action": "warn", "gm_silent": "0"}
        gid = ""
        if request.method == "GET":
            gid = str(request.query.get("gid") or "")
            out = {k: (self.gm_get(k, gid, defaults.get(k, "")) or defaults.get(k, "")) for k in keys}
            return aiohttp_web.json_response({"code": 0, "gid": gid, **out})
        d = await request.json()
        gid = str(d.get("gid") or "")
        for k in keys:
            if k in d:
                if gid:
                    self.store.group_cfg_set(gid, k, str(d.get(k) or ""))
                else:
                    self.store.set_setting(k, str(d.get(k) or ""))
        return aiohttp_web.json_response({"code": 0, "gid": gid})

