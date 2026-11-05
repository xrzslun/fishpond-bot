"""App 原生客户端接口：首页状态、聊天收发。"""
import time

import aiohttp.web as aiohttp_web

from fishpond.registry import add


add(id="appapi", name="App 客户端接口", entry="fishpond/features/appapi/service.py",
    routes=["/api/app/home", "/api/app/chat/history", "/api/app/chat/send"],
    tables=["app_chat"], ui="App 原生客户端")


class AppApiMixin:
    def app_chat_table(self):
        with self.store._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS app_chat(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qq TEXT, role TEXT, text TEXT, created_at REAL)""")

    def app_key(self) -> str:
        key = self.store.get_setting("app_key", "")
        if not key:
            import secrets as _s
            key = _s.token_hex(16)
            self.store.set_setting("app_key", key)
        return key

    def app_auth_ok(self, request) -> bool:
        key = (request.headers.get("X-App-Key") or "").strip()
        if key and key == self.app_key():
            return True
        try:
            if self.current_account(request):
                return True
        except Exception:
            pass
        peer = request.remote or ""
        return peer in ("127.0.0.1", "::1")

    def app_owner_qq(self) -> str:
        qq = self.store.get_setting("world_owner_qq", "") or ""
        if not qq:
            try:
                qq = str((self.super_admin_qqs() or [""])[0])
            except Exception:
                qq = ""
        return qq

    async def api_app_ping(self, request):
        v = getattr(self, "APP_VERSION", "") or ""
        if not v:
            import sys as _sys
            v = getattr(_sys.modules.get("__main__"), "APP_VERSION", "") or ""
        return aiohttp_web.json_response({"code": 0, "name": "FishPond", "version": v,
                                          "need_key": False})

    async def api_app_tunnel(self, request):
        if not self.app_auth_ok(request):
            return aiohttp_web.json_response({"code": -1, "message": "unauthorized"}, status=401)
        url = self.store.get_setting("current_tunnel_url", "") or self.store.get_setting("public_base_url", "")
        if not url:
            try:
                from pathlib import Path as _P
                f = _P(__file__).resolve().parents[3] / "tunnel_url"
                if f.is_file():
                    url = f.read_text().strip()
            except Exception:
                pass
        return aiohttp_web.json_response({"code": 0, "url": url, "key": self.app_key()})

    async def api_app_sso(self, request):
        key = str(request.query.get("key") or "")
        if key != self.app_key():
            return aiohttp_web.json_response({"code": -1, "message": "key invalid"}, status=403)
        import secrets as _s
        sid = _s.token_hex(16)
        self.auth_sessions[sid] = {"exp": time.time() + 7 * 86400, "id": 0, "username": "app", "role": "super"}
        resp = aiohttp_web.HTTPFound(self.webui_prefix() or "/")
        resp.set_cookie("qb_sid", sid, max_age=7 * 86400, httponly=True, samesite="Lax")
        return resp

    async def api_app_home(self, request):
        if not self.app_auth_ok(request):
            return aiohttp_web.json_response({"code": -1, "message": "unauthorized"}, status=401)
        self.app_chat_table()
        st = self.world_state() or {}
        with self.store._conn() as c:
            last = c.execute("SELECT text,created_at FROM app_chat ORDER BY id DESC LIMIT 1").fetchone()
        return aiohttp_web.json_response({"code": 0, "status": {
            "online": bool(getattr(self, "connected", False) and self.self_id),
            "qq": self.self_id,
            "model": self.model,
            "messages": self.msg_count,
            "replies": self.reply_count,
        }, "world": {
            "clock": st.get("clock", ""), "activity": st.get("activity", ""),
            "place": st.get("place", ""), "mood": st.get("mood", ""),
            "energy": st.get("energy", 0),
            "asleep": self.in_world_rest() if hasattr(self, "in_world_rest") else False,
        }, "events": [{"text": e.get("text", ""), "kind": e.get("kind", "")} for e in self.world_recent_events(12)],
           "last": ({"text": last["text"], "at": last["created_at"]} if last else None)})

    async def api_app_history(self, request):
        if not self.app_auth_ok(request):
            return aiohttp_web.json_response({"code": -1, "message": "unauthorized"}, status=401)
        self.app_chat_table()
        limit = min(100, int(request.query.get("limit", "50") or 50))
        with self.store._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT id,role,text,created_at FROM app_chat ORDER BY id DESC LIMIT ?", (limit,))]
        return aiohttp_web.json_response({"code": 0, "items": list(reversed(rows))})

    async def api_app_send(self, request):
        if not self.app_auth_ok(request):
            return aiohttp_web.json_response({"code": -1, "message": "unauthorized"}, status=401)
        self.app_chat_table()
        d = await request.json()
        text = str(d.get("text") or "").strip()
        if not text:
            return aiohttp_web.json_response({"code": -1, "message": "内容为空"})
        qq = self.app_owner_qq()
        sess = self.session("app:" + qq)
        async with sess["lock"]:
            reply = await self.ask_deepseek(sess, text, is_super=True, uid=qq, gid="")
        now = time.time()
        with self.store._conn() as c:
            c.execute("INSERT INTO app_chat(qq,role,text,created_at) VALUES(?,?,?,?)", (qq, "user", text, now))
            c.execute("INSERT INTO app_chat(qq,role,text,created_at) VALUES(?,?,?,?)", (qq, "assistant", reply, now + 0.001))
        return aiohttp_web.json_response({"code": 0, "reply": str(reply).replace("|||", " ")})
