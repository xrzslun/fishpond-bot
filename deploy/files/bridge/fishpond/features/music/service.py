"""点歌与唱歌模块。"""
import asyncio
import json
import random
import re
import tempfile
import time
from pathlib import Path

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


class MusicMixin:
    async def music_find(self, keyword):
        import urllib.parse as _up
        q = _up.quote(str(keyword)[:40])
        url = f"https://music.163.com/api/search/get?s={q}&type=1&limit=8"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                   "Referer": "https://music.163.com/"}
        try:
            async with self.http.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
            songs = ((data.get("result") or {}).get("songs") or [])
        except Exception as e:
            log.warning("音乐搜索失败: %s", e)
            return None
        deadline = time.time() + 20
        for song in songs[:5]:
            if time.time() > deadline:
                break
            sid = song.get("id")
            if not sid:
                continue
            outer = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
            try:
                async with self.http.get(outer, headers={**headers, "Range": "bytes=0-1023"},
                                         timeout=aiohttp.ClientTimeout(total=6)) as r:
                    ctype = (r.headers.get("Content-Type") or "").lower()
                    final = str(r.url)
                    if r.status in (200, 206) and ctype.startswith("audio/") and "/404" not in final:
                        artists = "、".join(a.get("name", "") for a in (song.get("artists") or []) if a.get("name"))
                        audio = final.replace("http://", "https://", 1)
                        cover = (song.get("album") or {}).get("picUrl", "")
                        if not cover:
                            try:
                                async with self.http.get(
                                    f"https://music.163.com/api/song/detail/?id={sid}&ids=%5B{sid}%5D",
                                    headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as dr:
                                    dd = await dr.json(content_type=None)
                                cover = (((dd.get("songs") or [{}])[0].get("album") or {}).get("picUrl") or "")
                            except Exception:
                                cover = ""
                        return {"id": sid, "name": song.get("name") or keyword, "artist": artists or "未知",
                                "url": audio, "page": f"https://music.163.com/song?id={sid}",
                                "image": cover}
            except Exception:
                continue
        return {}

    async def send_music_card(self, ws, mtype, ev, found):
        variants = [
            {"type": "music", "data": {
                "type": "custom",
                "url": found.get("page", ""),
                "audio": found.get("url", ""),
                "title": found.get("name", ""),
                "content": found.get("artist", ""),
                "image": found.get("image", "") or "",
            }},
        ]
        for seg in variants:
            if mtype == "group":
                action, params = "send_group_msg", {"group_id": ev.get("group_id"), "message": [seg]}
            else:
                action, params = "send_private_msg", {"user_id": ev.get("user_id"), "message": [seg]}
            try:
                res = await self.onebot_call(ws, action, params, timeout=20)
            except Exception:
                continue
            if bool(res) and (res.get("status") in ("ok", "async") or res.get("retcode") == 0):
                return True
        return False

    async def handle_music(self, ws, ev, keyword, mtype):
        kw = str(keyword or "").strip()
        found = await self.music_find(kw)
        if found is None:
            await self.send(ws, mtype, ev, "音乐搜索暂时连不上…等会儿再试试。", record_convo=False)
            return
        if not found:
            text = random.choice([
                f"《{kw}》我翻了一圈，不是会员专享就是版权锁着…放不了，有点小失落。",
                f"没找到能放的《{kw}》，不是要会员就是被锁区了，唉。",
                f"《{kw}》这首我拿不到播放链接，估计是会员歌，扫兴…",
            ])
            await self.send(ws, mtype, ev, text, record_convo=False)
            return
        ok = False
        try:
            ok = await self.send_music_card(ws, mtype, ev, found)
        except Exception as e:
            log.warning("音乐卡片发送失败: %s", e)
        if ok:
            text = f"找到啦～《{found['name']}》- {found['artist']}"
        else:
            text = (f"找到啦～《{found['name']}》- {found['artist']}\n"
                    f"点这里就能听：{found.get('page') or found['url']}")
        await self.send(ws, mtype, ev, text, record_convo=False)
        log.info("音乐分享: %s -> %s（卡片%s）", kw, found.get("name"), "成功" if ok else "失败")

    @staticmethod
    def music_command_keyword(user_text: str) -> str:
        """识别「播放 xxx」类点歌指令。"""
        t = str(user_text or "").strip()
        if not t:
            return ""
        mm = re.match(r'^(?:播放|放一首|放一下|放|来一首|来首|来|听一首|听一下|听)\s*[《"“]?\s*(.+?)'
                      r'\s*[》"”]?\s*(?:吧|呗|呀|啊)?$', t)
        if not mm:
            return ""
        kw = mm.group(1).strip()
        if not (1 <= len(kw) <= 40) or kw in ("列表", "什么", "歌", "音乐"):
            return ""
        return kw

    @staticmethod
    def sing_request(text: str):
        """解析「唱一首 X / 来一首 X / 唱个歌 / 唱两句」；不是唱歌请求返回 None，随便唱返回 ""。"""
        t = str(text or "").strip()
        if not t or len(t) > 40:
            return None
        m2 = re.search(r"来\s*(一|两|三)?\s*(首|句|段)", t)
        if "唱" not in t and not m2:
            return None
        q = re.search(r"[《「\"']([^》」\"']{1,20})[》」\"']", t)
        if q:
            return q.group(1).strip()
        if "唱" in t:
            rest = re.sub(r"^.*?唱", "", t, count=1)
        else:
            rest = t[m2.end():] if m2 else t
        rest = re.sub(r"^(一|两|三)?(首|句|段|个|下|点儿|点)+", "", rest).strip()
        rest = re.sub(r"(给我|来|唱|听听|听一下|听|呗|吧|嘛|呀|啊|哦|。|！|!|，|,|~|～)+$", "", rest).strip()
        if rest.endswith("的歌"):
            rest = rest[:-2]
        if rest.endswith("歌"):
            rest = rest[:-1]
        rest = rest.strip(" 的了")
        if rest in ("一", "两", "三"):
            rest = ""
        return rest[:12]

    async def handle_sing(self, ws, mtype: str, ev: dict, user_id: str, song: str) -> bool:
        """唱两句：只生成 2~4 句（高潮/副歌），不整首。"""
        if song:
            prompt = (f"只输出《{song}》最出名的高潮/副歌部分的 2~4 句歌词，每行不超过 12 个字，最多 4 行。"
                      "不要整首、不要标题、不要解释、不要评论、不要引号；"
                      "如果不确定这首歌，就写 2~4 句风格相近的原创歌词。")
        else:
            prompt = ("只写 2~4 句适合哼唱的短歌词，每行不超过 12 个字，最多 4 行，"
                      "轻松可爱，不要标题、不要解释、不要评论、不要引号。")
        lyrics = ""
        try:
            lyrics = await self.llm_complete("你是一个会唱歌的伙伴，只输出歌词本身。", prompt,
                                             max_tokens=160, temperature=0.8, timeout=20)
        except Exception as e:
            log.warning("生成歌词失败: %s", e)
        lyrics = str(lyrics or "").strip().strip('"“”')
        lines = [ln.strip() for ln in str(lyrics).splitlines() if ln.strip()]
        lyrics = "\n".join(lines[:4])
        if len(lyrics) > 80:
            lyrics = lyrics[:80]
        lyrics = re.sub(r"\n{2,}", "\n", lyrics).strip()
        if not lyrics:
            lyrics = "啦啦啦～这条小鱼今天也在游呀游。"
        title = f"《{song}》" if song else "随便唱两句"
        if self.tts_on() and await self.tts_speak(ws, mtype, ev, lyrics,
                                                    context=self.voice_context()):
            self.reply_count += 1
            log.info("唱歌：%s（%d 字）", title, len(lyrics))
            return True
        await self.send(ws, mtype, ev, f"🎵 {title}：{lyrics}")
        self.reply_count += 1
        return True

    async def api_music_get(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({"code": 0,
            "enabled": self.store.get_setting("music_enabled", "1") == "1"})

    async def api_music_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("music_enabled", "1" if data.get("enabled") else "0")
        return aiohttp_web.json_response({"code": 0})


add(id="music.core", name="点歌与唱歌", entry="fishpond.features.music.service:handle_music",
    routes=["/api/music", "/api/music/config"], tables=[], settings=["music_*"], ui="聊天/接话模式",
    files="fishpond/features/music/service.py", status="active")
