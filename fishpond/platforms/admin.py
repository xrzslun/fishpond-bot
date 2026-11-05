"""后台平台层：登录鉴权、日志、自检、版本更新。"""
import asyncio
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.core.config import MEMORY_FEATURE
from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")

DEFAULT_UPDATE_URL = "https://xrzs.cloud/updates/latest.json"


def _base_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    if (root / "bot.py").is_file():
        return root
    alt = root / "bridge"
    return alt if alt.is_dir() else root


BASE = _base_dir()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
    except ValueError:
        return False
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex() == h



class AdminMixin:
    def app_version(self) -> str:
        return getattr(self, "_app_version_str", "")

    def login_throttle_check(self, ip: str, username: str):
        now = time.time()
        recs = getattr(self, "_login_guard", {})
        for key in (f"ip:{ip}", f"u:{username}"):
            r = recs.get(key)
            if r and r.get("lock_until", 0) > now:
                return int(r["lock_until"] - now)
        self._login_guard = recs
        return 0

    def login_throttle_fail(self, ip: str, username: str):
        now = time.time()
        recs = getattr(self, "_login_guard", {})
        rules = [(f"ip:{ip}", 5, 600, 900), (f"u:{username}", 10, 1800, 300)]
        for key, limit, window, lock in rules:
            r = recs.setdefault(key, {"times": [], "lock_until": 0})
            r["times"] = [t for t in r["times"] if now - t < window]
            r["times"].append(now)
            if len(r["times"]) >= limit:
                r["lock_until"] = now + lock
                r["times"] = []
                log.warning("登录失败次数过多，已临时锁定 %s 分钟（%s）", lock // 60, key)
        self._login_guard = recs

    def login_throttle_ok(self, ip: str, username: str):
        recs = getattr(self, "_login_guard", {})
        recs.pop(f"ip:{ip}", None)
        recs.pop(f"u:{username}", None)
        self._login_guard = recs

    def ensure_default_admin(self, admin_cfg: dict):
        """首次部署生成初始账号：必须是超级管理员。"""
        if self.store.admin_count() != 0:
            return
        default = (admin_cfg or {}).get("default_admin", {}) or {}
        username = str(default.get("username") or "admin")
        password = str(default.get("password") or "admin")
        if self.store.create_account(username, password, "super") is None:
            self.store.add_admin(username, password)
            self.store.set_account_role_by_name(username, "super")
        log.info("已创建默认超级管理员 %s", username)

    def require_auth(self, request):
        if not self.auth_ok(request):
            raise aiohttp_web.HTTPUnauthorized(text=json.dumps({"code": -1, "message": "请先登录"}, ensure_ascii=False))

    def require_super(self, request):
        acc = self.current_account(request)
        if not acc:
            raise aiohttp_web.HTTPUnauthorized(text=json.dumps({"code": -1, "message": "请先登录"}, ensure_ascii=False))
        if str(acc.get("role")) != "super":
            raise aiohttp_web.HTTPForbidden(text=json.dumps({"code": -1, "message": "只有超级管理员可以操作"}, ensure_ascii=False))
        return acc

    def require_role(self, request, min_role: str = "user"):
        acc = self.current_account(request)
        if not acc:
            raise aiohttp_web.HTTPUnauthorized(text=json.dumps({"code": -1, "message": "请先登录"}, ensure_ascii=False))
        if str(acc.get("role")) == "viewer":
            if request.method in ("GET", "HEAD") and min_role == "user":
                return acc
            raise aiohttp_web.HTTPForbidden(text=json.dumps({"code": -1, "message": "没有权限"}, ensure_ascii=False))
        order = {"user": 1, "admin": 2, "super": 3}
        if order.get(str(acc.get("role")), 0) < order.get(min_role, 0):
            raise aiohttp_web.HTTPForbidden(text=json.dumps({"code": -1, "message": "没有权限"}, ensure_ascii=False))
        return acc

    def role_middleware(self):
        @aiohttp_web.middleware
        async def role_mw(request, handler):
            rel = request.path
            prefix = self.webui_prefix()
            if prefix and rel.startswith(prefix):
                rel = rel[len(prefix):] or "/"
            if rel in ("/", "/api/login", "/api/logout"):
                return await handler(request)
            # 表情包是给 NapCat 等外部客户端无 Cookie 拉取的公开静态文件：
            # 必须在鉴权前放行，否则 NapCat 下载图片收到 401，
            # 表现为日志显示“表情包已发送”但群里看不到图。
            if request.method in ("GET", "HEAD") and rel.startswith("/stickers/"):
                return await handler(request)
            if rel.startswith("/api/app/"):
                # APP 接口自行用 X-App-Key 鉴权，不能先被后台登录拦掉
                return await handler(request)
            if request.method in ("GET", "HEAD") and rel in ("/api/stickerpack/list", "/api/stickerpack/file"):
                return await handler(request)
            try:
                host = (request.host or "").lower()
                if host.endswith(".trycloudflare.com"):
                    url = f"{request.scheme}://{request.host}"
                    if self.store.get_setting("current_tunnel_url", "") != url:
                        self.store.set_setting("current_tunnel_url", url)
            except Exception:
                pass
            # 群面板 /g/<token>/ 是给群主的外链页，自带 token + 口令登录（_gp_ok），
            # 不能再套后台登录。前缀为空时（默认 webui.path=/）这些路由落在根应用上，
            # 不放行会整页 401，链接打不开。
            if rel.startswith("/g/"):
                return await handler(request)
            acc = self.current_account(request)
            if not acc:
                return aiohttp_web.json_response({"code": -1, "message": "请先登录"}, status=401)
            role = str(acc.get("role"))
            if role == "viewer" and request.method != "GET":
                return aiohttp_web.json_response({"code": -1, "message": "观察者模式：只读，不能操作"}, status=403)
            if rel.startswith("/api/memory") and not MEMORY_FEATURE:
                return aiohttp_web.json_response({"code": -1, "message": "该功能暂未开放"}, status=403)
            if rel.startswith("/api/") and not self.role_allowed(role, rel):
                return aiohttp_web.json_response({"code": -1, "message": "没有权限"}, status=403)
            # 强制更新期间：只暂停写操作，读操作和更新按钮保持可用
            if request.method not in ("GET", "HEAD"):
                info = self.force_update_required()
                allow = ("/api/login", "/api/logout", "/api/me", "/api/update/check",
                         "/api/update/apply", "/api/update/config", "/api/update")
                if info and rel not in allow:
                    return aiohttp_web.json_response({
                        "code": -2, "message": f"当前版本过低，请先更新到 {info.get('latest')}",
                        "force": True, "latest": info.get("latest"),
                    }, status=426)
            return await handler(request)

        return role_mw

    async def page_index(self, request):
        headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
        base = self.webui_prefix()
        if not self.auth_ok(request):
            return aiohttp_web.Response(text=self.login_html().replace("__BASE__", base), content_type="text/html", charset="utf-8", headers=headers)
        return aiohttp_web.Response(text=self.admin_html().replace("__BASE__", base), content_type="text/html", charset="utf-8", headers=headers)

    async def api_login(self, request):
        data = await request.json()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        ip = self.client_ip(request)
        ua = request.headers.get("User-Agent", "")
        remain = self.login_throttle_check(ip, username)
        if remain > 0:
            return aiohttp_web.json_response({"code": -1, "message": f"尝试次数过多，请 {max(1, remain // 60)} 分钟后再试"})
        loc = await self.ip_location(ip)
        acc = self.store.account_by_name(username)
        stored = acc.get("pass_hash") if acc else None
        if not stored or not verify_password(password, stored):
            self.login_throttle_fail(ip, username)
            self.store.log_login(acc.get("id") if acc else None, username, (acc or {}).get("role") or "", 0, ip, ua, "用户名或密码错误", loc)
            return aiohttp_web.json_response({"code": -1, "message": "用户名或密码错误"})
        if int(acc.get("disabled") or 0) == 1:
            self.store.log_login(acc.get("id"), username, acc.get("role") or "", 0, ip, ua, "账号已禁用", loc)
            return aiohttp_web.json_response({"code": -1, "message": "该账号已被禁用"})
        self.login_throttle_ok(ip, username)
        sid = secrets.token_urlsafe(32)
        role = str(acc.get("role") or "admin")
        self.auth_sessions[sid] = {"exp": time.time() + 7 * 86400, "id": acc.get("id"), "username": username, "role": role}
        self.store.touch_login(acc.get("id"), ip)
        self.store.log_login(acc.get("id"), username, role, 1, ip, ua, "", loc)
        if role == "super" and hasattr(self, "update_weather_location"):
            try:
                if self.store.get_setting("weather_loc_source", "") != "manual":
                    self.store.set_setting("weather_admin_ip", str(ip)[:64])
                    self.spawn(self.update_weather_location(ip), "weather_loc")
                self.spawn(self.weather_data(force=True), "weather_refresh")
            except Exception:
                pass
        resp = aiohttp_web.json_response({"code": 0, "role": role, "username": username})
        resp.set_cookie("qb_sid", sid, max_age=7 * 86400, httponly=True, samesite="Lax", secure=True)
        return resp

    async def api_logout(self, request):
        sid = request.cookies.get("qb_sid")
        if sid:
            self.auth_sessions.pop(sid, None)
        resp = aiohttp_web.json_response({"code": 0})
        resp.del_cookie("qb_sid")
        return resp

    async def api_logs(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({"code": 0, "logs": list(self.log_ring())})

    async def api_featurecheck_run(self, request):
        """功能块自检：每条检查都自带清理，不会留下测试数据。"""
        self.require_super(request)
        out = []
        mark = "__sc__" + secrets.token_hex(4)

        async def run(group, name, fn):
            t0 = time.time()
            ok, msg = False, ""
            try:
                r = fn()
                if asyncio.iscoroutine(r):
                    r = await r
                if isinstance(r, tuple):
                    ok, msg = bool(r[0]), str(r[1] or "")
                else:
                    ok, msg = bool(r), ""
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"[:140]
            out.append({"group": group, "name": name, "ok": ok,
                        "ms": int((time.time() - t0) * 1000), "msg": msg})

        # ---------- 数据库 ----------
        def _db():
            with self.store._conn() as c:
                r = c.execute("PRAGMA integrity_check").fetchone()[0]
            return (r == "ok"), str(r)

        await run("数据", "数据库完整性", _db)

        # ---------- 记忆读写 ----------
        def _mem():
            uid = "__selfcheck__"
            try:
                self.store.mem_add(uid, mark + " 功能自检", level="normal", source="selfcheck")
                hit = [m for m in self.store.mem_by_owner(uid, all_levels=True) if mark in str(m.get("content"))]
                if not hit:
                    return False, "写入后读不到"
                self.store.mem_delete(hit[0]["id"])
                left = [m for m in self.store.mem_by_owner(uid, all_levels=True) if mark in str(m.get("content"))]
                return (len(left) == 0), "写入/读取/删除正常" if not left else "清理失败"
            finally:
                try:
                    for m in self.store.mem_by_owner("__selfcheck__", all_levels=True):
                        if mark in str(m.get("content")):
                            self.store.mem_delete(m["id"])
                except Exception:
                    pass

        await run("记忆", "写入/读取/删除", _mem)

        # ---------- 关键词 ----------
        def _kw():
            try:
                self.store.add_keyword(mark)
                ok = mark in self.store.keywords()
                return ok, "增删正常" if ok else "写入后读不到"
            finally:
                self.store.remove_keyword(mark)

        await run("聊天", "关键词增删", _kw)

        # ---------- 白名单 ----------
        def _wl():
            gid = "999999999"
            try:
                self.store.add_wl("group", gid)
                ok = gid in [str(x) for x in self.store.groups()] or gid in [str(x) for x in self.store.groups(all_rows=True)]
                return ok, "增删正常" if ok else "写入后读不到"
            finally:
                self.store.remove_wl("group", gid)

        await run("白名单", "群白名单增删", _wl)

        # ---------- 称呼前缀 ----------
        def _pf():
            qq = "999999999"
            try:
                self.store.set_prefix(qq, "自检")
                ok = self.store.get_prefix(qq) == "自检"
                return ok, "增删正常" if ok else "写入后读不到"
            finally:
                self.store.remove_prefix(qq)

        await run("聊天", "称呼前缀", _pf)

        # ---------- 消息解析 ----------
        def _parse():
            ev = {"message_type": "group", "self_id": "1", "user_id": "2", "group_id": "3",
                  "message": [{"type": "at", "data": {"qq": "1"}},
                              {"type": "text", "data": {"text": " 在吗 "}}]}
            seg = self.parse_segments(ev, "1")
            return (seg.get("at_me") and "在吗" in seg.get("user_text", "")), str(seg.get("user_text"))[:40]

        await run("核心", "消息解析（@/文本）", _parse)

        # ---------- 分段回复 ----------
        def _split():
            parts = self.split_reply("第一句。第二句。第三句。")
            return (len(parts) >= 1), f"{len(parts)} 段"

        await run("核心", "回复分段", _split)

        # ---------- 表情包 ----------
        def _stk():
            n = len([x for x in self.sticker_dir().glob("*") if x.is_file()]) if self.sticker_dir().exists() else 0
            url = self.sticker_url("test.png")
            return (n > 0 and bool(url)), f"{n} 张"

        await run("媒体", "表情包目录", _stk)

        # ---------- 生图配置 ----------
        def _img():
            on = self.store.get_setting("image_enabled", "0") == "1"
            has = bool(self.store.get_setting("image_api_key", "") or self.store.get_setting("image_api_key_zhipu", ""))
            return (True, ("已开启" if on else "未开启") + ("·有 Key" if has else "·无 Key"))

        await run("媒体", "生图配置", _img)

        # ---------- 语音 ----------
        def _voice():
            import shutil as _sh
            ff = bool(_sh.which("ffmpeg"))
            eng = self.store.get_setting("voice_engine", "tts")
            return ff, f"ffmpeg={'ok' if ff else '缺失'} 引擎={eng}"

        await run("媒体", "语音依赖", _voice)

        # ---------- 剧本 ----------
        def _game():
            rows = self.store.script_list(only_enabled=True)
            return True, f"本地 {len(rows)} 个（可远程拉取）"

        await run("剧本", "剧本库", _game)

        # ---------- 群管理 ----------
        def _gm():
            gs = self.gm_groups()
            return (True, f"启用管理的群 {len(gs)} 个")

        await run("群管理", "管理群列表", _gm)

        # ---------- 模型连通（花极少量 token） ----------
        async def _llm():
            p = self.current_provider() or {}
            if not p.get("api_key"):
                return False, "未配置 Key"
            t0 = time.time()
            out_s = await self.llm_complete("只回复两个字：可用", "在吗", max_tokens=8, temperature=0.0, timeout=20)
            return (bool(out_s)), f"{(time.time()-t0):.1f}s {str(out_s)[:20]}"

        await run("模型", "模型连通性（约 20 token）", _llm)

        # ---------- OneBot 连接 ----------
        async def _ws():
            if not self.connected or not self.ws:
                return False, "未连接 NapCat"
            r = await self.onebot_call(self.ws, "get_login_info", {}, timeout=6)
            if isinstance(r, dict) and r.get("retcode") in (0, 1):
                d = r.get("data") or {}
                return True, f"QQ {d.get('user_id')} {str(d.get('nickname') or '')[:12]}"
            return False, str(r)[:80]

        await run("连接", "OneBot 通信", _ws)

        passed = sum(1 for x in out if x["ok"])
        log.info("功能自检：%s/%s 通过", passed, len(out))
        return aiohttp_web.json_response({"code": 0, "total": len(out), "passed": passed,
                                          "failed": len(out) - passed, "items": out,
                                          "version": self.app_version()})

    async def api_selfcheck_run(self, request):
        self.require_super(request)
        sid = secrets.token_urlsafe(24)
        self.auth_sessions[sid] = {"exp": time.time() + 600, "id": 0,
                                   "username": "selfcheck", "role": "super"}
        port = int(os.environ.get("FISHPOND_ADMIN_PORT", "8099"))
        base = f"http://127.0.0.1:{port}{self.webui_prefix()}"
        out = []
        try:
            for item in self.SELFCHECK_ITEMS:
                group, path = item["g"], item["p"]
                method = item.get("m", "GET")
                allow_nonzero = bool(item.get("allow"))
                t0 = time.time()
                status, ok, msg = 0, False, ""
                try:
                    _req = self.http.post if method == "POST" else self.http.get
                    _kw = {"headers": {"Cookie": f"qb_sid={sid}"},
                           "timeout": aiohttp.ClientTimeout(total=20)}
                    if method == "POST":
                        _kw["json"] = item.get("d") or {}
                    async with _req(base + path, **_kw) as r:
                        status = r.status
                        body = await r.text()
                        if r.status == 200:
                            try:
                                j = json.loads(body)
                                ok = int(j.get("code", 0)) == 0 or allow_nonzero
                                msg = "" if ok else str(j.get("message") or "")[:80]
                            except Exception:
                                ok, msg = True, "非 JSON 响应"
                        else:
                            msg = body[:100]
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"[:120]
                out.append({"group": group, "path": path, "method": method, "status": status,
                            "ok": ok, "ms": int((time.time() - t0) * 1000), "msg": msg})
        finally:
            self.auth_sessions.pop(sid, None)
        passed = sum(1 for x in out if x["ok"])
        log.info("接口自检：%s/%s 通过", passed, len(out))
        return aiohttp_web.json_response({"code": 0, "total": len(out), "passed": passed,
                                          "failed": len(out) - passed, "items": out,
                                          "route_total": int(getattr(self, "_route_total", 0) or 0),
                                          "version": self.app_version()})

    def current_version(self) -> str:
        cur = (self.app_version() or "").strip()
        saved = (self.store.get_setting("app_version", "") or "").strip()
        if saved and self.version_tuple(saved) > self.version_tuple(cur):
            return saved
        return cur

    @staticmethod
    def version_tuple(v: str) -> tuple:
        out = []
        for part in str(v or "").replace("-", ".").split("."):
            num = "".join(ch for ch in part if ch.isdigit())
            out.append(int(num) if num else 0)
        return tuple(out or [0])

    def force_update_required(self):
        cache = getattr(self, "_update_cache", None)
        if not cache:
            return None
        info = cache[0]
        if not info.get("force"):
            return None
        minv = str(info.get("min_version") or "").strip()
        if not minv:
            return None
        try:
            if self.version_tuple(minv) > self.version_tuple(self.app_version()):
                return info
        except Exception:
            return None
        return None

    async def report_update_failure(self, msg: str):
        text = f"❌ 自动更新失败\n原因：{msg}\n当前版本：{self.app_version()}\n旧版本未改动，后台仍可正常使用"
        log.error("自动更新失败: %s", msg)
        try:
            (BASE / "updates").mkdir(parents=True, exist_ok=True)
            with open(BASE / "updates" / "failure.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
        except Exception as e:
            log.warning("写 updates/failure.log 失败: %s", e)
        try:
            if self.ws:
                await self.notify_super(self.ws, text)
        except Exception as e:
            log.warning("更新失败通知超管失败: %s", e)

    async def update_watch_loop(self):
        await asyncio.sleep(25)
        while not self._stop:
            try:
                await self.update_info(True)
            except Exception:
                pass
            await asyncio.sleep(30 * 60)

    async def update_info(self, force: bool = False) -> dict:
        url = (self.store.get_setting("update_url", "") or DEFAULT_UPDATE_URL).strip()
        current = self.current_version()
        if not url:
            return {"url_set": False, "current": current, "has_update": False, "force": False,
                    "update_url": "", "force_min": (self.store.get_setting("update_force_min", "") or "")}
        now = time.time()
        if not force and self._update_cache and now - self._update_cache[1] < 6 * 3600:
            return self._update_cache[0]
        result = {"url_set": True, "current": current, "has_update": False, "force": False,
                  "update_url": url, "force_min": (self.store.get_setting("update_force_min", "") or ""),
                  "checked_at": time.strftime("%Y-%m-%d %H:%M")}
        try:
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    result["error"] = f"HTTP {resp.status}"
                    return result
                data = await resp.json(content_type=None)
            latest = str(data.get("version") or "").strip()
            if not latest:
                result["error"] = "latest.json 缺少 version"
                return result
            result.update({
                "latest": latest,
                "date": str(data.get("date") or ""),
                "notes": str(data.get("notes") or "")[:2000],
                "url": str(data.get("url") or "").strip(),
                "sha256": str(data.get("sha256") or "").strip().lower(),
                "min_version": str(data.get("min_version") or "").strip(),
            })
            newer = self.version_tuple(latest) > self.version_tuple(current)
            minv = (result.get("min_version") or "").strip()
            forced = bool(minv) and self.version_tuple(current) < self.version_tuple(minv)
            result["has_update"] = newer or forced
            result["force"] = newer and forced
            self._update_cache = (result, now)
        except Exception as e:
            result["error"] = f"检查失败: {e}"
        return result

    async def api_update_file(self, request):
        name = request.match_info.get("name", "")
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "._-")
        path = BASE / "updates" / safe
        if not safe or not path.is_file():
            return aiohttp_web.json_response({"code": -1, "message": "not found"}, status=404)
        return aiohttp_web.FileResponse(path)

    async def api_update_get(self, request):
        self.require_super(request)
        if self._update_cache:
            return aiohttp_web.json_response({"code": 0, **self._update_cache[0]})
        return aiohttp_web.json_response({
            "code": 0, "url_set": True, "current": self.current_version(),
            "has_update": False, "force": False, "update_url": DEFAULT_UPDATE_URL,
        })

    async def api_update_check(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({"code": 0, **(await self.update_info(True))})

    async def api_update_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "url" in data:
            self.store.set_setting("update_url", str(data.get("url") or "").strip())
            self._update_cache = None
        if "force_min" in data:
            self.store.set_setting("update_force_min", str(data.get("force_min") or "").strip())
            self._update_cache = None
        return aiohttp_web.json_response({"code": 0})

    def snapshot_state(self) -> str:
        """升级前快照：代码 + 数据库 + 配置，保留最近 3 份。"""
        import shutil
        snap_root = BASE / "snapshots"
        snap_root.mkdir(parents=True, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S")
        dst = snap_root / name
        dst.mkdir(parents=True, exist_ok=True)
        for item in ("bot.py", "fishpond", "web", "config.yaml"):
            src = BASE / item
            if not src.exists():
                continue
            if src.is_dir():
                shutil.copytree(src, dst / item, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, dst / item)
        for db_name in ("data.db", "data.db-wal", "data.db-shm"):
            src = BASE / db_name
            if src.exists():
                try:
                    shutil.copy2(src, dst / db_name)
                except Exception:
                    pass
        (dst / "meta.json").write_text(json.dumps({"version": self.app_version(), "time": name}), encoding="utf-8")
        snaps = sorted([d for d in snap_root.iterdir() if d.is_dir() and (d / "meta.json").is_file()])
        for old in snaps[:-3]:
            shutil.rmtree(old, ignore_errors=True)
        return name

    def latest_snapshot(self):
        root = BASE / "snapshots"
        if not root.is_dir():
            return None
        snaps = sorted([d for d in root.iterdir() if d.is_dir() and (d / "meta.json").is_file()])
        return snaps[-1] if snaps else None

    async def api_rollback(self, request):
        self.require_super(request)
        import shutil
        snap = self.latest_snapshot()
        if not snap:
            return aiohttp_web.json_response({"code": -1, "message": "没有可用快照"})
        try:
            for item in ("bot.py", "fishpond", "web", "config.yaml"):
                src = snap / item
                if not src.exists():
                    continue
                dst = BASE / item
                if dst.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            for db_name in ("data.db", "data.db-wal", "data.db-shm"):
                src = snap / db_name
                if src.exists():
                    shutil.copy2(src, BASE / db_name)
            (BASE / ".update_pending").write_text(snap.name, encoding="utf-8")
            asyncio.get_running_loop().create_task(self._restart_soon())
            return aiohttp_web.json_response({"code": 0, "message": f"已回滚到快照 {snap.name}，正在重启…"})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": f"回滚失败: {e}"})

    def apply_update_package(self, data: bytes, target_dir: Path, backup_dir: Path) -> str:
        """解压目录包并落盘；失败抛异常。返回新版本号。"""
        import io as _io
        import shutil as _sh
        import tarfile as _tar
        import tempfile
        work = Path(tempfile.mkdtemp(prefix="fp_upd_"))
        with _tar.open(fileobj=_io.BytesIO(data), mode="r:gz") as tf:
            members = [m for m in tf.getmembers()
                       if not m.name.startswith(("/", "..")) and ".." not in Path(m.name).parts]
            tf.extractall(work, members=members)
        root = work
        if not (root / "bot.py").is_file() and (root / "fishpond").is_dir():
            subs = [d for d in root.iterdir() if d.is_dir() and (d / "bot.py").is_file()]
            if subs:
                root = subs[0]
        bot_py = root / "bot.py"
        if not bot_py.is_file():
            raise ValueError("包内缺少 bot.py")
        compile(bot_py.read_text(encoding="utf-8"), str(bot_py), "exec")
        if not (root / "fishpond" / "registry.py").is_file():
            raise ValueError("包内缺少 fishpond/registry.py")
        backup_dir.mkdir(parents=True, exist_ok=True)
        for name in ("bot.py", "fishpond", "web"):
            src = target_dir / name
            if src.exists():
                dst = backup_dir / name
                if dst.is_dir():
                    _sh.rmtree(dst)
                elif dst.exists():
                    dst.unlink()
                if src.is_dir():
                    _sh.copytree(src, dst)
                else:
                    _sh.copy2(src, dst)
        for name in ("bot.py", "fishpond", "web"):
            src = root / name
            if not src.exists():
                continue
            dst = target_dir / name
            if dst.is_dir():
                _sh.rmtree(dst)
            elif dst.exists():
                dst.unlink()
            if src.is_dir():
                _sh.copytree(src, dst)
            else:
                _sh.copy2(src, dst)
        _sh.rmtree(work, ignore_errors=True)
        ver = ""
        try:
            import re as _re3
            m = _re3.search(r'APP_VERSION = "([^"]+)"', (target_dir / "bot.py").read_text(encoding="utf-8"))
            ver = m.group(1) if m else ""
        except Exception:
            pass
        return ver

    async def api_update_apply(self, request):
        self.require_super(request)
        info = await self.update_info(True)
        if not info.get("has_update"):
            return aiohttp_web.json_response({"code": -1, "message": "已经是最新版本"})
        url = info.get("url") or ""
        if not url.startswith(("http://", "https://")):
            await self.report_update_failure("latest.json 里的 url 无效")
            return aiohttp_web.json_response({"code": -1, "message": "latest.json 里的 url 无效"})
        try:
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    await self.report_update_failure(f"下载失败 HTTP {resp.status}")
                    return aiohttp_web.json_response({"code": -1, "message": f"下载失败 HTTP {resp.status}"})
                data = await resp.read()
        except Exception as e:
            await self.report_update_failure(f"下载失败: {e}")
            return aiohttp_web.json_response({"code": -1, "message": f"下载失败: {e}"})
        if not data or len(data) < 2000:
            await self.report_update_failure("下载内容异常（过小）")
            return aiohttp_web.json_response({"code": -1, "message": "下载内容异常"})
        want = (info.get("sha256") or "").lower()
        if want:
            got = hashlib.sha256(data).hexdigest()
            if got != want:
                await self.report_update_failure("校验失败：sha256 不匹配")
                return aiohttp_web.json_response({"code": -1, "message": "校验失败（sha256 不匹配）"})
        # 注意：本方法位于 fishpond/platforms/admin.py，__file__ 指向 admin.py，
        # 入口始终是 BASE/bot.py，不能用 __file__。
        target = BASE / "bot.py"
        try:
            snap_name = self.snapshot_state()
            (BASE / ".update_pending").write_text(snap_name, encoding="utf-8")
            log.info("升级前快照: %s", snap_name)
        except Exception as e:
            log.warning("升级快照失败（继续更新）: %s", e)
        if data[:2] == b"\x1f\x8b":
            try:
                backup = target.parent / ".update_backup"
                ver = self.apply_update_package(data, target.parent, backup)
            except Exception as e:
                await self.report_update_failure(f"目录包更新失败: {e}")
                return aiohttp_web.json_response({"code": -1, "message": f"更新包应用失败: {e}"})
            self.store.set_setting("app_version", str(info.get("latest") or ver or ""))
            asyncio.get_running_loop().create_task(self._restart_soon())
            return aiohttp_web.json_response({"code": 0,
                "message": f"已更新到 {info.get('latest') or ver}（目录包），正在重启…"})
        try:
            compile(data.decode("utf-8"), str(target), "exec")
        except Exception as e:
            await self.report_update_failure(f"代码语法校验失败: {e}")
            return aiohttp_web.json_response({"code": -1, "message": f"更新包代码异常: {e}"})
        try:
            import tempfile
            try:
                backup = target.with_suffix(target.suffix + ".bak")
                backup.write_bytes(target.read_bytes())
            except Exception as be:
                log.warning("更新备份失败: %s", be)
                try:
                    (Path(tempfile.gettempdir()) / (target.name + ".bak")).write_bytes(target.read_bytes())
                except Exception as be2:
                    await self.report_update_failure(f"备份失败，已中止: {be2}")
                    return aiohttp_web.json_response({"code": -1, "message": "备份失败，已中止更新，旧版本未改动"})
            try:
                tmp = target.with_suffix(target.suffix + ".new")
                tmp.write_bytes(data)
            except PermissionError:
                tmp = Path(tempfile.gettempdir()) / (target.name + ".new")
                tmp.write_bytes(data)
            os.replace(tmp, target)
        except Exception as e:
            hint = ""
            if isinstance(e, PermissionError) or "Permission denied" in str(e):
                hint = "（目录权限不足：请在服务器执行 sudo chown -R $USER:$USER /opt/qqbot 后重试）"
            await self.report_update_failure(f"写入失败: {e}{hint}")
            return aiohttp_web.json_response({"code": -1, "message": f"写入失败: {e}{hint}"})
        self.store.set_setting("app_version", str(info.get("latest") or ""))
        asyncio.get_running_loop().create_task(self._restart_soon())
        return aiohttp_web.json_response({"code": 0, "message": f"已更新到 {info.get('latest')}，正在重启…"})

    async def api_login_logs(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        role = acc.get("role")
        if role == "super":
            rows = self.store.login_logs(200)
        elif role == "admin":
            ids = [acc.get("id")]
            for a in self.store.accounts_all():
                if str(a.get("created_by")) == str(acc.get("id")):
                    ids.append(a.get("id"))
            rows = self.store.login_logs(200, ids)
        else:
            rows = self.store.login_logs(200, [acc.get("id")])
        return aiohttp_web.json_response({"code": 0, "logs": rows})

    async def api_admins(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({"code": 0, "admins": self.store.admins()})

    async def api_admin_add(self, request):
        self.require_auth(request)
        data = await request.json()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if not username or len(password) < 6:
            return aiohttp_web.json_response({"code": -1, "message": "用户名不能为空，密码至少 6 位"})
        if not self.store.add_admin(username, password):
            return aiohttp_web.json_response({"code": -1, "message": "该用户名已存在"})
        return aiohttp_web.json_response({"code": 0})

    async def api_admin_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        username = data.get("username")
        if not username:
            return aiohttp_web.json_response({"code": -1, "message": "缺少用户名"})
        if self.store.admin_count() <= 1:
            return aiohttp_web.json_response({"code": -1, "message": "至少要保留一个管理员"})
        self.store.remove_admin(username)
        return aiohttp_web.json_response({"code": 0})

    async def api_master_set_admin_password(self, request):
        if not self.master_ok(request):
            raise aiohttp_web.HTTPForbidden(text="master only")
        d = await request.json()
        pw = str(d.get("password") or "").strip()
        un = str(d.get("username") or "admin").strip() or "admin"
        if len(pw) < 6:
            return aiohttp_web.json_response({"code": -1, "message": "密码至少 6 位"})
        ok = self.store.set_account_password(un, pw)
        if not ok:
            self.store.create_account(un, pw, "super")
        return aiohttp_web.json_response({"code": 0})


add(id="admin.rollback", name="升级回滚", entry="fishpond.platforms.admin:AdminMixin",
    routes=["/api/rollback"], tables=[], settings=[], ui="超级管理员/基本设置",
    files="fishpond/platforms/admin.py", status="active")
add(id="admin.update", name="版本更新", entry="fishpond.platforms.admin:AdminMixin",
    routes=["/api/update/*"], tables=[], settings=["update_*", "app_version"], ui="超级管理员/更新",
    files="fishpond/platforms/admin.py", status="active")
