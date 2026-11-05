"""聊天调度模块：消息解析、回复决策、LLM 调用、休息与频率。"""
import asyncio
import json
from collections import deque
import random
import re
import secrets
import time
from datetime import datetime

import aiohttp

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


class ChatMixin:
    def reply_segments(self) -> int:
        if self.store.get_setting("thrifty_mode", "0") == "1":
            return 1
        mode = self.store.get_setting("reply_seg_mode", "fixed")
        try:
            if mode == "random":
                lo = max(1, min(10, int(self.store.get_setting("reply_seg_min", "1") or 1)))
                hi = max(lo, min(10, int(self.store.get_setting("reply_seg_max", "3") or 3)))
                return random.randint(lo, hi)
            n = int(self.store.get_setting("reply_seg_fixed", "2") or 2)
        except ValueError:
            n = 2
        return max(1, min(10, n))

    def split_reply(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        maxn = self.reply_segments()
        if maxn <= 1:
            return [text]
        if "|||" in text:
            parts = [p.strip() for p in text.split("|||") if p.strip()]
        else:
            parts = [p.strip() for p in re.split(r"(?<=[。！？!?…\n])", text) if p.strip()]
        if len(parts) <= maxn:
            return parts
        n = len(parts)
        chunk = (n + maxn - 1) // maxn
        merged = ["".join(parts[i:i + chunk]) for i in range(0, n, chunk)]
        return merged[:maxn]

    @staticmethod
    def exact_word_hit(text: str, words: list[str]) -> bool:
        import re as _re
        clean = lambda x: _re.sub(r"[\s，。！？、,.!?：:；;~～…\"'“”‘’()（）]+", "", str(x or ""))
        n = clean(text)
        if not n:
            return False
        return any(n == clean(w) for w in words if w)

    @staticmethod
    def parse_hhmm(value: str, default: str) -> int:
        try:
            hh, mm = str(value or default).strip().split(":")
            return max(0, min(23, int(hh))) * 60 + max(0, min(59, int(mm)))
        except Exception:
            hh, mm = default.split(":")
            return int(hh) * 60 + int(mm)

    def rest_window(self) -> bool:
        if self.store.get_setting("rest_enabled", "0") != "1":
            return False
        start = self.parse_hhmm(self.store.get_setting("rest_start", "22:00"), "22:00")
        end = self.parse_hhmm(self.store.get_setting("rest_end", "08:00"), "08:00")
        lt = time.localtime()
        cur = lt.tm_hour * 60 + lt.tm_min
        if start == end:
            return False
        if start < end:
            return start <= cur < end
        return cur >= start or cur < end

    @staticmethod
    def rest_phrase() -> str:
        h = time.localtime().tm_hour
        if 5 <= h < 11:
            return "早上好"
        if 11 <= h < 13:
            return "中午好"
        if 13 <= h < 18:
            return "下午好"
        return "晚上好"

    async def rest_notice_text(self, ending: bool) -> str:
        phrase = self.rest_phrase()
        if ending:
            fallback = f"{phrase}，我休息好啦，继续聊～"
            prompt = (
                "你是QQ群里的机器人，刚休息完回来。用一句简短自然的话告诉群里你回来了，"
                f"开头带上「{phrase}」，口语化、不超过30字；绝对不要出现「晚安」两个字。"
            )
        else:
            fallback = f"{phrase}，我去休息了，明天再聊～"
            prompt = (
                "你是QQ群里的机器人，现在要去休息了。用一句简短自然的话告诉群里你要休息了、明天再聊，"
                f"开头带上「{phrase}」，口语化、不超过30字；绝对不要出现「晚安」两个字。"
            )
        provider = self.current_provider()
        if not provider.get("api_key"):
            return fallback
        try:
            payload = {"model": provider.get("model") or self.model,
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.8, "max_tokens": 60}
            async with self.http.post(
                f"{provider['base_url']}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
                self.record_usage(data.get("usage"), "notice")
                text = ((data.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
            if text and "晚安" not in text:
                return text
        except Exception as e:
            log.warning("休息通知生成失败: %s", e)
        return fallback

    def rest_announce_groups(self) -> list[str]:
        groups = self.store.rest_notify_groups() or self.store.groups()
        out = []
        for g in groups:
            g = str(g)
            if g and g not in out:
                out.append(g)
        return out[:30]

    async def rest_announce(self, ending: bool):
        if self.store.get_setting("rest_notify", "1") != "1":
            return
        ws = getattr(self, "ws", None)
        if ws is None or not self.connected:
            return
        text = await self.rest_notice_text(ending)
        for idx, gid in enumerate(self.rest_announce_groups()):
            if idx:
                await asyncio.sleep(random.uniform(30, 120))
            ev = {"message_type": "group", "group_id": gid, "user_id": str(self.self_id)}
            await self.send(ws, "group", ev, text)

    def rest_allows(self, mtype: str, gid, uid: str) -> bool:
        users = [str(x) for x in self.store.rest_users()]
        groups = [str(x) for x in self.store.rest_groups()]
        if mtype == "group":
            if groups and str(gid) in groups:
                return True
            return str(uid) in users
        return str(uid) in users

    async def ai_review_memories(self, rows, on_progress=None):
        model = (self.store.get_setting("memory_review_model", "") or "").strip()
        system = (
            "你是严格的记忆审核员，负责判断哪些记忆值得长期保留。\n"
            "【保留 KEEP】关于这个人的长期稳定信息：昵称/称呼、喜好厌恶、性格习惯、重要关系、"
            "约定、重要日期、长期目标。\n"
            "【删除 DELETE】一次性事务：让 AI 做过的事、任务指令、操作步骤、教程、部署/配置/密钥/服务器、"
            "安全提醒、临时计划、功能要求、对 AI 的提问、通用常识、重复信息。\n"
            "判断标准：这条信息在三个月后的对话里还有用吗？有用就 KEEP，只是当时有用就 DELETE。\n"
            "拿不准一律 KEEP。\n"
            "示例：\n"
            "昵称是心如止水 -> KEEP\n"
            "喜欢吃辣 -> KEEP\n"
            "养了只猫叫小鲸 -> KEEP\n"
            "约好周末一起打游戏 -> KEEP\n"
            "提醒密钥要保密 -> DELETE\n"
            "要求生成文字版教程 -> DELETE\n"
            "提到今天更新了好几个版本 -> DELETE\n"
            "问服务器多少钱 -> DELETE\n"
            "输出 JSON：{\"items\":[{\"id\":1,\"action\":\"keep\"或\"delete\",\"reason\":\"简短理由\"}]}，只输出 JSON。"
        )
        cand = {}
        sem = asyncio.Semaphore(6)

        def parse_json(out):
            try:
                import re as _re
                m = _re.search(r"\{.*\}", out, _re.S)
                return json.loads(m.group(0)) if m else {}
            except Exception:
                return {}

        async def classify(chunk):
            async with sem:
                listing = "\n".join(f'{r["id"]}. {r["content"]}' for r in chunk)
                out = await self.llm_complete(system, listing, max_tokens=2500, temperature=0.1, model=model, timeout=120)
            data = parse_json(out or "")
            got = {}
            for it in data.get("items", []):
                if str(it.get("action")) == "delete":
                    try:
                        got[int(it.get("id"))] = str(it.get("reason") or "")[:80]
                    except Exception:
                        pass
            if on_progress:
                on_progress(len(chunk))
            return got

        chunks = [rows[i:i + 50] for i in range(0, len(rows), 50)]
        if chunks:
            for part in await asyncio.gather(*[classify(c) for c in chunks], return_exceptions=True):
                if isinstance(part, dict):
                    cand.update(part)
        if not cand:
            return []
        final = list(cand.keys())
        self._last_review_reasons = {i: cand[i] for i in final}
        return final

    async def llm_complete(self, system: str, user: str, max_tokens: int = 160, temperature: float = 0.2, model: str = "", timeout: int = 30) -> str:
        provider = self.current_provider() or {}
        key = provider.get("api_key") or ""
        if not key:
            return ""
        base = (provider.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
        model = model or provider.get("model") or "deepseek-chat"
        mt = max_tokens
        for _ in range(2):
            try:
                async with self.http.post(
                    base + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "system", "content": system},
                                                      {"role": "user", "content": user}],
                          "temperature": temperature, "max_tokens": mt},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status != 200:
                        return ""
                    data = await resp.json(content_type=None)
                    self.record_usage(data.get("usage"), "complete")
                    msg = ((data.get("choices") or [{}])[0].get("message") or {})
                    content = (msg.get("content") or "").strip()
                    if content:
                        return content
                    if msg.get("reasoning_content") and mt < 3000:
                        mt = min(4000, max(1500, mt * 4))
                        continue
                    return ""
            except Exception:
                return ""

    async def extract_memories(self, uid: str, level: str, user_text: str, reply: str, history=None):
        if not self.memory_enabled():
            return
        if level == "high":
            system = ("你是超级管理员的记忆提取器。提取关于这个人的【长期有用信息】，每行一条，最多 3 条："
                      "身份/称呼、喜好厌恶、性格习惯、重要关系、约定、重要日期，"
                      "以及重要事件、计划、决定、项目进展（带时间）。"
                      "不要记手机号、密码、身份证、住址、银行卡、验证码。"
                      "不要输出编号/解释；没有值得记的就输出：无")
        else:
            system = ("你是记忆提取器。只提取关于这个人的【长期稳定信息】，每行一条，最多 3 条："
                  "身份/称呼、喜好厌恶、性格习惯、重要关系、约定、重要日期。"
                  "禁止记录：一次性任务指令、要求 AI 做的事、操作步骤、部署/配置/密钥/服务器等事务细节、"
                  "安全提醒、临时计划、对机器人的功能要求。"
                  "不要记手机号、密码、身份证、住址、银行卡、验证码。"
                  "只输出记忆内容本身，不要编号/解释；没有值得记的就输出：无")
        convo = ""
        for h in list(history or [])[-8:]:
            role = "用户" if h.get("role") == "user" else "机器人"
            convo += f"{role}：{str(h.get('content') or '')[:200]}\n"
        for t in list(getattr(self, "_recent_msgs", {}).get(str(uid), []))[-8:]:
            line = f"用户：{t}"
            if line not in convo:
                convo += line + "\n"
        if convo.strip():
            user = f"用户QQ：{uid}\n最近的对话：\n{convo}\n请提取值得长期记住的关键点。"
        else:
            user = f"用户QQ：{uid}\n用户说：{user_text}\n机器人回复：{reply}"
        out = await self.llm_complete(system, user, max_tokens=220)
        if not out:
            return
        if (reply or "").startswith("（AI 服务"):
            return
        import re as _re
        sens = _re.compile(r"(1[3-9]\d{9}|\d{15,19}|密码|身份证|银行卡|住址|验证码)")
        existing = set()
        try:
            for i in self.store.mem_by_owner(str(uid), None, 200, all_levels=True):
                existing.add(i["content"])
        except Exception as e:
            log.warning("读取已有记忆失败（去重可能不准）: %s", e)
        added = 0
        for line in out.splitlines():
            t = line.strip().lstrip("-*0123456789.、 ").strip()
            if not t or t == "无" or len(t) > 80:
                continue
            if sens.search(t):
                continue
            if level != "high" and self.store.mem_is_noise(t):
                continue
            if any(self.store.mem_sim(t, e) for e in existing):
                continue
            self.store.mem_add(str(uid), t, level, "auto")
            existing.add(t)
            added += 1
        if added:
            log.info("记忆提取 QQ%s(%s): 新增 %d 条", uid, level, added)

    async def detect_gender(self, ws, mtype: str, gid, uid: str, sender: dict) -> str:
        if self.store.get_setting("gender_aware", "0") != "1":
            return ""
        sex = str((sender or {}).get("sex") or "").lower()
        if sex in ("male", "female"):
            return sex
        key = (str(gid or "p"), str(uid))
        cache = getattr(self, "_gender_cache", {})
        hit = cache.get(key)
        if hit and time.time() - hit[1] < 3600:
            return hit[0]
        sex_res = ""
        try:
            res = None
            if mtype == "group" and gid:
                res = await self.onebot_call(ws, "get_group_member_info", {"group_id": int(gid), "user_id": int(uid)})
            if isinstance(res, dict) and res.get("status") == "ok":
                sex_res = str(((res.get("data") or {}).get("sex")) or "").lower()
            if sex_res not in ("male", "female"):
                res2 = await self.onebot_call(ws, "get_stranger_info", {"user_id": int(uid)})
                if isinstance(res2, dict) and res2.get("status") == "ok":
                    sex_res = str(((res2.get("data") or {}).get("sex")) or "").lower()
        except Exception:
            sex_res = ""
        if sex_res not in ("male", "female"):
            sex_res = ""
        # 未知缓存 10 分钟，避免每条消息都打两次接口；已知缓存 1 小时
        cache[key] = (sex_res, time.time())
        self._gender_cache = cache
        return sex_res

    @staticmethod
    def _client_is_private(ip: str) -> bool:
        import ipaddress
        try:
            a = ipaddress.ip_address(ip)
        except Exception:
            return False
        return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast

    async def is_public_url(self, url: str) -> bool:
        from urllib.parse import urlparse
        try:
            p = urlparse(str(url or ""))
        except Exception:
            return False
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        host = p.hostname.lower()
        if host in ("localhost", "metadata.google.internal") or host.endswith(".local"):
            return False
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None)
        except Exception:
            return False
        if not infos:
            return False
        for info in infos:
            ip = str(info[4][0])
            if self._client_is_private(ip):
                return False
        return True

    def balance_keywords(self) -> list[str]:
        raw = self.store.get_setting("balance_keywords", "") or ""
        words = [w.strip() for w in raw.replace("，", ",").split(",") if w.strip()]
        return words or ["查余额", "余额还剩多少", "额度还剩多少", "还有多少余额"]

    def S(self, key: str, default: str = "") -> str:
        return self.store.get_setting(key, default) or default

    def SI(self, key: str, default: int) -> int:
        try:
            return int(float(self.store.get_setting(key, str(default)) or default))
        except (TypeError, ValueError):
            return default

    def keyword_hit(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        for kw in self.store.keywords():
            kw = (kw or "").strip()
            if not kw:
                continue
            if len(kw) == 1 and not kw.isalnum():
                # 纯符号关键词（如 "."）只做整句匹配，避免误伤任何带句号的句子
                if text == kw:
                    return True
            elif kw in text:
                return True
        return False

    def effective_api_key(self) -> str:
        return (self.store.get_setting("deepseek_api_key", "") or self.api_key or "").strip()

    async def member_nick(self, ws, gid: str, uid: str) -> str:
        key = (str(gid), str(uid))
        cached = self._nick_cache.get(key)
        if cached and time.time() - cached[1] < 600:
            return cached[0]
        nick = str(uid)
        try:
            res = await self.onebot_call(ws, "get_group_member_info", {"group_id": int(gid), "user_id": int(uid)})
            if isinstance(res, dict):
                data = res.get("data") or {}
                nick = str(data.get("card") or data.get("nickname") or uid)
        except Exception:
            pass
        self._nick_cache[key] = (nick, time.time())
        return nick

    def recent_context(self, key: str) -> str:
        session = self.session(key)
        return "\n".join(f"{m['role']}: {m['content']}" for m in list(session.get("history") or [])[-8:])

    async def should_reply(self, session: dict, text: str) -> bool:
        provider = self.current_provider()
        if not provider.get("api_key"):
            return True
        recent = list(session.get("history") or [])[-6:]
        ctx = "\n".join(f"{m['role']}: {m['content'][:80]}" for m in recent)
        prompt = (
            "你是QQ群里的闲聊机器人。判断最后一条消息是否需要你回复，只需输出 是 或 否。\n"
            "需要回复：有人提问、点你、话题跟你有关、能自然接话。\n"
            "不需要回复：别人互相聊跟你无关、已经聊完、纯表情/无意义。\n"
            f"上下文:\n{ctx}\n最后一条: {text[:150]}"
        )
        payload = {"model": provider.get("model") or self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 3}
        try:
            async with self.http.post(
                f"{provider['base_url']}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None)
                self.record_usage(data.get("usage"), "judge")
                ans = ((data.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
                return not ans.startswith("否")
        except Exception:
            return True

    def allowed(self, mtype: str, group_id, user_id: str) -> bool:
        users = self.store.users()
        if users and user_id not in users:
            return False
        if mtype == "group":
            groups = self.store.groups()
            if groups and str(group_id) not in groups:
                return False
        return True

    def message_at_me(self, ev, self_id):
        for seg in ev.get("message") or []:
            if seg.get("type") == "at" and str((seg.get("data") or {}).get("qq")) == str(self_id):
                return True
        return False

    def _plain_text(self, ev):
        out = []
        for seg in ev.get("message") or []:
            if seg.get("type") == "text":
                out.append(str((seg.get("data") or {}).get("text") or ""))
        return "".join(out).strip()

    def active_hour(self, qq: str, days: int = 30):
        """按记忆创建时间统计该用户最活跃的小时，返回 (hour, count) 或 None。"""
        try:
            with self.store._conn() as c:
                rows = c.execute(
                    "SELECT strftime('%H', created_at) AS h, COUNT(*) AS n FROM memories "
                    "WHERE owner_qq=? AND created_at >= datetime('now','localtime',?) "
                    "GROUP BY h ORDER BY n DESC LIMIT 1",
                    (str(qq), f"-{int(days)} days")).fetchone()
            if rows and rows["h"] is not None:
                return int(rows["h"]), int(rows["n"])
        except Exception:
            pass
        return None

    async def handle_friend_request(self, ev: dict, ws):
        if ev.get("request_type") != "friend":
            return
        uid = self.norm_qq(ev.get("user_id", ""))
        flag = str(ev.get("flag") or "")
        comment = str(ev.get("comment") or "")
        if not uid or not flag:
            return
        auto = self.store.get_setting("friend_auto_accept", "0") == "1"
        notify = self.store.get_setting("friend_notify", "1") == "1"
        limit = int(self.store.get_setting("friend_daily_limit", "10") or 10)
        rejected = self.store.is_black(uid)
        action = "pending"
        if rejected:
            action = "rejected"
        elif auto:
            if self.store.friend_today("accepted") >= limit:
                action = "overlimit"
            else:
                res = await self.onebot_call(ws, "set_friend_add_request", {"flag": flag, "approve": True})
                action = "accepted" if (res or {}).get("status") == "ok" else "failed"
        self.store.friend_add(uid, comment, flag, action)
        log.info("好友申请: %s action=%s", uid, action)
        if notify:
            label = {"pending": "待处理", "accepted": "已自动通过", "rejected": "已拒绝（黑名单）",
                     "overlimit": "超过今日上限", "failed": "处理失败"}.get(action, action)
            await self.notify_super(ws, f"好友申请：{uid}\n附言：{comment or '无'}\n结果：{label}")

    @staticmethod
    def parse_segments(ev: dict, self_id: str) -> dict:
        """把 OneBot 消息段拆成文本/@信息/图片/语音/引用等，纯函数，便于测试。"""
        texts, image_urls, records, reply_ids = [], [], [], []
        at_me, at_others, at_target, stickers = False, False, "", 0
        for seg in ev.get("message") or []:
            st, sd = seg.get("type"), seg.get("data") or {}
            if st == "text":
                texts.append(str(sd.get("text", "")))
            elif st == "reply":
                rid = str(sd.get("id") or "")
                if rid:
                    reply_ids.append(rid)
            elif st == "at":
                q = str(sd.get("qq"))
                if q == self_id:
                    at_me = True
                elif q not in ("all", ""):
                    at_others = True
                    if not at_target:
                        at_target = q
            elif st == "record":
                u = sd.get("url") or sd.get("file") or ""
                if str(u).startswith("http"):
                    records.append(str(u))
            elif st in ("image", "mface"):
                u = sd.get("url") or sd.get("file") or ""
                if str(u).startswith("http"):
                    image_urls.append(str(u))
                else:
                    stickers += 1
        return {
            "user_text": "".join(texts).strip(),
            "at_me": at_me, "at_others": at_others, "at_target": at_target,
            "image_urls": image_urls, "stickers": stickers,
            "records": records, "reply_ids": reply_ids,
        }

    @staticmethod
    def parse_quoted(q: dict) -> tuple:
        """解析 get_msg 的返回，取出被引用消息的文本和图片。"""
        quoted_text, quoted_img = "", None
        if not (q and isinstance(q.get("data"), dict)):
            return quoted_text, quoted_img
        qmsg = q["data"].get("message")
        if isinstance(qmsg, str):
            quoted_text = qmsg
        elif isinstance(qmsg, list):
            parts = []
            for seg in qmsg:
                st, sd = seg.get("type"), seg.get("data") or {}
                if st == "text":
                    parts.append(str(sd.get("text", "")))
                elif st == "image":
                    u = sd.get("url") or sd.get("file") or ""
                    if str(u).startswith("http") and not quoted_img:
                        quoted_img = str(u)
            quoted_text = "".join(parts)
        return quoted_text, quoted_img

    def remember_recent(self, user_id: str, text: str):
        """记录最近消息，给怼人/接话做上下文。"""
        if not text:
            return
        rec = getattr(self, "_recent_msgs", {})
        dq = rec.get(str(user_id))
        if dq is None:
            dq = deque(maxlen=8)
            rec[str(user_id)] = dq
        dq.append(text[:200])
        self._recent_msgs = rec

    async def handle_balance_query(self, ws, ev, mtype, user_text, is_super) -> bool:
        """超管问余额时直接回当前供应商余额。"""
        if not (is_super and user_text):
            return False
        if not any(w in user_text for w in self.balance_keywords()):
            return False
        provider = self.current_provider() or {}
        if not provider.get("api_key"):
            await self.send(ws, mtype, ev, "还没配置模型 Key，查不了余额", record_convo=False)
            return True
        bal = await self.fetch_balance_text(provider)
        if bal:
            who = provider.get("name") or provider.get("model") or "当前模型"
            await self.send(ws, mtype, ev, f"当前模型（{who}）余额：{bal}", record_convo=False)
        else:
            await self.send(ws, mtype, ev, "余额查询失败：该供应商不支持查询，或 Key 无效", record_convo=False)
        return True

    async def handle_super_moderation(self, ws, ev, mtype, user_id, user_text,
                                      at_me, at_target, image_urls, is_super) -> bool:
        """超管的群管理动作：收录表情包、拉黑/解黑。返回 True 表示已处理。"""
        if mtype != "group" or not is_super:
            return False
        cap_kws = [w.strip() for w in
                   (self.store.get_setting("sticker_capture_keywords", "") or "添加表情包,收录,存表情")
                   .replace("，", ",").split(",") if w.strip()]
        cap_hit = self.match_capture_keyword(user_text, cap_kws) if user_text else None
        if at_me and image_urls and cap_hit and self.store.get_setting("sticker_capture_enabled", "1") == "1":
            context = (user_text.split(cap_hit, 1)[1] if cap_hit in user_text else "").strip(" ：:，,。.！!~\n\t")
            name, desc = await self.save_sticker_from_url(image_urls[0], "qq", context)
            if not name:
                await self.send(ws, mtype, ev, "表情包收录失败：图片下载不了或超过 5MB")
                return True
            msg = ("已收录表情包 ✅\n含义：" + desc) if desc else "已收录表情包 ✅（未识别到含义，可到后台编辑说明）"
            await self.send(ws, mtype, ev, msg)
            log.info("超管收录表情包: %s", name)
            return True
        if at_target and user_text:
            if any(w in user_text for w in ("加入黑名单", "拉黑")):
                nick = await self.member_nick(ws, str(ev.get("group_id")), at_target)
                self.store.add_black(at_target, nick)
                await self.send(ws, mtype, ev, f"已把 {nick} 加入黑名单", at_qq=at_target)
                log.info("黑名单新增: %s（操作人 %s）", at_target, user_id)
                return True
            if any(w in user_text for w in ("移出黑名单", "解除黑名单", "取消黑名单")):
                self.store.remove_black(at_target)
                await self.send(ws, mtype, ev, f"已把 {at_target} 移出黑名单")
                log.info("黑名单移除: %s（操作人 %s）", at_target, user_id)
                return True
        return False

    def likely_bot_sender(self, gid: str, uid: str, text: str) -> bool:
        """识别机器人式高频/复读账号：短时间大量消息或重复同一句，10 分钟内不再接话。"""
        key = f"{gid}:{uid}"
        now = time.time()
        if self._suspect.get(key, 0) > now:
            return True
        bucket = self._msg_rate.get(key)
        if bucket is None:
            bucket = []
            self._msg_rate[key] = bucket
        bucket.append((now, text))
        if len(bucket) > 40:
            del bucket[:-40]
        recent = [(t, x) for t, x in bucket if now - t < 8]
        same = sum(1 for t, x in bucket if x == text and now - t < 60 and len(text) >= 10)
        if len(recent) >= 4 or same >= 2:
            self._suspect[key] = now + 600
            log.warning("疑似机器人互刷账号 %s，10 分钟内忽略", key)
            return True
        return False

    def loop_guard_blocked(self, mtype: str, ev: dict, text: str) -> bool:
        """同一目标 30 秒内重复同一句话 3 次，判定为双机器人互刷，暂停该目标 5 分钟。"""
        gid = str(ev.get("group_id") or ev.get("user_id") or "")
        key = f"{mtype}:{gid}"
        now = time.time()
        if self._loop_guard.get(key, 0) > now:
            return True
        same = sum(1 for ts, t, k in list(self._sent_guard) if k == key and t == text and now - ts < 60 and len(str(text)) >= 10)
        self._sent_guard.append((now, text, key))
        if same >= 1:
            self._loop_guard[key] = now + 300
            log.warning("防循环触发：%s 重复发送同一内容，暂停 5 分钟", key)
            return True
        return False

    def record_recent_topic(self, uid: str, text: str):
        try:
            text = " ".join(str(text or "").split())[:120]
            if len(text) < 2:
                return
            with self.store._conn() as c:
                c.execute("INSERT INTO chat_recent(user_qq,text,created_at) VALUES(?,?,?)", (str(uid), text, time.time()))
                if not self.is_super_admin(str(uid)):
                    c.execute("DELETE FROM chat_recent WHERE user_qq=? AND created_at<?", (str(uid), time.time() - 7 * 86400))
        except Exception:
            pass

    def recent_topic_context(self, uid: str) -> str:
        try:
            if not uid:
                return ""
            if self.is_super_admin(str(uid)):
                since = 0  # 超级管理员永久保留
            else:
                since = time.time() - 7 * 86400
            with self.store._conn() as c:
                rows = c.execute("SELECT text FROM chat_recent WHERE user_qq=? AND created_at>? ORDER BY id DESC LIMIT 3",
                                 (str(uid), since)).fetchall()
            if not rows:
                return ""
            return "\n你们最近聊过：" + "；".join(str(r["text"])[:60] for r in reversed(rows)) + "（可以自然接着聊，不要硬提）"
        except Exception:
            return ""

    def remember_outgoing(self, text: str):
        """记录刚发出去的内容，用于识别“机器人收到自己消息”的回环。"""
        try:
            from collections import deque
            buf = getattr(self, "_recent_out", None)
            if buf is None:
                buf = deque(maxlen=40)
                self._recent_out = buf
            buf.append((time.time(), re.sub(r"\s+", "", str(text))[:100]))
        except Exception:
            pass

    def looks_like_self_echo(self, text: str) -> bool:
        """判断这段收到的文字是不是刚发出去的内容（语音被转写回来也适用）。"""
        try:
            import difflib
            buf = getattr(self, "_recent_out", None) or []
            cur = re.sub(r"\s+", "", str(text))
            if len(cur) < 6:
                return False
            now = time.time()
            for ts, prev in list(buf)[-20:]:
                if now - ts > 180 or len(prev) < 6:
                    continue
                if difflib.SequenceMatcher(None, cur, prev).ratio() >= 0.8:
                    return True
        except Exception:
            pass
        return False

    async def llm_messages(self, messages: list[dict], max_tokens: int = 900,
                           temperature: float = 0.8, timeout: int = 120) -> str:
        """按原始 messages 调一次模型（游戏模式需要带多轮历史）。"""
        provider = self.current_provider() or {}
        key = provider.get("api_key") or ""
        if not key:
            return ""
        base = (provider.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
        model = provider.get("model") or "deepseek-chat"
        mt = max_tokens
        for _ in range(2):
            try:
                async with self.http.post(
                    base + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages,
                          "temperature": temperature, "max_tokens": mt},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status != 200:
                        log.warning("游戏模式 LLM HTTP %s", resp.status)
                        return ""
                    data = await resp.json(content_type=None)
                    self.record_usage(data.get("usage"), "game")
                    msg = ((data.get("choices") or [{}])[0].get("message") or {})
                    content = (msg.get("content") or "").strip()
                    if content:
                        return content
                    if msg.get("reasoning_content") and mt < 3000:
                        mt = min(4000, max(1500, mt * 4))
                        continue
                    return ""
            except Exception as e:
                log.warning("游戏模式 LLM 失败: %s", e)
                return ""
        return ""

    @staticmethod
    def watermark_prompt(text: str, tag: str) -> str:
        """在提示词里夹零宽水印，泄露时可反查出是哪台部署（视觉上不可见）。"""
        try:
            import hashlib
            h = hashlib.sha256(str(tag).encode()).hexdigest()[:16]
            bits = "".join(format(int(ch, 16), "04b") for ch in h)
            zw = "".join("\u200b" if b == "0" else "\u200c" for b in bits)
            if not text:
                return text
            mid = len(text) // 2
            return text[:mid] + zw + text[mid:]
        except Exception:
            return text

    async def handle_game(self, ws, mtype: str, ev: dict, user_id: str, user_text: str) -> bool:
        """剧本杀：私聊直接玩；群聊需先 @机器人 发「继续游戏」接入。返回 True 表示已处理。"""
        t = str(user_text or "").strip()
        if not t:
            return False
        in_group = mtype == "group"
        gid = str(ev.get("group_id") or "") if in_group else ""
        if in_group:
            allowed = gid in [str(x) for x in self.store.groups()]
            cmdish = (t in self.GAME_START_WORDS or t in self.GAME_EXIT_WORDS or t in self.GAME_GROUP_CMDS
                      or t.startswith("玩第") or t.startswith("判定") or t.startswith("投骰"))
            if not allowed:
                if cmdish:
                    await self.send(ws, mtype, ev, "本群还没开启剧本杀。让超级管理员把本群加入白名单后即可。", record_convo=False)
                return False
            gctx = self.store.ctx_get(user_id, gid)
            if t in self.GAME_EXIT_WORDS:
                if gctx:
                    self.store.ctx_deactivate(user_id, gid)
                    await self.send(ws, mtype, ev, "已退出群内剧本，进度保留。私聊或再发「继续游戏」都能接着玩。", record_convo=False)
                else:
                    await self.send(ws, mtype, ev, "当前没有接入群内剧本。", record_convo=False)
                return True
            if gctx and gctx.get("active"):
                if t in self.GAME_START_WORDS:
                    await self.send(ws, mtype, ev, "已经在群内剧本里了，直接 @我 说话即可推进；发「结束游戏」退出。", record_convo=False)
                    return True
            else:
                if t in self.GAME_START_WORDS:
                    pl0 = self.store.player_get(user_id)
                    sid0 = (pl0 or {}).get("script_id")
                    if not pl0 or not sid0:
                        await self.send(ws, mtype, ev, "你还没有分配剧本，请联系超级管理员添加后再玩。", record_convo=False)
                        return True
                    script0 = await self.game_script_resolve(sid0)
                    if not script0:
                        await self.send(ws, mtype, ev, "剧本加载失败，请稍后再试。", record_convo=False)
                        return True
                    run0 = self.store.run_active(user_id, int(sid0)) or {}
                    if not run0:
                        await self.send(ws, mtype, ev,
                                        "你还没有开始这一局。先私聊机器人发「开始」建档，再回群里发「继续游戏」。",
                                        record_convo=False)
                        return True
                    self.store.ctx_set(user_id, gid, int(sid0))
                    self.store.player_set(user_id, active=1)
                    await self.send(ws, mtype, ev,
                                    f"已接入《{script0.get('name') or '剧本'}》：第 {run0.get('run_no')} 次、"
                                    f"{run0.get('turn_count')} 回合。\n@我 说话即可推进；发「结束游戏」退出群内剧情。",
                                    record_convo=False)
                    return True
                if t in self.GAME_GROUP_CMDS or t.startswith("玩第") or t.startswith("判定") or t.startswith("投骰"):
                    await self.send(ws, mtype, ev, "你还没接入群内剧本。先 @我 发「继续游戏」接入。", record_convo=False)
                    return True
                return False   # 未接入群内剧本 → 当普通聊天处理
        pl = self.store.player_get(user_id)
        if not pl:
            return False
        sid = pl.get("script_id")
        if not sid:
            admins = self.super_admin_qqs() or []
            who = admins[0] if admins else "超级管理员"
            await self.send(ws, mtype, ev, f"你已被加入剧本杀，但还没有分配剧本。\n请联系超级管理员 QQ {who} 添加剧本后再玩。", record_convo=False)
            return True
        script = await self.game_script_resolve(sid)
        if not script:
            await self.send(ws, mtype, ev, "剧本暂时加载失败（可能是网络或接口 token 问题），请稍后再试或联系超级管理员。", record_convo=False)
            return True
        active = bool(pl.get("active"))
        # 退出
        if t in self.GAME_EXIT_WORDS:
            if active:
                self.store.player_set(user_id, active=0)
                await self.send(ws, mtype, ev, "已退出剧本。进度保留，发「继续游戏」随时回来。", record_convo=False)
                return True
            return False
        # 存档信息
        if t in ("存档", "我的存档", "进度"):
            runs = self.store.run_list(user_id)[:5]
            cur = self.store.run_active(user_id, int(sid))
            lines = [f"《{script.get('name') or '剧本'}》当前第 {(cur or {}).get('run_no', '?')} 次，已 {(cur or {}).get('turn_count', 0)} 回合。"]
            if runs:
                lines.append("历史局：" + "、".join(f"第{r['run_no']}次({r['status']})" for r in runs))
            lines.append("发「玩第N次」可切换到某一局继续。")
            await self.send(ws, mtype, ev, "\n".join(lines), record_convo=False)
            return True
        # 主动判定：判定 武力
        import re as _re
        m_dice = _re.match(r"^(?:判定|投骰|骰子?)\s*[:：]?\s*(\S{1,6})$", t)
        if m_dice:
            if not active:
                await self.send(ws, mtype, ev, "还没开始。发送「开始」进入剧情后再判定。", record_convo=False)
                return True
            attr = m_dice.group(1)
            run = self.store.run_active(user_id, int(sid)) or await self.game_pick_run(user_id, int(sid))
            base = 2
            try:
                st = json.loads(run.get("state_json") or "{}")
                base = int((st.get("attrs") or {}).get(attr) or 2)
            except Exception:
                pass
            roll = secrets.randbelow(100) + 1
            total = roll + base * 5
            res = "成功" if total >= 70 else ("险成（必有代价）" if total >= 30 else "失败（剧情仍推进）")
            await self.send(ws, mtype, ev, f"【判定·{attr}】d100={roll} + 属性{base}×5 = {total}\n结果：{res}", record_convo=False)
            out = await self.game_turn(user_id, script, run,
                                       f"（系统判定）玩家主动发起「{attr}」判定：d100={roll}，属性值={base}，"
                                       f"合计={total}，结果={res}。请据此描写结果与代价，不要透露骰值。")
            await self.game_send(ws, mtype, ev, out)
            return True

        # 查看状态面板
        if t in ("状态", "我的状态", "面板", "看看状态"):
            if not active:
                await self.send(ws, mtype, ev, "还没开始。发送「开始」进入剧情。", record_convo=False)
                return True
            run = self.store.run_active(user_id, int(sid)) or await self.game_pick_run(user_id, int(sid))
            out = await self.game_turn(
                user_id, script, run,
                "（系统指令）不要推进剧情，只根据当前进度输出【状态面板】：生命/精神/内力/属性/境界/资源/物品/线索/好感/声望/时间，末尾一句话说明当前处境。")
            await self.game_send(ws, mtype, ev, out)
            return True

        # 重开本局
        if t in ("重开本局", "重新开始", "重开"):
            rid = self.store.run_create(user_id, int(sid))
            self.store.run_set_status(user_id, int(sid), rid)
            self.store.player_set(user_id, active=1)
            run = self.store.run_get(rid)
            out = await self.game_turn(user_id, script, run, "开始新的一局：输出建档卡与开场，不要引用之前的进度。")
            await self.game_send(ws, mtype, ev, out)
            return True

        # 选局：玩第N次
        import re as _re
        m = _re.match(r"^玩第\s*(\d+)\s*次$", t)
        if m:
            want = int(m.group(1))
            runs = [r for r in self.store.run_list(user_id) if r.get("run_no") == want]
            if not runs:
                await self.send(ws, mtype, ev, f"没有第 {want} 次的记录。发「我的存档」看看有哪些。", record_convo=False)
                return True
            run = runs[0]
            self.store.run_set_status(user_id, int(sid), run["id"])
            self.store.player_set(user_id, active=1)
            await self.send(ws, mtype, ev, f"已切到第 {want} 次（{run['turn_count']} 回合）。\n发送任意内容继续。", record_convo=False)
            return True
        # 未开启：只有开局/继续类指令生效
        if not active:
            if t in self.GAME_START_WORDS or t.startswith("开始"):
                self.store.player_set(user_id, active=1)
                run = await self.game_pick_run(user_id, int(sid))
                out = await self.game_turn(user_id, script, run,
                                           "开始（如果是新的一局就输出建档卡；如果已有进度就回顾当前处境后继续）")
                await self.game_send(ws, mtype, ev, out)
                return True
            return False
        # 正常回合
        run = await self.game_pick_run(user_id, int(sid))
        out = await self.game_turn(user_id, script, run, t)
        await self.game_send(ws, mtype, ev, out)
        return True

    async def handle_message(self, ev: dict, ws):
        mtype = ev.get("message_type")
        if mtype not in ("group", "private"):
            return
        self_id = str(ev.get("self_id") or self.self_id)
        self.self_id = self_id
        user_id = self.norm_qq(ev.get("user_id", ""))
        if user_id == self_id:
            return
        sender = ev.get("sender") or {}
        if sender.get("bot"):
            return
        if self.store.is_black(user_id):
            return
        try:
            if mtype == "group":
                _gid = str(ev.get("group_id") or "")
                if self._loop_guard.get("group:" + _gid, 0) > time.time():
                    log.warning("群 %s 处于防循环保护，跳过处理", _gid)
                    return
                if self.likely_bot_sender(_gid, str(user_id), str(ev.get("raw_message") or "")):
                    return
        except Exception:
            pass
        is_super = self.is_super_admin(user_id)
        try:
            if mtype == "private" and is_super and self.store.get_setting("world_enabled", "1") == "1":
                self.world_wake("你私聊了他")
        except Exception:
            pass
        # 剧本杀玩家在休息时段也要能玩：私聊已分配剧本 / 群聊已接入本群
        game_pass = False
        try:
            _pl = self.store.player_get(user_id) if self.store.get_setting("game_rest_bypass", "1") != "0" else {}
            _pl = _pl or {}
            if _pl.get("script_id"):
                if mtype == "private":
                    game_pass = True
                else:
                    _ctx = self.store.ctx_get(user_id, str(ev.get("group_id") or ""))
                    game_pass = bool(_ctx.get("active"))
        except Exception:
            game_pass = False
        if self.rest_window() and not game_pass:
            wake_on = self.store.get_setting("wake_enabled", "0") == "1"
            if is_super:
                if mtype != "private":
                    gid_s = str(ev.get("group_id") or "")
                    if not (mtype == "group" and gid_s in [str(x) for x in self.store.rest_groups()]):
                        return
                    if wake_on:
                        await self.handle_wake(ws, ev, user_id, gid_s)
                        return
            elif not self.rest_allows(mtype, ev.get("group_id"), user_id):
                return
            elif wake_on and mtype == "group":
                return
        if mtype == "group" and self.store.get_setting("exclusive_mode", "0") == "1":
            try:
                win = max(10, int(self.store.get_setting("exclusive_window_seconds", "60")))
            except ValueError:
                win = 60
            if is_super:
                self.last_super_at = time.time()
            elif time.time() - self.last_super_at <= win:
                return

        seg = self.parse_segments(ev, self_id)
        user_text = seg["user_text"]
        at_me, at_others, at_target = seg["at_me"], seg["at_others"], seg["at_target"]
        image_urls, stickers = seg["image_urls"], seg["stickers"]
        records, reply_ids = seg["records"], seg["reply_ids"]
        self.remember_recent(user_id, user_text)
        try:
            if (mtype == "group" and self.gm_get("gm_blacklist_kick", str(ev.get("group_id") or ""), "0") == "1"
                    and str(ev.get("group_id") or "") in self.gm_groups()
                    and self.gm_black(str(ev.get("group_id") or ""), str(user_id))
                    and any(k in (user_text or "") for k in self.gm_kw_g("gm_blacklist_keywords", str(ev.get("group_id") or ""), ""))):
                if await self.gm_bot_is_admin(str(ev.get("group_id") or "")):
                    await self.onebot_action("set_group_kick", {"group_id": str(ev.get("group_id")),
                                                                "user_id": str(user_id),
                                                                "reject_add_request": False})
                    log.info("黑名单自动踢出: %s @ %s", user_id, ev.get("group_id"))
                    await self.gm_notify_punish(str(ev.get("group_id")), str(user_id), "黑名单用户触发关键词，自动踢出")
                    return
            if mtype == "group" and str(ev.get("group_id") or "") in self.gm_groups():
                hit = await self.gm_kwlimit_check(ws, ev, str(user_text or ""))
                if hit:
                    return
            if (mtype == "group" and self.gm_get("gm_recall_enabled", str(ev.get("group_id") or ""), "0") == "1"
                    and str(ev.get("group_id") or "") in self.gm_groups()):
                kws = self.gm_kw_g("gm_recall_keywords", str(ev.get("group_id") or ""), "")
                if kws and any(k in (user_text or "") for k in kws):
                    mid = ev.get("message_id")
                    if mid:
                        await self.onebot_action("delete_msg", {"message_id": mid})
                        log.info("违规关键词撤回: %s 在 %s：%s", user_id, ev.get("group_id"), user_text[:40])
                        return
            await self.gm_patrol(ws, ev, mtype, user_text, is_super)
            if await self.handle_bili(ws, ev, mtype, user_text, is_super):
                return
            if await self.handle_mute_command(ws, ev, mtype, user_text, is_super, at_target):
                return
            if await self.handle_kick_command(ws, ev, mtype, user_text, is_super, at_target):
                return
            # 管理群禁止闲聊：只响应超管/授权管理员，普通成员消息直接忽略
            if (mtype == "group" and self.gm_get("gm_silent", str(ev.get("group_id") or ""), "0") == "1"
                    and str(ev.get("group_id") or "") in self.gm_groups()
                    and not self.gm_kick_allowed(str(user_id))):
                return
            if await self.handle_verify_reply(ws, ev, mtype, user_text):
                return
        except Exception as _e:
            log.warning("群管理前置处理失败: %s", _e)
        try:
            _mid = str(ev.get("message_id") or "")
            if _mid:
                _cache = getattr(self, "_recall_msgs", None)
                if _cache is None:
                    _cache = {}; self._recall_msgs = _cache
                _parts = [user_text] if user_text else []
                if image_urls or stickers: _parts.append("[图片]")
                if records: _parts.append("[语音]")
                _cache[_mid] = {
                    "text": " ".join(_parts) if _parts else "（空消息）",
                    "images": list(image_urls or [])[:4],
                    "user": str(user_id), "nick": str(sender.get("nickname") or ""),
                    "group": str(ev.get("group_id") or ""),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                if len(_cache) > 500:
                    _cache.pop(next(iter(_cache)), None)
        except Exception:
            pass
        had_voice = False
        if records:
            had_voice = True
            if self.asr_on():
                tr = await self.transcribe(records[0])
                if tr:
                    user_text = (user_text + " " + tr).strip() if user_text else tr
                elif not user_text:
                    user_text = "（对方发了一条语音，我没听清）"
        if reply_ids:
            q = None
            if reply_ids[0].isdigit():
                q = await self.onebot_call(ws, "get_msg", {"message_id": int(reply_ids[0])})
            quoted_text, quoted_img = self.parse_quoted(q)
            if quoted_img:
                image_urls.append(quoted_img)
            if quoted_text.strip():
                user_text = f"[引用: {quoted_text.strip()[:60]}] {user_text}".strip()
            elif quoted_img:
                user_text = f"[引用了一张图片] {user_text}".strip()
        try:
            if user_text:
                self.record_recent_topic(user_id, user_text)
                if hasattr(self, "detect_promise"):
                    self.spawn(self.detect_promise(user_id, user_text), "promise")
        except Exception:
            pass
        if await self.handle_balance_query(ws, ev, mtype, user_text, is_super):
            return
        if await self.handle_super_moderation(ws, ev, mtype, user_id, user_text,
                                               at_me, at_target, image_urls, is_super):
            return
        log.info("收到[%s] %s: %r (语音=%s, 图片=%d)", mtype, user_id,
                 str(user_text)[:80], had_voice, len(image_urls))
        if self.looks_like_self_echo(user_text):
            log.info("忽略疑似自回环消息: %r", str(user_text)[:50])
            return
        try:
            if (mtype == "private" and is_super and hasattr(self, "world_selfie")
                    and any(k in str(user_text) for k in ("自拍", "拍张", "拍给我", "看看你"))):
                self.spawn(self.world_selfie(user_id), "selfie")
                return
        except Exception:
            pass
        # 私聊末世文字冒险优先处理（群聊版后续再加）
        if (mtype == "private" or (mtype == "group" and at_me)) and await self.handle_game(ws, mtype, ev, user_id, user_text):
            return
        sing_song = self.sing_request(user_text)
        if sing_song is not None:
            if await self.handle_sing(ws, mtype, ev, user_id, sing_song):
                return
        if await self.handle_roast(ws, ev, mtype, user_id, user_text, at_target, is_super):
            return
        music_kw = ""
        if self.store.get_setting("music_enabled", "1") == "1" and (at_me or mtype == "private") and user_text:
            music_kw = self.music_command_keyword(user_text)
        if music_kw:
            await self.handle_music(ws, ev, music_kw, mtype)
            return
        if (at_me or mtype == "private") and user_text:
            if self.image_help_requested(user_text):
                if self.store.get_setting("image_enabled", "0") != "1":
                    await self.send(ws, mtype, ev, "生图功能还没开，让老大去后台打开。", record_convo=False)
                else:
                    await self.send(ws, mtype, ev, self.image_help_text(is_super), record_convo=False)
                return
        if (at_me or mtype == "private") and user_text:
            img_prompt = self.image_command_prompt(user_text)
            if img_prompt:
                await self.handle_image(ws, ev, mtype, user_id, img_prompt, is_super)
                return
        if (at_me or mtype == "private") and self.store.get_setting("reminder_enabled", "1") == "1":
            if await self.messenger.handle(ws, ev, mtype, user_id, user_text):
                return
        # 群里 @ 的是别人、没有 @ 机器人：视为不是在叫它，不接话
        if mtype == "group" and at_others and not at_me:
            return
        # 群里聊机器人配置/技术细节时，不主动插嘴（除非明确 @ 它）
        meta_words = ("触发词", "关键词", "提示词", "后台", "API", "token", "部署", "配置", "模型设置", "机器人设置")
        if mtype == "group" and not at_me and any(w in (user_text or "") for w in meta_words):
            return
        if at_others and not at_me and not is_super and not self.keyword_hit(user_text):
            return
        if not user_text and not image_urls and not stickers and not at_me:
            return
        if stickers and not image_urls:
            user_text = (user_text + " （对方发了个表情包）").strip()

        if not is_super and not self.allowed(mtype, ev.get("group_id"), user_id):
            return

        triggered = False
        always = False
        conv_active = False
        thrifty = False
        if mtype == "group":
            gid = str(ev.get("group_id"))
            now = time.time()
            if user_text and self.store.get_setting("end_phrase_enabled", "1") == "1":
                phrases = self.store.end_phrases()
                hit = next((p for p in phrases if p in user_text), None) if phrases else None
                if hit:
                    if (gid, user_id) in self.active_convos:
                        self.active_convos.pop((gid, user_id), None)
                        log.info("结束语[%s]触发，已移除该用户的接话: 群%s QQ%s", hit, gid, user_id)
                        final_text = (self.store.get_setting("end_phrase_reply", "好的，那我退下了") or "").strip()
                        if final_text:
                            await self.send(ws, mtype, ev, final_text, record_convo=False)
                    return
            kw_hit = self.keyword_hit(user_text)
            auto_hit = (
                user_id in self.store.auto_users()
                and self.store.get_setting("auto_reply_enabled", "1") == "1"
            )
            triggered = at_me or kw_hit or auto_hit or is_super
            thrifty = self.store.get_setting("thrifty_mode", "0") == "1"
            always = (not thrifty) and (gid in self.store.always_groups())
            conv_active = (not thrifty) and (now < self.active_convos.get((gid, user_id), 0))
            if self.group_at_only and not triggered and not always and not conv_active:
                return
            try:
                if (not triggered and not is_super and hasattr(self, "world_low_mood")
                        and self.world_low_mood()):
                    log.info("心情不好，减少接话: 群%s", gid)
                    return
            except Exception:
                pass
            if not triggered and (always or conv_active):
                # 一直接话/个人会话续聊：限每分钟回复数，避免刷屏
                cap = self.SI("always_max_per_minute", 10) if always else self.SI("group_max_replies", self.group_max_replies)
                times = self.group_reply_times.setdefault(gid, deque())
                while times and now - times[0] > 60:
                    times.popleft()
                if len(times) >= cap:
                    return
            if not user_text and not image_urls:
                # 只@了但没说话：回一句提示（限流）
                if at_me and now - self.last_reply.get(f"g{gid}", 0) >= self.min_interval:
                    self.last_reply[f"g{gid}"] = now
                    hint_at = user_id if self.store.get_setting("reply_at_enabled", "0") == "1" else None
                    await self.send(ws, mtype, ev, "在的，直接说事情就好～", at_qq=hint_at)
                return
            key = f"g{gid}"
        else:
            if not user_text and not image_urls:
                return
            key = f"p{user_id}"

        self.spawn(self.affect_process(user_id, user_text, key), "affect")
        self.spawn(self.panic_on_reply(user_id, user_text), "panic_reply")
        self.boredom_touch(user_id, is_super)

        now = time.time()
        if mtype == "group":
            skip_rate = is_super or ((not thrifty) and (str(ev.get("group_id")) in self.store.always_groups()) and not triggered)
            if not skip_rate and not self.group_rate_ok(str(ev.get("group_id"))):
                log.info("限频丢弃: 群%s QQ%s（该群回复频率设置拦截）", ev.get("group_id"), user_id)
                try:
                    sess = self.session(key)
                    self.schedule_memory_extract(user_id, self.memory_level(user_id), user_text, "",
                                                 mtype, list(sess.get("history") or [])[-8:])
                except Exception:
                    pass
                return
        else:
            if now - self.last_reply.get(key, 0) < self.min_interval:
                return
            self.last_reply[key] = now

        if is_super:
            log.info("超管[%s] 消息进入处理", user_id)
        self.msg_count += 1
        self.last_message = {
            "time": time.strftime("%H:%M:%S"),
            "session": key,
            "user": sender.get("nickname", user_id),
            "text": user_text[:100],
        }
        if user_text and re.search(r"(发|来|整|给|换|要).{0,5}表情", user_text):
            rows = self.store.sticker_descriptions()
            if rows:
                name = None
                if self.store.get_setting("sticker_mode", "smart") == "smart":
                    name = await self.smart_pick_sticker(rows, user_text, "（对方只是要一张表情包）")
                if not name:
                    name = random.choice([r["filename"] for r in rows])
                ok = await self.send_sticker(ws, mtype, ev, name)
                if ok:
                    self.reply_count += 1
                    return
        session = self.session(key)
        if session["lock"].locked():
            return
        if mtype == "group" and conv_active and not triggered and not always and not is_super:
            if not await self.should_reply(session, user_text):
                log.info("AI 判断无需回复，已跳过")
                return
        async with session["lock"]:
            nickname = str(sender.get("nickname") or user_id)
            label = f"[{nickname}({user_id})]"
            llm_text = f"{label} {user_text}" if user_text else f"{label} （发了张图片）"
            log.info("回复[%s] %s: %s", key, nickname, user_text[:80])
            images = await self.prepare_images(image_urls) if image_urls else []
            gender = await self.detect_gender(ws, mtype, ev.get("group_id"), user_id, sender)
            slang_text = ""
            if self.store.get_setting("slang_enabled", "0") == "1" and user_text:
                try:
                    every = max(1, int(self.store.get_setting("slang_every", "3") or 3))
                    cnt = getattr(self, "_slang_counter", 0) + 1
                    self._slang_counter = cnt
                    learned = await self.slang_learn(user_text) if cnt % every == 0 else []
                    slang_text = self.slang_note(user_text, learned)
                except Exception:
                    slang_text = ""
            mem_level = self.memory_level(user_id)
            if is_super and self.memory_scope_ok(mtype, user_id):
                try:
                    await self.extract_memories(user_id, "high", user_text, "", list(session.get("history") or [])[-8:])
                except Exception:
                    pass
            mem_text = self.memory_prompt(user_id, mem_level, user_text) if self.memory_scope_ok(mtype, user_id) else ""
            pass
            reply = await self.ask_deepseek(session, llm_text, images, is_super=is_super, gender=gender, memory_text=mem_text, slang_text=slang_text, uid=user_id, gid=str(ev.get("group_id") or ""))
            self.commit_memory_usage(user_id, user_text, reply)
            try:
                self.world_chat_mood(user_text, str(user_id), str(ev.get("group_id") or ""))
            except Exception:
                pass
            try:
                asyncio.get_running_loop().create_task(self.detect_task(str(user_id), user_text, str(ev.get("message_id") or "")))
                asyncio.get_running_loop().create_task(self.detect_cancel(str(user_id), user_text))
            except Exception:
                pass
            if self.memory_scope_ok(mtype, user_id) and not is_super:
                self.schedule_memory_extract(user_id, mem_level, user_text, reply, mtype, list(session.get("history") or [])[-8:])
            if image_urls and any(k in reply for k in ("存了", "收了", "存起来", "收藏了", "存进", "加入表情")):
                try:
                    _saved = await self.auto_save_sticker_images(image_urls, reply)
                except Exception:
                    _saved = None
                if not _saved:
                    for _k in ("存了存了", "存了", "收了", "存起来", "收藏了", "存进表情包"):
                        reply = reply.replace(_k, "")
                    reply = reply.strip() + "（这张没存上，图裂了）"
            prefix = (
                self.store.get_prefix(user_id)
                if self.store.get_setting("prefix_enabled", "1") == "1"
                else None
            )
            if prefix:
                sep = "" if prefix[-1] in "，。！？、,.!?~…" else "，"
                reply = f"{prefix}{sep}{reply}"
            want_voice = self.voice_wanted(had_voice, user_id, user_text)
            if want_voice and await self.tts_speak(ws, mtype, ev, reply,
                                                    context=self.voice_context(mem_text, slang_text)):
                self.reply_count += 1
            else:
                parts = self.split_reply(reply)
                delay_ms = max(0, min(10000, self.SI("multi_msg_delay_ms", 600)))
                first_ms = max(0, min(10000, self.SI("msg_first_delay_ms", 300)))
                try:
                    e = self.world_emotion()
                    if e.get("anger", 0) >= 60 or e.get("sad", 0) >= 60:
                        first_ms += 1200
                    elif e.get("stress", 0) >= 70:
                        first_ms += 600
                    elif e.get("joy", 0) >= 70:
                        first_ms = max(0, first_ms - 200)
                except Exception:
                    pass
                try:
                    # 按回复长度模拟打字：越长越慢，最多再加 1.5 秒
                    first_ms += min(1500, int(len(reply) * 22))
                except Exception:
                    pass
                if first_ms:
                    await asyncio.sleep(first_ms / 1000.0)
                at_qq = None
                if mtype == "group" and at_me and self.store.get_setting("reply_at_enabled", "0") == "1":
                    at_qq = user_id
                for idx, part in enumerate(parts):
                    if idx:
                        seg_ms = max(delay_ms, min(1400, int(len(part) * 35)))
                        await asyncio.sleep(seg_ms / 1000.0)
                    await self.send(ws, mtype, ev, part, at_qq=(at_qq if idx == 0 else None))
                self.reply_count += max(1, len(parts))
            await self.maybe_send_sticker(ws, mtype, ev, llm_text, reply, has_image=bool(image_urls))

    def open_conversation(self, gid: str, uid: str):
        try:
            cap = int(self.store.get_setting("max_active_users", str(self.max_active_users)))
        except ValueError:
            cap = self.max_active_users
        cap = max(1, cap)
        try:
            window = int(self.store.get_setting("group_continue_seconds", str(self.continue_seconds)))
        except ValueError:
            window = self.continue_seconds
        now = time.time()
        active = {k: v for k, v in self.active_convos.items() if k[0] == gid and v > now}
        if (gid, uid) not in active and len(active) >= cap:
            oldest = min(active, key=active.get)
            self.active_convos.pop(oldest, None)
        self.active_convos[(gid, uid)] = now + window

    def get_group_rate(self, gid: str):
        row = self.store.get_rate(gid)
        if row:
            return row
        return (self.SI("group_max_replies", self.group_max_replies), self.min_interval)

    def group_rate_ok(self, gid: str) -> bool:
        cap, interval = self.get_group_rate(gid)
        cap = max(1, cap); interval = max(0, interval)
        now = time.time()
        if now - self.group_last_reply.get(gid, 0) < interval:
            return False
        times = self.group_reply_times.setdefault(gid, deque())
        while times and now - times[0] > 60:
            times.popleft()
        return len(times) < cap


add(id="chat.dispatch", name="消息调度", entry="fishpond.features.chat.dispatch:handle_message",
    routes=[], tables=[], settings=["reply_*", "rest_*"], ui="（核心）",
    files="fishpond/features/chat/dispatch.py", status="active")
