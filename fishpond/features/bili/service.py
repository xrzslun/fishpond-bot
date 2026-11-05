"""B 站功能模块：解析、热门、学习、笔记、自动学习、主动话题。"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = logging.getLogger("qqbridge")


class BiliMixin:
    BILI_HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                 "Referer": "https://www.bilibili.com/"}

    async def bili_cookies(self) -> dict:
        now = time.time()
        if getattr(self, "_bili_ck", None) and now - getattr(self, "_bili_ck_ts", 0) < 3600:
            return self._bili_ck
        ck = {}
        try:
            async with self.http.get("https://api.bilibili.com/x/frontend/finger/spi", headers=self.BILI_HDRS,
                                      timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json(content_type=None)
                ck = {"buvid3": (d.get("data") or {}).get("b_3", ""), "buvid4": (d.get("data") or {}).get("b_4", "")}
        except Exception:
            pass
        self._bili_ck = ck; self._bili_ck_ts = now
        return ck

    async def bili_json(self, url: str, params: dict = None) -> dict:
        ck = await self.bili_cookies()
        try:
            async with self.http.get(url, params=params, headers=self.BILI_HDRS, cookies=ck,
                                      timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json(content_type=None)
        except Exception as e:
            log.warning("B站请求失败: %s", e)
            return {}

    def bili_ensure_cols(self):
        if getattr(self, "_bili_cols_ok", False):
            return
        with self.store._conn() as c:
            for col in ("kind", "hook", "keywords", "quotes"):
                try:
                    c.execute(f"ALTER TABLE bili_notes ADD COLUMN {col} TEXT")
                except Exception:
                    pass
        self._bili_cols_ok = True

    def bili_memory_context(self, text: str) -> str:
        try:
            self.bili_ensure_cols()
        except Exception:
            return ""
        text = str(text or "")
        asked = any(k in text for k in ("看过", "看了", "学过", "学了", "刷到", "B站", "b站", "视频", "梗", "名言", "记得"))
        tokens = [t for t in re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{3,}", text)
                  if t not in ("什么", "怎么", "这个", "那个", "你还", "知道", "记得", "视频", "一下")][:6]
        rows = []
        with self.store._conn() as c:
            if tokens:
                where = " OR ".join(["title LIKE ? OR summary LIKE ? OR keywords LIKE ?" for _ in tokens])
                params = []
                for t in tokens:
                    params += [f"%{t}%", f"%{t}%", f"%{t}%"]
                rows = c.execute(f"SELECT title,summary,quotes FROM bili_notes WHERE {where} ORDER BY id DESC LIMIT 3", params).fetchall()
            if not rows and asked:
                rows = c.execute("SELECT title,summary,quotes FROM bili_notes ORDER BY id DESC LIMIT 3").fetchall()
        if not rows:
            return ""
        lines = ["\n你平时刷B站学到的东西（这些是你自己的记忆，对方聊到相关话题时可以自然接一句，不要背资料、不要说“根据我的学习”）："]
        for r in rows:
            s2 = str(r["summary"] or "").replace("\n", " ")[:200]
            q = str(r["quotes"] or "").strip()
            line = f"· 《{r['title']}》：{s2}"
            if q:
                line += f"（其中的梗/金句：{q[:80]}）"
            lines.append(line)
        return "\n".join(lines)

    async def bili_search(self, kw: str, n: int = 3) -> list[dict]:
        d = await self.bili_json("https://api.bilibili.com/x/web-interface/search/type",
                                 {"search_type": "video", "keyword": kw, "page": 1})
        out = []
        for it in ((d.get("data") or {}).get("result") or [])[:n]:
            if not isinstance(it, dict):
                continue
            out.append({"bvid": it.get("bvid") or "", "title": re.sub(r"<[^>]+>", "", it.get("title") or ""),
                        "author": it.get("author") or "", "play": it.get("play") or 0,
                        "desc": re.sub(r"<[^>]+>", "", it.get("description") or ""), "pic": it.get("pic") or ""})
        return out

    async def bili_view(self, bvid: str) -> dict:
        d = await self.bili_json("https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
        data = d.get("data") or {}
        if not data:
            return {}
        pages = data.get("pages") or []
        return {"bvid": bvid, "title": data.get("title") or "", "author": (data.get("owner") or {}).get("name") or "",
                "play": ((data.get("stat") or {}).get("view") or 0), "desc": data.get("desc") or "",
                "cid": (pages[0].get("cid") if pages else data.get("cid")), "cover": data.get("pic") or "",
                "duration": int(data.get("duration") or 0)}

    async def bili_subtitles(self, bvid: str, cid) -> str:
        try:
            nav = await self.bili_json("https://api.bilibili.com/x/web-interface/nav")
            wbi = ((nav.get("data") or {}).get("wbi_img") or {})
            img = (wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
            sub = (wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
            mixin = self._wbi_mixin(img, sub)
            params = {"bvid": bvid, "cid": cid}
            params["wts"] = str(int(time.time()))
            q = "&".join(f"{k}={params[k]}" for k in sorted(params))
            sign = __import__("hashlib").md5((q + mixin).encode()).hexdigest()
            url = f"https://api.bilibili.com/x/player/wbi/v2?{q}&w_rid={sign}"
            d = await self.bili_json(url)
            subs = ((d.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
            if not subs:
                return ""
            su = subs[0].get("subtitle_url") or ""
            if su.startswith("//"):
                su = "https:" + su
            async with self.http.get(su, headers=self.BILI_HDRS, timeout=aiohttp.ClientTimeout(total=15)) as r:
                j = await r.json(content_type=None)
            body = j.get("body") or []
            return " ".join(str(x.get("content") or "") for x in body)[:8000]
        except Exception as e:
            log.warning("B站字幕获取失败: %s", e)
            return ""

    def bili_auto_window(self) -> bool:
        try:
            st = (self.store.get_setting("bili_auto_start", "05:00") or "05:00")[:5]
            en = (self.store.get_setting("bili_auto_end", "07:00") or "07:00")[:5]
            now = datetime.now().strftime("%H:%M")
            if st == en:
                return True
            if st < en:
                return st <= now < en
            return now >= st or now < en
        except Exception:
            return False

    async def bili_auto_loop(self):
        await asyncio.sleep(60)
        while True:
            try:
                if (self.store.get_setting("bili_auto_enabled", "0") == "1"
                        and self.bili_auto_window() and (getattr(self, "_bal_num", None) or 99) >= 0.3):
                    next_at = getattr(self, "_bili_next_at", 0)
                    day = datetime.now().strftime("%Y-%m-%d")
                    if getattr(self, "_bili_day", "") != day:
                        self._bili_day = day
                        self._bili_today = 0
                    try:
                        cap = max(1, min(20, int(self.store.get_setting("bili_auto_max", "3") or 3)))
                    except Exception:
                        cap = 3
                    if time.time() >= next_at and getattr(self, "_bili_today", 0) < cap:
                        await self.bili_auto_step()
            except Exception as e:
                log.warning("B站自动学习失败: %s", e)
            await asyncio.sleep(60)

    async def bili_proactive_loop(self):
        await asyncio.sleep(90)
        while True:
            try:
                if (self.store.get_setting("bili_proactive_enabled", "0") == "1"
                        and self.store.get_setting("bili_enabled", "1") == "1"
                        and (getattr(self, "_bal_num", None) or 99) >= 0.3):
                    await self.bili_proactive_step()
            except Exception as e:
                log.warning("主动找话题失败: %s", e)
            await asyncio.sleep(300)

    async def bili_proactive_step(self):
        if self.in_world_rest():
            return
        try:
            minm = max(1, int(self.store.get_setting("bili_proactive_min_mem", "5") or 5))
        except Exception:
            minm = 5
        now = datetime.now()
        hour = now.hour
        today = now.strftime("%Y-%m-%d")
        sent = getattr(self, "_pro_sent", None)
        if sent is None:
            sent = {}; self._pro_sent = sent
        try:
            with self.store._conn() as c:
                qqs = [r["owner_qq"] for r in c.execute(
                    "SELECT owner_qq, COUNT(*) n FROM memories GROUP BY owner_qq HAVING n>=?", (minm,))]
        except Exception:
            qqs = []
        for qq in qqs[:5]:
            if sent.get(qq) == today:
                continue
            hit = self.active_hour(qq)
            if not hit or hit[0] != hour:
                continue
            with self.store._conn() as c:
                rows = c.execute("SELECT title,summary,hook,kind FROM bili_notes ORDER BY id DESC LIMIT 10").fetchall()
            if not rows:
                return
            import random as _r
            pick = _r.choice(rows)
            opener = await self.llm_complete(
                "你在主动找朋友聊天，用刚看的视频开头，口语自然、一句到两句，不要说教，不要列点。",
                f"视频：{pick['title']}\n类型：{pick['kind'] or '其他'}\n内容：{str(pick['summary'])[:300]}\n话术：{pick['hook'] or ''}",
                max_tokens=120, temperature=0.9, timeout=30)
            text = (opener or pick['hook'] or "").strip()
            if not text:
                continue
            try:
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(qq),
                                                      "message": [{"type": "text", "data": {"text": text}}]})
                sent[qq] = today
                log.info("主动找话题 -> %s（活跃时段 %s 点）", qq, hour)
                import random as _rr
                if _rr.random() < 0.3:
                    self.panic_start(qq)
            except Exception:
                pass

    async def bili_share_super(self, title: str, summary: str, link: str):
        if self.store.get_setting("bili_share_super", "1") != "1":
            return
        qqs = self.super_admin_qqs()
        if not qqs:
            return
        style = await self.llm_complete(
            "你是一个普通网友，刚看完一个视频想随手分享给朋友。用口语、自然、带点情绪，1~2 句，不要标题党，不要列要点。",
            f"视频标题：{title}\n内容要点：{summary[:500]}\n链接：{link}",
            max_tokens=120, temperature=0.8, timeout=30)
        points = str(summary or "").strip()
        if points:
            points = "\n".join(points.splitlines()[:6])[:400]
            body = (style or f"刚刷到一个视频：{title}").strip() + "\n" + points + f"\n{link}"
        else:
            body = (style or f"刚刷到一个视频：{title}").strip() + f"\n{link}"
        for qq in qqs:
            try:
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": qq,
                                                      "message": [{"type": "text", "data": {"text": body}}]})
            except Exception:
                pass

    async def bili_auto_step(self):
        topics = [x.strip() for x in re.split(r"[,，\n]+", self.store.get_setting("bili_auto_topics", "") or "") if x.strip()]
        if not topics:
            self._bili_next_at = time.time() + 600
            return
        idx = getattr(self, "_bili_topic_idx", 0) % len(topics)
        kw = topics[idx]
        self._bili_topic_idx = idx + 1
        items = await self.bili_search(kw, 5)
        learned = set()
        with self.store._conn() as c:
            for r in c.execute("SELECT bvid FROM bili_notes"):
                learned.add(r["bvid"])
        pick = next((it for it in items if it["bvid"] not in learned), None)
        if not pick:
            self._bili_next_at = time.time() + 1800
            log.info("B站自动学习：主题 %s 暂无新视频", kw)
            return
        info = await self.bili_view(pick["bvid"]) or pick
        sub = ""
        if info.get("cid"):
            sub = await self.bili_subtitles(pick["bvid"], info.get("cid"))
        material = f"标题：{info.get('title')}\n简介：{info.get('desc')}\n字幕：{sub[:4000] if sub else '（无字幕）'}"
        raw2 = await self.llm_complete('你是学习助理，只输出 JSON：{"kind":"搞笑/伤感/知识/生活/游戏/影视/其他","summary":"3~5 条要点","hook":"一句自然的口语分享"}',
                                       material, max_tokens=420, temperature=0.3, timeout=60)
        kind2, summary, hook2, keywords2, quotes2 = "其他", (raw2 or ""), "", "", ""
        try:
            mm3 = re.search(r"\{.*\}", raw2 or "", re.S)
            if mm3:
                dj2 = json.loads(mm3.group(0))
                kind2 = str(dj2.get("kind") or "其他")[:8]
                summary = str(dj2.get("summary") or "")
                hook2 = str(dj2.get("hook") or "")[:80]
                keywords2 = str(dj2.get("keywords") or "")[:120]
                qs = dj2.get("quotes") or []
                quotes2 = " | ".join(str(x) for x in qs[:3])[:200] if isinstance(qs, list) else str(qs)[:200]
        except Exception:
            pass
        self.bili_ensure_cols()
        with self.store._conn() as c:
            c.execute("INSERT INTO bili_notes(qq,topic,bvid,title,summary,created_at,kind,hook,keywords,quotes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      ("auto", kw, pick["bvid"], info.get("title") or "", (summary or "").strip(), time.time(), kind2, hook2, keywords2, quotes2))
        await self.bili_share_super(info.get("title") or "", (summary or "").strip(),
                                    f"https://www.bilibili.com/video/{pick['bvid']}")
        gid = (self.store.get_setting("bili_auto_group", "") or "").strip()
        if gid.isdigit():
            try:
                pts = "\n".join((summary or "").strip().splitlines()[:5])[:300]
                body = (f"刷到一个视频：{info.get('title') or ''}\n" + (pts + "\n" if pts else "") +
                        f"https://www.bilibili.com/video/{pick['bvid']}")
                await self.onebot_action("send_msg", {"message_type": "group", "group_id": gid,
                                                      "message": [{"type": "text", "data": {"text": body}}]})
            except Exception:
                pass
        self._bili_today = getattr(self, "_bili_today", 0) + 1
        dur = int(info.get("duration") or 0)
        wait = min(2400, max(180, dur if dur > 0 else 600))
        self._bili_next_at = time.time() + wait
        log.info("B站自动学习：%s（%s）时长 %ss，下次 %s 秒后（今日第 %s 条）",
                 info.get("title"), kw, dur, wait, self._bili_today)

    async def handle_bili(self, ws, ev, mtype, text, is_super) -> bool:
        t = str(text or "").strip()
        if not t or self.store.get_setting("bili_enabled", "1") != "1":
            return False
        allow = is_super or self.store.get_setting("bili_allow_all", "0") == "1"
        low = t.lower()
        # 学习 / 热门 / 笔记
        if low.startswith("b站学习") or low.startswith("bilibili学习"):
            if not allow:
                await self.send(ws, mtype, ev, "B站学习只有管理员能用。", record_convo=False)
                return True
            if (getattr(self, "_bal_num", None) or 99) < 0.3:
                await self.send(ws, mtype, ev, "我先省点电，等充上电再学吧。", record_convo=False)
                return True
            kw = re.sub(r"^(b站学习|bilibili学习)\s*", "", t, flags=re.I).strip()
            if not kw:
                await self.send(ws, mtype, ev, "用法：B站学习 主题", record_convo=False)
                return True
            await self.send(ws, mtype, ev, f"开始学习「{kw}」，找视频、看字幕、总结中…", record_convo=False)
            self.spawn(self.bili_learn(ws, ev, mtype, kw), "bili_learn")
            return True
        if low.startswith("b站搜") or low.startswith("bilibili搜"):
            kw = re.sub(r"^(b站搜|bilibili搜)\s*", "", t, flags=re.I).strip()
            if not kw:
                await self.send(ws, mtype, ev, "用法：B站搜 关键词", record_convo=False)
                return True
            items = await self.bili_search(kw, 5)
            if not items:
                await self.send(ws, mtype, ev, f"没搜到「{kw}」。", record_convo=False)
                return True
            out = [f"「{kw}」搜索结果："]
            for i, it in enumerate(items, 1):
                out.append(f"{i}. {it.get('title')}\n   {it.get('author')} · 播放 {it.get('play')}\n   https://www.bilibili.com/video/{it['bvid']}")
            await self.send(ws, mtype, ev, "\n".join(out)[:1500], record_convo=False)
            return True
        if low.startswith("b站总结") or low.startswith("bilibili总结"):
            if not allow:
                await self.send(ws, mtype, ev, "B站总结只有管理员能用。", record_convo=False)
                return True
            raw = re.sub(r"^(b站总结|bilibili总结)\s*", "", t, flags=re.I).strip()
            m = re.search(r"(BV[0-9A-Za-z]{10})", raw)
            bvid = m.group(1) if m else ""
            if not bvid:
                sh = re.search(r"https?://[^\s]+", raw)
                if sh:
                    try:
                        async with self.http.get(sh.group(0), headers=self.BILI_HDRS, allow_redirects=True,
                                                  timeout=aiohttp.ClientTimeout(total=10)) as r:
                            final = str(r.url)
                        mm = re.search(r"(BV[0-9A-Za-z]{10})", final)
                        bvid = mm.group(1) if mm else ""
                    except Exception:
                        bvid = ""
            if not bvid:
                await self.send(ws, mtype, ev, "用法：B站总结 BV号 或 视频链接", record_convo=False)
                return True
            await self.send(ws, mtype, ev, "我去看这个视频，整理一下要点…", record_convo=False)
            self.spawn(self.bili_summarize_one(ws, ev, mtype, bvid), "bili_sum")
            return True
        if low in ("b站热门", "bilibili热门"):
            try:
                d = await self.bili_json("https://api.bilibili.com/x/web-interface/popular", {"ps": 5, "pn": 1})
                items = ((d.get("data") or {}).get("list") or [])[:5]
                if not items:
                    await self.send(ws, mtype, ev, "热门榜暂时拿不到，稍后再试。", record_convo=False)
                    return True
                lines = ["B站热门："]
                for i, it in enumerate(items, 1):
                    lines.append(f"{i}. {it.get('title')}｜{it.get('owner', {}).get('name')}｜播放 {it.get('stat', {}).get('view')}")
                await self.send(ws, mtype, ev, "\n".join(lines), record_convo=False)
            except Exception as e:
                log.warning("热门获取失败: %s", e)
            return True
        if low.startswith("笔记"):
            kw = re.sub(r"^笔记\s*", "", t, flags=re.I).strip()
            rows = []
            with self.store._conn() as c:
                if kw:
                    rows = c.execute("SELECT topic,title,summary FROM bili_notes WHERE topic LIKE ? OR title LIKE ? OR summary LIKE ? ORDER BY id DESC LIMIT 3", (f"%{kw}%", f"%{kw}%", f"%{kw}%")).fetchall()
                else:
                    rows = c.execute("SELECT topic,title,summary FROM bili_notes ORDER BY id DESC LIMIT 3").fetchall()
            if not rows:
                await self.send(ws, mtype, ev, "还没有笔记，先让我「B站学习 主题」吧。", record_convo=False)
            else:
                out = ["我学到的："]
                for r in rows:
                    out.append(f"· {r['title']}\n  {str(r['summary'])[:160]}")
                await self.send(ws, mtype, ev, "\n".join(out), record_convo=False)
            return True
        if low.startswith("找话题") or low.startswith("找个话题"):
            with self.store._conn() as c:
                rows = c.execute("SELECT title,summary,hook,kind FROM bili_notes ORDER BY id DESC LIMIT 5").fetchall()
            if not rows:
                await self.send(ws, mtype, ev, "还没学到东西，先让我刷会儿B站。", record_convo=False)
                return True
            import random as _rnd
            pick = _rnd.choice(rows)
            seed = f"类型：{pick['kind'] or '其他'}\n视频：{pick['title']}\n内容：{str(pick['summary'])[:400]}\n现成话术：{pick['hook'] or ''}"
            opener = await self.llm_complete(
                "你是个普通网友，想用刚看的视频跟朋友搭话。用口语、自然、具体，一句到两句，不要列点，不要标题党。",
                seed, max_tokens=120, temperature=0.9, timeout=30)
            await self.send(ws, mtype, ev, (opener or pick['hook'] or pick['title']), record_convo=False)
            return True
        # 链接 / BV 号解析
        m = re.search(r"(BV[0-9A-Za-z]{10})", t)
        bvid = m.group(1) if m else ""
        if not bvid and ("b23.tv" in t or "bilibili.com" in t):
            short = re.search(r"https?://[^\s]+", t)
            if short:
                try:
                    async with self.http.get(short.group(0), headers=self.BILI_HDRS, allow_redirects=True,
                                              timeout=aiohttp.ClientTimeout(total=10)) as r:
                        final = str(r.url)
                    m2 = re.search(r"(BV[0-9A-Za-z]{10})", final)
                    bvid = m2.group(1) if m2 else ""
                except Exception:
                    bvid = ""
        if not bvid:
            return False
        info = await self.bili_view(bvid)
        if not info:
            await self.send(ws, mtype, ev, f"没找到这个视频：{bvid}", record_convo=False)
            return True
        msg = (f"{info['title']}\nUP：{info['author']}\n播放：{info['play']}\n"
               f"https://www.bilibili.com/video/{bvid}")
        await self.send(ws, mtype, ev, msg, record_convo=False)
        cover = info.get("cover") or ""
        if cover.startswith("//"):
            cover = "https:" + cover
        if cover:
            try:
                await ws.send_str(json.dumps({"action": "send_msg", "params": {
                    "message": [{"type": "image", "data": {"file": cover}}],
                    "message_type": mtype, **({"group_id": ev.get("group_id")} if mtype == "group" else {"user_id": ev.get("user_id")})}},
                    ensure_ascii=False))
            except Exception:
                pass
        return True

    async def bili_summarize_one(self, ws, ev, mtype, bvid: str):
        try:
            info = await self.bili_view(bvid)
            if not info:
                await self.send(ws, mtype, ev, "没找到这个视频。", record_convo=False)
                return
            sub = ""
            if info.get("cid"):
                sub = await self.bili_subtitles(bvid, info.get("cid"))
            material = (f"标题：{info.get('title')}\nUP：{info.get('author')}\n简介：{info.get('desc')}\n"
                        f"字幕：{sub[:6000] if sub else '（无字幕）'}")
            sys = ('你是学习助理。阅读视频简介和字幕，输出 JSON：'
                   '{"kind":"搞笑/伤感/知识/生活/游戏/影视/其他","summary":"5~8 条要点，中文，每条一句话","hook":"一句自然的口语分享","keywords":"3~6个关键词，逗号分隔","quotes":["梗、金句或名言，最多3条"]}。只输出 JSON。')
            raw = await self.llm_complete(sys, material, max_tokens=600, temperature=0.3, timeout=90)
            kind, summary, hook, kws, qs2 = "其他", "", "", "", ""
            try:
                mm = re.search(r"\{.*\}", raw or "", re.S)
                if mm:
                    dj = json.loads(mm.group(0))
                    kind = str(dj.get("kind") or "其他")[:8]
                    summary = str(dj.get("summary") or "")
                    hook = str(dj.get("hook") or "")[:80]
                    kws = str(dj.get("keywords") or "")[:120]
                    qq2 = dj.get("quotes") or []
                    qs2 = " | ".join(str(x) for x in qq2[:3])[:200] if isinstance(qq2, list) else str(qq2)[:200]
            except Exception:
                summary = raw or ""
            self.bili_ensure_cols()
            with self.store._conn() as c:
                c.execute("INSERT INTO bili_notes(qq,topic,bvid,title,summary,created_at,kind,hook,keywords,quotes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (str(ev.get("user_id") or ""), "总结", bvid, info.get("title") or "", summary, time.time(), kind, hook, kws, qs2))
            await self.send(ws, mtype, ev, f"【{info.get('title')}】\n{summary[:1200]}\nhttps://www.bilibili.com/video/{bvid}", record_convo=False)
        except Exception as e:
            log.warning("B站总结失败: %s", e)
            await self.send(ws, mtype, ev, "总结失败，稍后再试。", record_convo=False)

    async def bili_learn(self, ws, ev, mtype, kw):
        try:
            try:
                n = max(1, min(5, int(self.store.get_setting("bili_count", "3") or 3)))
            except Exception:
                n = 3
            items = await self.bili_search(kw, n)
            if not items:
                await self.send(ws, mtype, ev, f"没搜到「{kw}」的视频。", record_convo=False)
                return
            summaries = []
            for it in items:
                info = await self.bili_view(it["bvid"]) or it
                sub = ""
                if info.get("cid"):
                    sub = await self.bili_subtitles(it["bvid"], info.get("cid"))
                material = (f"标题：{info.get('title')}\n简介：{info.get('desc')}\n"
                            f"字幕：{sub[:4000] if sub else '（无字幕）'}")
                system = ('你是学习助理，同时判断视频的类型。阅读简介和字幕，只输出 JSON：'
                          '{"kind":"搞笑/伤感/知识/生活/游戏/影视/其他","summary":"3~5 条要点，中文","hook":"一句适合拿去和朋友聊天的分享话，口语、自然、不超过40字","keywords":"3~6个关键词，逗号分隔","quotes":["视频里的梗、金句或名言，最多3条"]}')
                raw = await self.llm_complete(system, material, max_tokens=420, temperature=0.3, timeout=60)
                kind, summary, hook, kwds, qts = "其他", raw or "", "", "", ""
                try:
                    mm2 = re.search(r"\{.*\}", raw or "", re.S)
                    if mm2:
                        dj = json.loads(mm2.group(0))
                        kind = str(dj.get("kind") or "其他")[:8]
                        summary = str(dj.get("summary") or "")
                        hook = str(dj.get("hook") or "")[:80]
                        kwds = str(dj.get("keywords") or "")[:120]
                        ql = dj.get("quotes") or []
                        qts = " | ".join(str(x) for x in ql[:3])[:200] if isinstance(ql, list) else str(ql)[:200]
                except Exception:
                    pass
                summary = (summary or "").strip()
                self.bili_ensure_cols()
                with self.store._conn() as c:
                    c.execute("INSERT INTO bili_notes(qq,topic,bvid,title,summary,created_at,kind,hook,keywords,quotes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (str(ev.get("user_id") or ""), kw, it["bvid"], info.get("title") or "", summary, time.time(), kind, hook, kwds, qts))
                summaries.append(f"【{info.get('title')}】\n{summary}")
                await self.bili_share_super(info.get("title") or "", summary,
                                            f"https://www.bilibili.com/video/{it['bvid']}")
            await self.send(ws, mtype, ev, f"「{kw}」学习完成，共 {len(items)} 个视频：", record_convo=False)
            for s2 in summaries:
                await asyncio.sleep(0.6)
                await self.send(ws, mtype, ev, s2[:900], record_convo=False)
        except Exception as e:
            log.warning("B站学习失败: %s", e)
            await self.send(ws, mtype, ev, "学习失败，稍后再试。", record_convo=False)

    async def api_bili_config(self, request):
        self.require_super(request)
        keys = ("bili_enabled", "bili_allow_all", "bili_count", "bili_auto_enabled",
                "bili_auto_start", "bili_auto_end", "bili_auto_topics", "bili_auto_max", "bili_share_super",
                "bili_proactive_enabled", "bili_proactive_min_mem", "bili_auto_group")
        if request.method == "GET":
            defaults = {"bili_enabled": "1", "bili_allow_all": "0", "bili_count": "3",
                        "bili_auto_enabled": "0", "bili_auto_start": "05:00", "bili_auto_end": "07:00",
                        "bili_auto_topics": "", "bili_auto_max": "3", "bili_share_super": "1",
                        "bili_proactive_enabled": "0", "bili_proactive_min_mem": "5", "bili_auto_group": ""}
            return aiohttp_web.json_response({"code": 0, **{k: (self.store.get_setting(k, "") or defaults.get(k, "")) for k in keys}})
        d = await request.json()
        for k in keys:
            if k in d:
                self.store.set_setting(k, str(d.get(k) or ""))
        return aiohttp_web.json_response({"code": 0})

    @staticmethod
    def _wbi_mixin(img_key: str, sub_key: str) -> str:
        table = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]
        raw = img_key + sub_key
        return "".join(raw[i] for i in table if i < len(raw))[:32]


add(id="bili.parse", name="B站解析", entry="fishpond.features.bili.service:handle_bili",
    routes=[], tables=[], settings=["bili_enabled"], ui="机器人/B站",
    files="fishpond/features/bili/service.py", status="active")
add(id="bili.learn", name="B站学习", entry="fishpond.features.bili.service:bili_learn",
    routes=[], tables=["bili_notes"], settings=["bili_count"], ui="机器人/B站",
    files="fishpond/features/bili/service.py", status="active")
add(id="bili.auto", name="B站自动学习", entry="fishpond.features.bili.service:bili_auto_loop",
    routes=[], tables=["bili_notes"], settings=["bili_auto_*"], ui="机器人/B站",
    files="fishpond/features/bili/service.py", status="active")
add(id="bili.proactive", name="主动找话题", entry="fishpond.features.bili.service:bili_proactive_loop",
    routes=[], tables=["bili_notes", "memories"], settings=["bili_proactive_*"], ui="机器人/B站",
    files="fishpond/features/bili/service.py", status="active")
add(id="bili.config", name="B站配置接口", entry="fishpond.features.bili.service:api_bili_config",
    routes=["/api/bili/config"], tables=[], settings=["bili_*"], ui="机器人/B站",
    files="fishpond/features/bili/service.py", status="active")
