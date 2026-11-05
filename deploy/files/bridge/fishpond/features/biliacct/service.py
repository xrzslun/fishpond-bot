"""B站账号实况：扫码登录、刷推荐、点赞、评论、私信超管。"""
import asyncio
import base64
import json
import logging
import random
import time

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = logging.getLogger("qqbridge")


add(id="bili.account", name="B站账号实况", entry="fishpond/features/biliacct/service.py",
     routes=["/api/bili/account/status", "/api/bili/account/config", "/api/bili/account/qr",
             "/api/bili/account/qr/poll", "/api/bili/account/action", "/api/bili/account/logs",
             "/api/bili/account/cookies"],
     tables=[], settings=["bili_acct_*"], ui="机器人/B站", files=["fishpond/features/biliacct/service.py"])
class BiliAccountMixin:
    def bili_log(self, action: str, detail: str, ok: bool = True):
        try:
            with self.store._conn() as c:
                c.execute("CREATE TABLE IF NOT EXISTS bili_acct_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, ok INTEGER, created_at REAL)")
                c.execute("INSERT INTO bili_acct_log(action,detail,ok,created_at) VALUES(?,?,?,?)",
                          (str(action)[:20], str(detail)[:300], 1 if ok else 0, time.time()))
                c.execute("DELETE FROM bili_acct_log WHERE id NOT IN (SELECT id FROM bili_acct_log ORDER BY id DESC LIMIT 200)")
        except Exception:
            pass

    def bili_cred(self):
        sess = self.store.get_setting("bili_sessdata", "")
        jct = self.store.get_setting("bili_bili_jct", "")
        buvid = self.store.get_setting("bili_buvid3", "")
        if not sess:
            return None
        try:
            from bilibili_api import Credential
            return Credential(sessdata=sess, bili_jct=jct, buvid3=buvid,
                              dedeuserid=self.store.get_setting("bili_uid", "") or "")
        except Exception:
            return None

    def bili_acct_day_reset(self):
        st = self.world_state() or {}
        day = st.get("day_index", 0)
        if str(self.store.get_setting("bili_acct_day", "")) != str(day):
            self.store.set_setting("bili_acct_day", str(day))
            self.store.set_setting("bili_acct_comments", "0")
            self.store.set_setting("bili_acct_likes", "0")
            self.store.set_setting("bili_acct_dms", "0")

    async def api_bili_acct_status(self, request):
        self.require_super(request)
        self.bili_acct_day_reset()
        return aiohttp_web.json_response({"code": 0, "account": {
            "uid": self.store.get_setting("bili_uid", ""),
            "uname": self.store.get_setting("bili_uname", ""),
            "enabled": "1" if self.store.get_setting("bili_sessdata", "") else "0",
            "super_mid": self.store.get_setting("bili_super_mid", ""),
            "super_uname": self.store.get_setting("bili_super_uname", ""),
            "comment_max": self.store.get_setting("bili_acct_comment_max", "2"),
            "like_max": self.store.get_setting("bili_acct_like_max", "8"),
            "dm_max": self.store.get_setting("bili_acct_dm_max", "5"),
            "comments": self.store.get_setting("bili_acct_comments", "0"),
            "likes": self.store.get_setting("bili_acct_likes", "0"),
            "dms": self.store.get_setting("bili_acct_dms", "0"),
            "risk": self.store.get_setting("bili_acct_risk", ""),
            "qr_state": self.store.get_setting("bili_qr_state", ""),
            "warn": "该功能为登录态自动化，可能触发风控、限制评论/私信，严重会封号。请使用可放弃的小号。",
        }})

    async def api_bili_acct_action(self, request):
        self.require_super(request)
        d = await request.json()
        action = str(d.get("action") or "browse")
        if action == "browse":
            r = await self.bili_acct_session(force=True, dry=d.get("dry"))
            return aiohttp_web.json_response({"code": 0, "result": r})
        if action == "dm":
            cred = self.bili_cred()
            mid = str(self.store.get_setting("bili_super_mid", "")).strip()
            if not cred or not mid.isdigit():
                return aiohttp_web.json_response({"code": -1, "message": "未登录或未填超管 mid"})
            try:
                from bilibili_api import session as bsession
                await bsession.send_msg(cred, receiver_id=int(mid), msg_type=bsession.EventType.TEXT,
                                        content=str(d.get("text") or "在吗")[:100])
                self.bili_log("dm", "手动私信超管", True)
                return aiohttp_web.json_response({"code": 0})
            except Exception as e:
                self.bili_log("dm", f"私信失败: {e}", False)
                return aiohttp_web.json_response({"code": -1, "message": str(e)[:160]})
        if action == "like":
            return aiohttp_web.json_response({"code": -1, "message": "请用 browse 刷一次"})
        return aiohttp_web.json_response({"code": -1, "message": "未知操作"})

    async def api_bili_acct_logs(self, request):
        self.require_super(request)
        rows = []
        try:
            with self.store._conn() as c:
                c.execute("CREATE TABLE IF NOT EXISTS bili_acct_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, ok INTEGER, created_at REAL)")
                rows = [dict(r) for r in c.execute("SELECT * FROM bili_acct_log ORDER BY id DESC LIMIT 30")]
        except Exception:
            pass
        return aiohttp_web.json_response({"code": 0, "items": rows})

    async def api_bili_acct_config(self, request):
        self.require_super(request)
        d = await request.json()
        if "super_mid" in d:
            v = str(d.get("super_mid") or "").strip()
            if v and not v.isdigit():
                uname = str(d.get("super_uname") or self.store.get_setting("bili_super_uname", "")).strip()
                resolved = ""
                if uname:
                    try:
                        from bilibili_api import search
                        sr = await search.search_by_type(uname, search.SearchObjectType.USER, page=1, page_size=10)
                        for it in (sr or {}).get("result") or []:
                            if str(it.get("uname") or "") == uname or not resolved:
                                resolved = str(it.get("mid") or "")
                            if str(it.get("uname") or "") == uname:
                                break
                    except Exception as e:
                        log.warning("搜索超管 mid 失败: %s", e)
                if not resolved:
                    return aiohttp_web.json_response({"code": -1, "message": "mid 必须是纯数字；自动搜索失败，请打开个人主页复制 space.bilibili.com/数字"})
                d["super_mid"] = resolved
                self.store.set_setting("bili_super_mid", resolved)
        for k, key in (("enabled", "bili_acct_enabled"), ("super_mid", "bili_super_mid"),
                       ("super_uname", "bili_super_uname"), ("comment_max", "bili_acct_comment_max"),
                       ("like_max", "bili_acct_like_max"), ("dm_max", "bili_acct_dm_max")):
            if k in d:
                self.store.set_setting(key, str(d.get(k))[:80])
        return aiohttp_web.json_response({"code": 0})

    async def api_bili_acct_qr(self, request):
        self.require_super(request)
        try:
            now = time.time()
            key = getattr(self, "_bili_qr_key", "") or self.store.get_setting("bili_qr_key", "")
            img = getattr(self, "_bili_qr_img", "") or self.store.get_setting("bili_qr_img", "")
            try:
                saved_at = float(self.store.get_setting("bili_qr_at", "0") or 0)
            except Exception:
                saved_at = 0
            now = time.time()
            if not getattr(self, "_bili_qr_at", 0) and saved_at:
                self._bili_qr_at = saved_at
            force = request.query.get("refresh") == "1"
            if key and img and not force and now - getattr(self, "_bili_qr_at", 0) < 150:
                return aiohttp_web.json_response({"code": 0, "image": img, "cached": True})
            async with self.http.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36", "Referer": "https://www.bilibili.com/"},
                                     timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json(content_type=None)
            data = (d or {}).get("data") or {}
            url = data.get("url") or ""
            key = data.get("qrcode_key") or ""
            if not url or not key:
                return aiohttp_web.json_response({"code": -1, "message": "B站二维码接口异常"})
            import io
            import qrcode as _qr
            buf = io.BytesIO()
            _qr.make(url).save(buf, format="PNG")
            self._bili_qr_key = key
            self._bili_qr_at = now
            self._bili_qr_img = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            self.store.set_setting("bili_qr_key", key)
            self.store.set_setting("bili_qr_img", self._bili_qr_img)
            self.store.set_setting("bili_qr_at", str(now))
            return aiohttp_web.json_response({"code": 0, "image": self._bili_qr_img})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": f"生成二维码失败: {e}"})

    async def api_bili_acct_qr_poll(self, request):
        self.require_super(request)
        key = getattr(self, "_bili_qr_key", "") or self.store.get_setting("bili_qr_key", "")
        if not key:
            return aiohttp_web.json_response({"code": -1, "message": "还没有二维码"})
        try:
            from urllib.parse import urlparse, parse_qs
            async with self.http.get("https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                                     params={"qrcode_key": key}, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36", "Referer": "https://www.bilibili.com/"},
                                     timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json(content_type=None)
            data = (d or {}).get("data") or {}
            raw_code = data.get("code")
            code = int(raw_code) if raw_code is not None else -1
            sv = {0: "done", 86101: "scan", 86090: "confirm", 86038: "timeout"}.get(code, str(code))
            self.store.set_setting("bili_qr_state", sv)
            log.info("B站扫码状态: %s", sv)
            if sv == "timeout":
                self._bili_qr_key = ""
                self.store.set_setting("bili_qr_key", "")
                return aiohttp_web.json_response({"code": 0, "state": "timeout"})
            if sv != "done":
                return aiohttp_web.json_response({"code": 0, "state": sv})
            url = str(data.get("url") or "")
            q = parse_qs(urlparse(url).query)
            sess = (q.get("SESSDATA") or [""])[0] or (q.get("sessdata") or [""])[0]
            jct = (q.get("bili_jct") or [""])[0]
            uid = (q.get("DedeUserID") or [""])[0] or (q.get("dedeuserid") or [""])[0]
            if not sess:
                sess = (r.cookies.get("SESSDATA").value if r.cookies.get("SESSDATA") else "")
                jct = jct or (r.cookies.get("bili_jct").value if r.cookies.get("bili_jct") else "")
                uid = uid or (r.cookies.get("DedeUserID").value if r.cookies.get("DedeUserID") else "")
            if hasattr(sess, "value"):
                sess = sess.value
            if hasattr(jct, "value"):
                jct = jct.value
            if hasattr(uid, "value"):
                uid = uid.value
            log.info("扫码完成: sess=%s jct=%s uid=%s", len(str(sess)), len(str(jct)), str(uid))
            if not sess or not str(uid).isdigit():
                self.store.set_setting("bili_qr_state", "done_no_cookie")
                return aiohttp_web.json_response({"code": -1, "message": "扫码成功但没拿到 Cookie，请改用 Cookie 登录"})
            self.store.set_setting("bili_sessdata", str(sess))
            self.store.set_setting("bili_bili_jct", str(jct))
            self.store.set_setting("bili_uid", str(uid))
            uname = ""
            try:
                cred = self.bili_cred()
                from bilibili_api import user
                info = await user.User(str(uid), cred).get_user_info()
                uname = info.get("name") or ""
                self.store.set_setting("bili_uname", uname)
                self.store.set_setting("bili_acct_risk", "")
            except Exception as e:
                log.warning("扫码后校验失败: %s", e)
            self._bili_qr_key = ""
            self.store.set_setting("bili_qr_key", "")
            self.bili_log("qr", f"扫码登录成功: {uname or uid}", True)
            return aiohttp_web.json_response({"code": 0, "state": "done", "uid": str(uid), "uname": uname})
        except Exception as e:
            self.store.set_setting("bili_qr_state", f"error:{e}")
            log.warning("B站扫码轮询失败: %s", e)
            return aiohttp_web.json_response({"code": -1, "message": f"轮询失败: {e}"})

    async def api_bili_acct_cookies(self, request):
        self.require_super(request)
        d = await request.json()
        sess = str(d.get("sessdata") or "").strip()
        jct = str(d.get("bili_jct") or "").strip()
        uid = str(d.get("uid") or "").strip()
        if not sess or not jct or not uid.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "SESSDATA、bili_jct、UID 都要填"})
        self.store.set_setting("bili_sessdata", sess)
        self.store.set_setting("bili_bili_jct", jct)
        self.store.set_setting("bili_uid", uid)
        uname = ""
        try:
            cred = self.bili_cred()
            from bilibili_api import user
            info = await user.User(uid, cred).get_user_info()
            uname = info.get("name") or ""
            self.store.set_setting("bili_uname", uname)
            self.store.set_setting("bili_acct_risk", "")
        except Exception as e:
            self.bili_log("cookie", f"校验失败: {e}", False)
            return aiohttp_web.json_response({"code": -1, "message": f"Cookie 无效或已过期: {str(e)[:120]}"})
        self.bili_log("cookie", f"Cookie 登录成功: {uname or uid}", True)
        return aiohttp_web.json_response({"code": 0, "uid": uid, "uname": uname})

    def _bili_risk(self, e: Exception):
        text = str(e)
        if any(x in text for x in ("-412", "-352", "-403", "风控", "captcha", "请求过于频繁")):
            self.store.set_setting("bili_acct_risk", f"{int(time.time())}:{text[:120]}")
            log.warning("B站风控: %s", text[:160])

    async def bili_acct_session(self, force: bool = False, dry: bool = False):
        cred = self.bili_cred()
        if not cred:
            return {"error": "未登录：凭据为空，请重新扫码或改用 Cookie 登录"}
        st = self.world_state() or {}
        if not force and (self.in_world_rest() or str(st.get("place")) != "家"):
            return {}
        try:
            self.bili_acct_day_reset()
            from bilibili_api import homepage
            feed = await homepage.get_videos(cred)
            items = (feed or {}).get("item") or ((feed or {}).get("data") or {}).get("item") or []
            items = [x for x in items if (x.get("bvid") or x.get("id"))]
            if not items:
                self.bili_log("browse", "推荐流为空", False)
                return {"error": "推荐流为空"}
            pick = random.choice(items)
            bvid = pick.get("bvid") or (("BV" + str(pick.get("bvid"))) if pick.get("bvid") else "")
            title = pick.get("title") or ""
            if not bvid:
                return {"error": "没有 bvid"}
            from bilibili_api import video
            v = video.Video(bvid=bvid, credential=cred)
            likes = int(self.store.get_setting("bili_acct_likes", "0"))
            like_max = int(self.store.get_setting("bili_acct_like_max", "8") or 8)
            liked = commented = False
            if likes < like_max and (dry or random.random() < 0.8):
                try:
                    if not dry:
                        await v.like(True)
                        self.store.set_setting("bili_acct_likes", str(likes + 1))
                    liked = True
                except Exception as e:
                    self._bili_risk(e)
            comments = int(self.store.get_setting("bili_acct_comments", "0"))
            cmax = int(self.store.get_setting("bili_acct_comment_max", "2") or 2)
            if comments < cmax and (dry or random.random() < 0.5):
                text = await self._bili_make_comment(title, str(pick.get("desc") or ""))
                if text:
                    try:
                        from bilibili_api import comment as bcomment
                        info = await v.get_info()
                        if not dry:
                            await bcomment.send_comment(text, oid=int(info["aid"]), type_=bcomment.CommentResourceType.VIDEO, credential=cred)
                            self.store.set_setting("bili_acct_comments", str(comments + 1))
                        commented = True
                    except Exception as e:
                        self._bili_risk(e)
            self.store.set_setting("bili_acct_last", str(time.time()))
            self.store.set_setting("bili_last_video_title", title[:80])
            self.store.set_setting("bili_last_video_url", f"https://www.bilibili.com/video/{bvid}")
            self.bili_log("browse", f"{title[:30]} 点赞{'是' if liked else '否'} 评论:{'有' if commented else '无'}", True)
            return {"title": title, "bvid": bvid, "liked": liked, "commented": commented, "dry": bool(dry)}
        except Exception as e:
            self._bili_risk(e)
            log.warning("B站私信检查失败: %s", e)
            self.bili_log("browse", f"失败: {e}", False)
            return {"error": str(e)[:160]}

    async def _bili_make_comment(self, title: str, desc: str) -> str:
        super_uname = self.store.get_setting("bili_super_uname", "")
        at = ""
        if super_uname and random.random() < 0.25:
            at = f"@{super_uname} "
        try:
            text = await self.llm_complete(
                "你是普通B站网友。看视频标题和简介，写一条自然、口语、不重复的评论，20~40字，"
                "不要AI味，不要引战，不碰政治、低俗、人身攻击。只输出评论正文。",
                f"标题：{title}\n简介：{desc[:300]}", max_tokens=80, temperature=0.9, timeout=30)
            text = " ".join(str(text or "").split())[:60]
            return (at + text).strip() if text else ""
        except Exception:
            return ""

    async def bili_acct_dm_poll(self):
        cred = self.bili_cred()
        mid = str(self.store.get_setting("bili_super_mid", "")).strip()
        if not cred or not mid.isdigit():
            return
        try:
            from bilibili_api import session as bsession
            data = await bsession.get_sessions(cred, session_type=1)
            sessions = (data or {}).get("session_list") or ((data or {}).get("data") or {}).get("session_list") or []
            target = next((x for x in sessions if str(x.get("talker_id")) == mid), None)
            if not target:
                return
            msgs = await bsession.fetch_session_msgs(int(mid), cred, session_type=1)
            items = (msgs or {}).get("messages") or ((msgs or {}).get("data") or {}).get("messages") or []
            if not items:
                return
            items = sorted(items, key=lambda x: int(x.get("timestamp") or 0))
            incoming = [x for x in items if str(x.get("sender_uid")) == mid]
            if not incoming:
                return
            last = incoming[-1]
            content = last.get("content") or ""
            try:
                content = json.loads(content).get("content", content)
            except Exception:
                pass
            last_key = str(last.get("msg_key") or last.get("msg_seqno") or "")
            if last_key and last_key == self.store.get_setting("bili_last_dm_key", ""):
                return
            self.store.set_setting("bili_last_dm_key", last_key)
            vtitle = self.store.get_setting("bili_last_video_title", "")
            vurl = self.store.get_setting("bili_last_video_url", "")
            ctx = f"你刚在B站刷到视频《{vtitle}》。对方问起就自然聊，可以带链接 {vurl}" if vtitle else "你刚刷了会儿B站。"
            reply = await self.llm_complete(
                "你是一个普通B站网友，正在和你的超级管理员朋友私聊。用口语回1~2句，自然，不要客服腔。"
                "如果对方问视频内容或让你分享，就把链接原样带上，不要编造没看过的细节。",
                f"{ctx}\n对方说：{str(content)[:300]}", max_tokens=160, temperature=0.9, timeout=30)
            reply = " ".join(str(reply or "").split())[:200]
            if reply:
                if vurl and any(k in str(content) for k in ("什么", "内容", "分享", "看看", "链接", "描述", "发我")) and vurl not in reply:
                    reply = (reply + "\n" + vurl)[:260]
                await bsession.send_msg(cred, receiver_id=int(mid), msg_type=bsession.EventType.TEXT, content=reply)
                dms = int(self.store.get_setting("bili_acct_dms", "0"))
                self.store.set_setting("bili_acct_dms", str(dms + 1))
        except Exception as e:
            self._bili_risk(e)

    async def bili_acct_loop(self):
        await asyncio.sleep(180)
        while True:
            try:
                now = time.time()
                if self.bili_cred():
                    await self.bili_acct_dm_poll()
                    try:
                        last = float(self.store.get_setting("bili_acct_last", "0") or 0)
                    except Exception:
                        last = 0
                    if now - last > 2700 and random.random() < 0.5:
                        await self.bili_acct_session()
            except Exception as e:
                log.warning("B站账号循环异常: %s", e)
            await asyncio.sleep(60)
