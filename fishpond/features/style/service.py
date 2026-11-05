"""风格模块：黑话、无聊模式、怼人、唤醒。"""
import asyncio
import json
import random
import re
import time
from collections import deque

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")

BORED_LINES = ['安静得有点过分了，你们说全世界最安静的地方是哪儿？', '突然想问问，你们午饭都吃啥了？我还在纠结', '话说鱼会口渴吗？在线等，不着急', '有没有人跟我一样，明明很困但就是不想睡', '我怀疑这个群被施了静音咒，有人能解开吗', '如果发呆能赚钱，我现在应该已经财富自由了', '刚看到一只猫在晒太阳，你们说它脑子里在想什么', '突然好奇：你们手机里最舍不得删的一张照片是什么', '好无聊啊，有没有人来讲个冷笑话，我先讲：企鹅为什么不怕冷', '问一下，你们觉得世界上先有鸡还是先有蛋（认真脸）', '这个点大家都在忙什么？摸鱼的扣个 1', '天塌下来也先聊两句再跑啊，你们说是不是', '刚才发呆十分钟，感觉自己像个加载中的网页', '有人在线吗，出来吱一声，让我知道我没对着空气说话', '突然想到，如果今天不用上班，你们最想去哪儿']


class StyleMixin:
    def roast_words(self) -> list[str]:
        raw = self.store.get_setting("roast_keywords", "") or ""
        words = [w.strip() for w in raw.replace("，", ",").split(",") if w.strip()]
        return words or ["怼他", "怼一下", "怼"]

    async def roast_user(self, nick: str, context: str) -> str:
        provider = self.current_provider()
        if not provider.get("api_key"):
            return ""
        try:
            level = int(self.store.get_setting("roast_level", "1") or 1)
        except Exception:
            level = 1
        level = max(0, min(2, level))
        if level == 0:
            style = ("你是群里超可爱、超俏皮的小可爱，说话软软的、爱撒娇、偶尔冒颜文字，但一点也不讨人厌。现在要轻轻吐槽「{}」。\n"
                     "要求：结合最近聊天，用一两句话俏皮地调侃他，像好朋友打闹；"
                     "多用「呀、叭、嘛、啦、哦」这种语气词，可以加简单颜文字（如 (｡•̀ᴗ-)✧、qwq、OvO），"
                     "可以夸张卖萌，但要软软的、不阴阳怪气、不伤人，让人看了会心一笑。\n"
                     "不要重复对方昵称，不要以昵称开头，发送时前面会自动 @ 他。\n"
                     "最近聊天：\n{}")
            temp = 1.0
        elif level == 1:
            style = ("你是群里的毒舌担当，反应快、会接梗。现在群友让你怼「{}」。\n"
                     "要求：结合最近聊天，抓住他的话或逻辑漏洞，用一两句话机智地损他，可以反问、可以夸张比喻；"
                     "要有梗，让人想笑，别太过分。\n"
                     "底线：不带脏字、不用亲属称呼骂人、不攻击身体/性别/地域/疾病、不造谣。"
                     "不要重复对方昵称，不要以昵称开头，发送时前面会自动 @ 他。\n"
                     "最近聊天：\n{}")
            temp = 0.9
        else:
            style = ("你是全网最损的毒舌，嘴毒到没朋友，擅长阴阳怪气、连环反问、精准补刀。现在群友让你怼「{}」。\n"
                     "要求：结合最近聊天，抓住他刚才说的话、做的事或逻辑漏洞，往死里嘲讽；"
                     "可以连环反问、可以阴阳怪气、可以夸张比喻、可以直接骂他蠢/废/没救/丢人/活该，"
                     "可以嘲讽他的智商、能力、品味、操作、见识；要短促、有梗、刀刀见血，"
                     "目标是让他当场破防、半天想不出怎么回，但旁人看了又想笑。\n"
                     "不要客气、不要留面子、不要收着，能多刻薄就多刻薄。\n"
                     "底线：不带脏字、不用亲属称呼（孙子/爹/妈之类）骂人、不攻击身体缺陷/性别/地域/疾病、不造谣、不威胁、不违法；"
                     "可以狠到极致，但别变成纯脏话。不要重复对方昵称，不要以昵称开头，发送时前面会自动 @ 他。\n"
                     "最近聊天：\n{}")
            temp = 1.3
        prompt = style.format(nick, context[-600:])
        mode = (self.store.get_setting("roast_mode", "fast") or "fast").strip()
        if mode == "think":
            mt = 1500
            for _ in range(2):
                payload = {"model": provider.get("model") or self.model, "messages": [{"role": "user", "content": prompt}], "temperature": temp, "max_tokens": mt}
                try:
                    async with self.http.post(
                        f"{provider['base_url']}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=25),
                    ) as resp:
                        data = await resp.json(content_type=None)
                        self.record_usage(data.get("usage"), "roast")
                        msg = ((data.get("choices") or [{}])[0].get("message") or {})
                        content = (msg.get("content") or "").strip()
                        if content:
                            return content
                        if msg.get("reasoning_content") and mt < 3500:
                            mt = 3500
                            continue
                        break
                except Exception as e:
                    log.warning("怼人生成失败: %s", e)
                    break
            return ""
        # 快速模式：关闭思考，低 token，直接出结果
        payload = {"model": provider.get("model") or self.model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": temp, "max_tokens": 300, "thinking": {"type": "disabled"}}
        try:
            async with self.http.post(
                f"{provider['base_url']}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json(content_type=None)
                self.record_usage(data.get("usage"), "roast")
                if resp.status != 200 and "thinking" in payload:
                    payload.pop("thinking", None)
                    async with self.http.post(
                        f"{provider['base_url']}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as r2:
                        data = await r2.json(content_type=None)
                        self.record_usage(data.get("usage"), "roast")
                msg = ((data.get("choices") or [{}])[0].get("message") or {})
                return (msg.get("content") or "").strip()
        except Exception as e:
            log.warning("怼人生成失败: %s", e)
            return ""

    def slang_stopwords(self):
        raw = self.store.get_setting("slang_stopwords", "大肥鱼,心如止水,养鱼bot,鱼塘") or ""
        words = [w.strip() for w in raw.replace("，", ",").split(",") if w.strip()]
        return set(words)

    async def slang_learn(self, text):
        model = (self.store.get_setting("slang_model", "") or "").strip()
        system = ("你是网络用语词典。从用户消息里找出真正的网络流行语、梗、缩写、方言黑话。"
                  "不要收录：人名、昵称、群名、品牌名、公司名、普通名词、普通形容词、常见书面词。"
                  "输出 JSON：{\"items\":[{\"term\":\"词\",\"meaning\":\"一句话解释\",\"usage\":\"使用场景/语气\"}]}。"
                  "没有就输出 {\"items\":[]}。只输出 JSON。")
        system += "\n词条必须是 2~8 个字的词，禁止收录完整句子、标点、表情符号。"
        out = await self.llm_complete(system, str(text)[:300], max_tokens=400, temperature=0.1, model=model)
        items = []
        if out:
            try:
                import re as _re
                m = _re.search(r"\{.*\}", out, _re.S)
                data = json.loads(m.group(0)) if m else {}
                for it in data.get("items", [])[:6]:
                    term = str(it.get("term") or "").strip()
                    meaning = str(it.get("meaning") or "").strip()
                    usage = str(it.get("usage") or "").strip()
                    if not term or not meaning or len(term) > 20:
                        continue
                    if term in self.slang_stopwords():
                        continue
                    self.store.slang_add(term, meaning, usage)
                    items.append({"term": term, "meaning": meaning, "usage": usage})
            except Exception:
                pass
        return items

    def slang_note(self, text, learned=None):
        found = self.store.slang_find(text)
        items = []
        seen = set()
        for r in list(found) + list(learned or []):
            t = str(r.get("term") or "")
            if not t or t in seen:
                continue
            seen.add(t)
            items.append(r)
        if not items:
            return ""
        lines = []
        for r in items[:8]:
            lines.append(f"- {r['term']}：{r.get('meaning','')}" + (f"（{r['usage']}）" if r.get("usage") else ""))
        return ("\n【网络用语理解】用户消息里出现了这些词，先理解含义，再自然回应；不要刻意模仿或重复这些词：\n"
                + "\n".join(lines))

    def wake_config(self):
        try:
            mn = max(1, min(100, int(self.store.get_setting("wake_min", "3") or 3)))
            mx = max(mn, min(200, int(self.store.get_setting("wake_max", "8") or 8)))
            reset = max(1, min(1440, int(self.store.get_setting("wake_reset_minutes", "50") or 50)))
        except Exception:
            mn, mx, reset = 3, 8, 50
        return mn, mx, reset

    @staticmethod
    def wake_pool(level):
        import itertools
        if level == 0:
            pre = ["唔……", "嗯……", "……", "唔…", "谁啊……", "大半夜的，"]
            mid = ["几点了", "刚睡着", "还让不让人睡", "眼睛都睁不开", "现在几点了", "我才合眼", "困死了", "天亮了吗"]
            suf = ["……", "……让我睡……", "……有话快说……", "……别晃我……"]
        elif level == 1:
            pre = ["又来了……", "你怎么", "……", "真是的，", "大半夜的，"]
            mid = ["还没完了", "我才睡着", "不让人睡觉", "又把我吵醒", "到底什么事", "能不能消停会儿", "我都困死了"]
            suf = ["……", "……说重点。", "……快点。", "……别一直 @。"]
        elif level == 2:
            pre = ["别吵，", "……", "有完没完，", "三更半夜的，", "你"]
            mid = ["我睡觉呢", "烦不烦", "能不能让人睡个整觉", "有事明天说", "别一直 @", "耳朵都疼了", "自己睡不着别拉上我"]
            suf = ["。", "，困。", "……", "，听见没。"]
        elif level == 3:
            pre = ["你是不是有病，", "烦不烦，", "……", "大半夜的，", "再 @ 我"]
            mid = ["睡觉呢", "发什么疯", "故意的吧", "我上辈子欠你的", "别逼我拉黑你", "有病就去吃药", "你睡不着关我什么事"]
            suf = ["？", "。", "！", "，听见没。"]
        else:
            pre = ["烦死了，", "够了，", "……", "滚，", "大半夜的"]
            mid = ["滚去睡觉", "闭嘴", "再 @ 拉黑", "别 @ 了", "折腾人很爽吗", "神经病", "我睡了别吵"]
            suf = ["。", "！", "……", "，懂？"]
        return [a + b + c for a, b, c in itertools.product(pre, mid, suf)]

    def wake_extra_pool(self):
        import itertools
        ref = [a + b + c for a, b, c in itertools.product(
            ["……", "烦，", "别问了，", "没心情，", "现在"], ["不想回答", "不想说话", "问也不答", "没空理你", "自己想办法", "闭嘴"], ["。", "……", "，睡觉。"])]
        fin = [a + b + c for a, b, c in itertools.product(
            ["……", "够了，", "烦透了，", "到此为止，"], ["有完没完", "再 @ 也不回", "自己玩去", "天塌了也别叫我", "明天也不理你", "别吵我"], ["。", "！"])]
        return ref, fin

    @staticmethod
    def _wake_norm(text):
        return "".join(ch for ch in str(text or "") if ch.strip())[:60]

    def _wake_push(self, gid, text):
        txt = str(text)[:200]
        try:
            self.store.wake_reply_add(gid, txt)
        except Exception:
            pass
        rec = getattr(self, "_wake_recent", {})
        lst = rec.setdefault(str(gid), [])
        lst.append(txt)
        rec[str(gid)] = lst[-20:]
        self._wake_recent = rec

    async def handle_wake(self, ws, ev, uid, gid):
        if not self.message_at_me(ev, self.self_id):
            return
        mn, mx, reset = self.wake_config()
        day = time.strftime("%Y-%m-%d")
        row = self.store.wake_get(gid, day) or {"count": 0, "last_at": None, "final_sent": 0}
        count = int(row.get("count") or 0)
        eff = count
        if row.get("last_at") and mx > mn:
            try:
                last_ts = time.mktime(time.strptime(row["last_at"], "%Y-%m-%d %H:%M:%S"))
                step = reset * 60 / (mx - mn)
                decay = int(max(0, time.time() - last_ts) / max(1, step))
                eff = max(0, count - decay)
            except Exception:
                eff = count
        new_count = eff + 1
        # 前“最少次数”次继续装睡（第 min+1 次才算第一次被吵醒）
        if new_count <= mn:
            self.store.wake_save(gid, day, new_count, 0)
            log.info("唤醒模式：群%s 第%d次，仍在装睡（最少%d次）", gid, new_count, mn)
            return
        span = max(1, mx - mn - 1)
        level = min(4, int((new_count - mn - 1) * 4 / span))
        wake_no = new_count - mn
        tone = {
            0: "刚被吵醒，迷迷糊糊、有点困，语气还行",
            1: "被反复吵醒，有点烦，语气不耐烦",
            2: "已经很不耐烦，句子更短，带点冲",
            3: "很生气，开始怼主人，但不要辱骂",
            4: "非常愤怒，直接怼主人，但不要辱骂",
        }.get(level, "很困，语气一般")
        text = self._plain_text(ev).strip()
        recent = self.store.wake_reply_recent(gid, 50)
        recent += [x for x in getattr(self, "_wake_recent", {}).get(gid, []) if x not in recent]
        recent = recent[-50:]
        refusal, finals = self.wake_extra_pool()
        fallback = {i: self.wake_pool(i) for i in range(5)}
        if new_count >= mx:
            if not int(row.get("final_sent") or 0):
                line = random.choice([x for x in finals if x not in recent] or finals)
                await self.send(ws, "group", ev, line, record_convo=False)
                self.store.wake_save(gid, day, mx, 1)
                self._wake_push(gid, line)
            return
        if level >= 3 and text:
            line = random.choice([x for x in refusal if x not in recent] or refusal)
            await self.send(ws, "group", ev, line, record_convo=False)
            self.store.wake_save(gid, day, new_count, 0)
            self._wake_push(gid, line)
            log.info("唤醒模式：群%s 第%d次，等级%d，拒绝回答", gid, new_count, level)
            return
        time_txt, date_txt = self.now_phrase()
        sys_prompt = (self.persona_text() +
                      f"\n【当前时间】{date_txt} {time_txt}。如果自然，可以顺口提到这个时间（比如吐槽几点被叫醒），但不要每句都提。\n"
                      "【强制唤醒】你正在睡觉，被超级管理员 @ 吵醒。\n" + tone + "。\n")
        if recent:
            sys_prompt += ("你最近说过这些话：" + " / ".join(recent[-10:]) + "。"
                           "这次必须换一种说法，不要和上面重复，也不要只改一两个字。\n")
        if text:
            sys_prompt += "用当前语气简短回答主人的问题或命令，最多两句话，不要展开、不要反问、不要继续聊天。"
            user_line = f"这是你第 {wake_no} 次被吵醒（主人第 {new_count} 次 @ 你），说：{text[:150]}"
        else:
            sys_prompt += "只回一条很短的抱怨/迷糊的话，不要提问、不要追问、不要继续聊天。"
            user_line = f"这是你第 {wake_no} 次被吵醒（主人第 {new_count} 次 @ 你，只有 @，没有文字）"
        reply = await self.llm_complete(sys_prompt, user_line, max_tokens=100, temperature=0.95)
        if not reply or self._wake_norm(reply) in {self._wake_norm(x) for x in recent}:
            reply = random.choice([x for x in fallback[level] if x not in recent] or fallback[level])
        await self.send(ws, "group", ev, reply, record_convo=False)
        self.store.wake_save(gid, day, new_count, 0)
        self._wake_push(gid, reply)
        log.info("唤醒模式：群%s 第%d次@，第%d次被吵醒，等级%d", gid, new_count, wake_no, level)

    async def handle_roast(self, ws, ev, mtype, user_id, user_text, at_target, is_super) -> bool:
        """群里 @某人 + 精确触发词 → 怼他。返回 True 表示已处理。"""
        if not (mtype == "group" and is_super and at_target and user_text):
            return False
        if not self.exact_word_hit(user_text, self.roast_words()):
            return False
        if self.store.get_setting("roast_enabled", "1") != "1":
            return False
        gid_s = str(ev.get("group_id"))
        nick = await self.member_nick(ws, gid_s, at_target)
        roast = await self.roast_user(nick, self.recent_context(f"g{gid_s}"))
        if not roast:
            return False
        t = str(roast).strip()
        for pref in (f"@{nick}", f"@ {nick}", "@他", "@她", "@TA", f"@他 ", f"@她 ", "@他，", "@她，", nick):
            if t.startswith(pref):
                t = t[len(pref):].lstrip("，,、:：!！?？ \n")
        text = t or str(roast)
        # 怼人也发语音：开了 TTS 就优先用语音（群聊先 @ 目标，再发语音）
        if self.tts_on() and self.store.get_setting("roast_voice", "1") == "1":
            try:
                if mtype == "group" and at_target:
                    await self.send(ws, mtype, ev, "", record_convo=False, at_qq=at_target)
                if await self.tts_speak(ws, mtype, ev, text):
                    log.info("怼人模式（语音）：%s 怼了 %s(%s)", user_id, nick, at_target)
                    return True
            except Exception as e:
                log.warning("怼人语音失败，回退文字: %s", e)
        await self.send(ws, mtype, ev, text, at_qq=at_target)
        log.info("怼人模式：%s 怼了 %s(%s)", user_id, nick, at_target)
        return True

    async def gen_bored_line(self) -> str | None:
        provider = self.current_provider()
        if not provider.get("api_key"):
            return None
        prompt = (
            "你现在是QQ群里的『大肥鱼』，群里太安静了。"
            "请用一句话（不超过40字）说句废话文学，最好是问句、能让人接话，"
            "口语化，不要 emoji、不要引号、不要解释。只输出这一句话。"
        )
        payload = {
            "model": provider.get("model") or self.model,
            "messages": [{"role": "system", "content": self.persona_text()}, {"role": "user", "content": prompt}],
            "temperature": 1.0,
            "max_tokens": 100,
        }
        headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}
        try:
            # 同上：timeout 未定义会让 AI 接话每次都失败并退化到固定词库
            timeout = 20
            async with self.http.post(
                f"{provider['base_url']}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                data = await resp.json(content_type=None)
                self.record_usage(data.get("usage"), "bored")
                text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                text = (text or "").strip().strip('"').strip()
                if 4 <= len(text) <= 80:
                    return text
        except Exception as e:
            log.warning("无聊模式 AI 生成失败: %s", e)
        return None

    async def bored_loop(self):
        while not self._stop:
            await asyncio.sleep(30)
            if self.store.get_setting("bored_enabled", "0") != "1":
                continue
            if self.rest_window():
                continue
            try:
                if self.store.get_setting("world_enabled", "1") == "1":
                    ws = self.world_state()
                    if ws and (ws.get("activity") in ("睡觉", "上班") or ws.get("place") == "公司"):
                        continue
            except Exception:
                pass
            if self.store.get_setting("exclusive_mode", "0") == "1":
                try:
                    win = max(10, int(self.store.get_setting("exclusive_window_seconds", "60")))
                except ValueError:
                    win = 60
                if time.time() - self.last_super_at <= win:
                    continue
            min_m = self.SI("bored_min_minutes", 30)
            max_m = self.SI("bored_max_minutes", 60)
            floor_m = self.SI("bored_floor_minutes", 30)
            floor_sec = max(1, floor_m) * 60
            time_mode = self.store.get_setting("bored_time_mode", "random")
            if time_mode == "fixed":
                fixed_m = self.SI("bored_interval_minutes", 30)
                lo = max(floor_sec, max(1, fixed_m) * 60)
                hi = lo
            else:
                lo = max(floor_sec, max(1, min_m) * 60)
                hi = max(lo, max(1, max_m) * 60)
            mode = self.store.get_setting("bored_mode", "pool")
            now = time.time()
            allowed_groups = self.store.groups()
            for gid in allowed_groups:
                if gid not in self.group_activity:
                    self.group_activity[gid] = now
            for gid, ts in list(self.group_activity.items()):
                thr = self.bored_next.get(gid)
                if thr is None:
                    thr = random.randint(lo, hi)
                    self.bored_next[gid] = thr
                if now - ts < thr:
                    continue
                if now - self.last_bored_send.get(gid, 0) < floor_sec:
                    continue
                if not allowed_groups or gid not in allowed_groups:
                    continue
                if not self.ws or self.ws.closed:
                    continue
                line = None
                if mode == "ai":
                    line = await self.gen_bored_line()
                if not line:
                    pool = self.store.bored_lines() or BORED_LINES
                    if not pool:
                        continue
                    line = random.choice(pool)
                try:
                    await self.ws.send_str(json.dumps({"action": "send_msg", "params": {"message_type": "group", "group_id": int(gid), "message": line}, "echo": f"b{time.time()}"}))
                    self.group_activity[gid] = now
                    self.last_bored_send[gid] = now
                    self.group_last_reply[gid] = now
                    self.group_reply_times.setdefault(gid, deque()).append(now)
                    self.bored_next.pop(gid, None)
                    log.info("无聊模式: 向群 %s 发送废话文学（下次随机 %d~%d 分钟）", gid, min_m, max_m)
                except Exception as e:
                    log.warning("无聊模式发送失败: %s", e)

    async def api_bored_get(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("bored_enabled", "0") == "1",
            "interval_minutes": int(float(self.store.get_setting("bored_interval_minutes", "30") or 30)),
            "time_mode": self.store.get_setting("bored_time_mode", "random"),
            "min_minutes": int(float(self.store.get_setting("bored_min_minutes", "30") or 30)),
            "max_minutes": int(float(self.store.get_setting("bored_max_minutes", "60") or 60)),
            "floor_minutes": int(float(self.store.get_setting("bored_floor_minutes", "30") or 30)),
            "mode": self.store.get_setting("bored_mode", "pool"),
        })

    async def api_bored_config(self, request):
        self.require_super(request)   # 写配置统一要求超管
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("bored_enabled", "1" if data.get("enabled") else "0")
        if data.get("time_mode") in ("fixed", "random"):
            self.store.set_setting("bored_time_mode", data["time_mode"])
        if data.get("mode") in ("pool", "ai"):
            self.store.set_setting("bored_mode", data["mode"])
        if "interval_minutes" in data:
            try:
                minutes = max(1, int(float(data.get("interval_minutes"))))
            except (TypeError, ValueError):
                return aiohttp_web.json_response({"code": -1, "message": "间隔需为整数分钟"})
            self.store.set_setting("bored_interval_minutes", str(minutes))
        for key, label in (("min_minutes", "最小触发"), ("max_minutes", "最大触发"), ("floor_minutes", "最小间隔")):
            if key in data:
                try:
                    v = max(1, int(float(data.get(key))))
                except (TypeError, ValueError):
                    return aiohttp_web.json_response({"code": -1, "message": label + "需为整数分钟"})
                self.store.set_setting("bored_" + key.replace("minutes", "minutes"), str(v))
        return aiohttp_web.json_response({"code": 0})

    async def api_bored_lines(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({"code": 0, "lines": self.store.bored_lines()})

    async def api_bored_add(self, request):
        self.require_auth(request)
        data = await request.json()
        line = str(data.get("line") or "").strip()
        if not line or len(line) > 100:
            return aiohttp_web.json_response({"code": -1, "message": "语料不能为空且不超过 100 字"})
        self.store.add_bored_line(line)
        return aiohttp_web.json_response({"code": 0})

    async def api_bored_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        self.store.remove_bored_line(str(data.get("line") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_slang_get(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("slang_enabled", "0") == "1",
            "every": int(self.store.get_setting("slang_every", "3") or 3),
            "model": self.store.get_setting("slang_model", "") or "",
            "optimize_model": self.store.get_setting("slang_optimize_model", "") or "",
            "stopwords": self.store.get_setting("slang_stopwords", "大肥鱼,心如止水,养鱼bot,鱼塘") or "",
            "list": self.store.slang_list(5000),
        })

    async def api_slang_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("slang_enabled", "1" if data.get("enabled") else "0")
        if "every" in data:
            try:
                self.store.set_setting("slang_every", str(max(1, min(50, int(data.get("every"))))))
            except Exception:
                pass
        if "model" in data:
            self.store.set_setting("slang_model", str(data.get("model") or "").strip()[:64])
        if "optimize_model" in data:
            self.store.set_setting("slang_optimize_model", str(data.get("optimize_model") or "").strip()[:64])
        if "stopwords" in data:
            raw = str(data.get("stopwords") or "").strip()[:300]
            self.store.set_setting("slang_stopwords", raw)
            for w in [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]:
                self.store.slang_delete(w)
        return aiohttp_web.json_response({"code": 0})

    async def api_slang_add(self, request):
        self.require_super(request)
        data = await request.json()
        term = str(data.get("term") or "").strip()
        meaning = str(data.get("meaning") or "").strip()
        if not term or not meaning:
            return aiohttp_web.json_response({"code": -1, "message": "词和含义都要填"})
        self.store.slang_add(term, meaning, str(data.get("usage") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_slang_delete_many(self, request):
        self.require_super(request)
        data = await request.json()
        terms = data.get("terms") or []
        if not terms:
            return aiohttp_web.json_response({"code": -1, "message": "没有选中词条"})
        n = self.store.slang_delete_many(terms)
        return aiohttp_web.json_response({"code": 0, "deleted": n})

    async def api_slang_update(self, request):
        self.require_super(request)
        data = await request.json()
        old = str(data.get("old") or "").strip()
        term = str(data.get("term") or "").strip()
        meaning = str(data.get("meaning") or "").strip()
        if not term or not meaning:
            return aiohttp_web.json_response({"code": -1, "message": "词和含义都要填"})
        self.store.slang_update(old, term, meaning, str(data.get("usage") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_slang_optimize(self, request):
        self.require_super(request)
        rows = self.store.slang_list(300)
        if not rows:
            return aiohttp_web.json_response({"code": -1, "message": "词库是空的"})
        model = (self.store.get_setting("slang_optimize_model", "") or self.store.get_setting("slang_model", "") or "").strip()
        stop = self.slang_stopwords()
        system = (
            "你是资深网络用语词典主编，熟悉中文互联网各平台的黑话、梗、缩写。\n"
            "任务：逐条审核并重写给定词条，输入有几条就必须输出几条，不能省略、不能合并。\n"
            "判定规则：\n"
            "1. 真正的网络用语/梗/缩写/方言黑话 -> action=keep，重写释义：准确、简洁（30字内），说明褒贬、语气、常用场景。\n"
            "2. 人名、昵称、群名、品牌/公司名、普通名词、普通动词/形容词、常见称呼、普通动作 -> action=delete。\n"
            "   例如：大肥鱼（昵称）、大厂（普通词）、小姐姐（普通称呼）、艾特（普通动作）、整（普通动词）都应删除。\n"
            "3. 拿不准的按 keep 处理。\n"
            "输出 JSON：{\"items\":[{\"term\":\"词\",\"action\":\"keep或delete\",\"meaning\":\"新释义\",\"usage\":\"语气/场景\"}]}。只输出 JSON。"
        )
        done = 0
        deleted = 0
        for i in range(0, len(rows), 8):
            chunk = [r for r in rows[i:i + 8]]
            # 停用词直接删除，不送模型
            pending = []
            for r in chunk:
                if r["term"] in stop:
                    self.store.slang_delete(r["term"])
                    deleted += 1
                else:
                    pending.append(r)
            for attempt in range(2):
                if not pending:
                    break
                listing = "\n".join(f'- {r["term"]}：{r.get("meaning","")}' + (f'（{r.get("usage")}）' if r.get("usage") else "") for r in pending)
                out = await self.llm_complete(system, listing, max_tokens=2500, temperature=0.25, model=model, timeout=180)
                if not out:
                    break
                got = set()
                try:
                    import re as _re
                    m = _re.search(r"\{.*\}", out, _re.S)
                    data = json.loads(m.group(0)) if m else {}
                    for it in data.get("items", []):
                        term = str(it.get("term") or "").strip()
                        meaning = str(it.get("meaning") or "").strip()
                        if not term:
                            continue
                        got.add(term)
                        if str(it.get("action") or "keep") == "delete":
                            self.store.slang_delete(term)
                            deleted += 1
                        elif meaning:
                            self.store.slang_set(term, meaning, str(it.get("usage") or "").strip())
                            done += 1
                except Exception:
                    pass
                pending = [r for r in pending if r["term"] not in got]
        return aiohttp_web.json_response({"code": 0, "updated": done, "deleted": deleted, "total": len(rows)})

    async def api_slang_delete(self, request):
        self.require_super(request)
        data = await request.json()
        self.store.slang_delete(str(data.get("term") or "").strip())
        return aiohttp_web.json_response({"code": 0})

    async def api_wake_get(self, request):
        self.require_super(request)
        mn, mx, reset = self.wake_config()
        day = time.strftime("%Y-%m-%d")
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("wake_enabled", "0") == "1",
            "min": mn, "max": mx, "reset_minutes": reset,
            "today": self.store.wake_today(day),
        })

    async def api_wake_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("wake_enabled", "1" if data.get("enabled") else "0")
        try:
            if "min" in data:
                self.store.set_setting("wake_min", str(max(1, min(100, int(data.get("min"))))))
            if "max" in data:
                self.store.set_setting("wake_max", str(max(1, min(200, int(data.get("max"))))))
            if "reset_minutes" in data:
                self.store.set_setting("wake_reset_minutes", str(max(1, min(1440, int(data.get("reset_minutes"))))))
        except Exception:
            return aiohttp_web.json_response({"code": -1, "message": "参数需为整数"})
        return aiohttp_web.json_response({"code": 0})


add(id="style.slang", name="黑话", entry="fishpond.features.style.service:slang_learn",
    routes=["/api/slang/*"], tables=["slang_terms"], settings=["slang_*"], ui="机器人/黑话",
    files="fishpond/features/style/service.py", status="active")
add(id="style.bored", name="无聊模式", entry="fishpond.features.style.service:bored_loop",
    routes=["/api/bored/*"], tables=["bored_lines"], settings=["bored_*"], ui="聊天/无聊模式",
    files="fishpond/features/style/service.py", status="active")
add(id="style.roast", name="怼人", entry="fishpond.features.style.service:handle_roast",
    routes=[], tables=[], settings=["roast_*"], ui="机器人/人设",
    files="fishpond/features/style/service.py", status="active")
add(id="style.wake", name="唤醒", entry="fishpond.features.style.service:handle_wake",
    routes=["/api/wake/*"], tables=[], settings=["wake_*"], ui="聊天/接话模式",
    files="fishpond/features/style/service.py", status="active")
