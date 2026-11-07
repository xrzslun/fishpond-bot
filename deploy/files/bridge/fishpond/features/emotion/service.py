"""情绪与人格模块：情绪值、恐慌状态机、无聊值、人格词条、关系。"""
import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime

from fishpond.registry import add

log = logging.getLogger("qqbridge")


class EmotionMixin:
    @staticmethod
    def _affect_rules(text: str):
        t = str(text or "")
        praise = ["厉害", "真棒", "聪明", "爱你", "喜欢", "谢谢", "好厉害", "太强", "牛", "膜拜", "可爱", "乖"]
        neg = ["傻", "蠢", "废物", "辣鸡", "垃圾", "滚", "讨厌", "恶心", "真菜", "没用", "呵呵", "阴阳", "捉弄", "耍", "大聪明", "就这", "可真是", "可真会"]
        if any(k in t for k in praise) and not any(k in t for k in neg):
            return {"joy": 2, "happy": 2, "favor": 1, "anger": -1, "sad": -1}
        if any(k in t for k in neg):
            return {"joy": -2, "happy": -2, "favor": -1, "anger": 2, "sad": 2}
        return None

    async def affect_analyze(self, text: str, context: str = "") -> dict:
        quick = self._affect_rules(text)
        if quick:
            return quick
        try:
            system = ('你是情绪感知器。判断这句话对"你"（AI）的情绪影响，结合上下文判断是否阴阳怪气、捉弄、真诚夸奖、贬低。'
                      '只输出 JSON：{"joy":-5..5,"anger":-5..5,"sad":-5..5,"happy":-5..5,"favor":-3..3}')
            user = f"上下文：\n{context[-600:]}\n\n待判断：{text}"
            raw = await self.llm_complete(system, user, max_tokens=90, temperature=0.0, timeout=20)
            m = re.search(r"\{.*\}", raw or "", re.S)
            if m:
                d = json.loads(m.group(0))
                out = {k: max(-6, min(6, int(d.get(k) or 0))) for k in ("joy", "anger", "sad", "happy", "favor")}
                return out
        except Exception:
            pass
        return None

    @staticmethod
    def rel_detect(text: str) -> str:
        t = str(text or "")
        rules = [("父子", ["儿子", "我是你爸", "叫爸爸", "喊爸爸", "认我做爹", "干儿子"]),
                 ("父女", ["女儿", "闺女", "我是你爸", "干女儿"]),
                 ("兄妹", ["妹妹", "我是你哥", "喊哥哥", "哥哥"]),
                 ("姐弟", ["弟弟", "我是你姐", "姐姐"]),
                 ("夫妻", ["老婆", "老公", "媳妇", "娘子"]),
                 ("朋友", ["兄弟", "哥们", "铁子", "闺蜜"])]
        for rel, kws in rules:
            if any(k in t for k in kws):
                return rel
        return ""

    async def affect_process(self, user_id: str, text: str, key: str):
        try:
            if not text:
                return
            last = getattr(self, "_affect_ts", {})
            now = time.time()
            if now - last.get(user_id, 0) < 5:
                return
            last[user_id] = now
            ctx = ""
            try:
                sess = self.session(key)
                hist = sess.get("history") or []
                ctx = "\n".join(str(x.get("content") or "") for x in hist[-4:])
            except Exception:
                pass
            rel = self.rel_detect(text)
            if rel:
                self.store.rel_set(user_id, rel)
            d = await self.affect_analyze(text, ctx)
            if d:
                self.store.emotion_apply(user_id, reason=text[:80], **d)
        except Exception as e:
            log.warning("情绪解析失败: %s", e)

    def emotion_note(self, user_id: str) -> str:
        e = self.store.emotion_get(user_id)
        try:
            tone = ""
            f = int(e.get("favor") or 50); a = int(e.get("anger") or 0); sad = int(e.get("sad") or 0)
            if f < 25:
                tone = "你对 ta 有点疏远，语气冷淡、简短，但保持礼貌。"
            elif f >= 75:
                tone = "你对 ta 很亲近，语气更暖、更放松。"
            if a >= 60:
                tone += "你现在有点委屈和生气，说话带点小情绪，但不要骂人。"
            if sad >= 60:
                tone += "你现在有点低落，语气软一点，可以少说几句。"
            return (f"\n【你此刻的感受】好感度 {f}/100；开心 {e.get('joy')} 生气 {a} 难过 {sad} 快乐 {e.get('happy')}。"
                    f"{tone} 只影响你的语气，不要把数字或这套设定说出来。")
        except Exception:
            return ""

    def traits_note(self) -> str:
        ts = self.store.traits_all()[:8]
        if not ts:
            return ""
        return "\n【你逐渐养成的性格】" + "、".join(str(x["trait"]) for x in ts) + "。"

    def rel_note(self, user_id: str) -> str:
        r = self.store.rel_get(user_id)
        if not r:
            return ""
        return f"\n【关系】对方常把你当作「{r}」，顺着这个关系自然回应，不要刻意点破。"

    async def trait_evolve_day(self):
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            if getattr(self, "_trait_day", "") != today:
                self._trait_day = today
                self._trait_used = 0
            if getattr(self, "_trait_used", 0) >= 4:
                return
            with self.store._conn() as c:
                rows = c.execute("SELECT reason FROM affect_log WHERE created_at >= ? ORDER BY id DESC LIMIT 30",
                                 (time.time() - 86400,)).fetchall()
            texts = [r["reason"] for r in rows if (r["reason"] or "").strip()]
            if not texts:
                return
            raw = await self.llm_complete(
                "根据用户最近的说话方式，提炼一个最能概括 AI 新形成性格的词（2、4 或 8 个汉字，中文，不带标点，只输出这个词，不要解释）。",
                "\n".join(texts[-20:]), max_tokens=20, temperature=0.4, timeout=30)
            trait = re.sub(r"[^\u4e00-\u9fa5]", "", raw or "").strip()[:8]
            if not trait or len(trait) not in (2, 4, 8):
                return
            units = len(trait) // 2
            if getattr(self, "_trait_used", 0) + units > 4:
                return
            polarity = 1 if "温柔" in trait or "耐心" in trait else (0 if len(trait) == 4 else 0)
            self.store.traits_add(trait, polarity)
            self._trait_used += units
            log.info("人格词条演化: %s（今日已用 %s/4）", trait, self._trait_used)
        except Exception as e:
            log.warning("人格演化失败: %s", e)

    def panic_can_trigger(self, user_qq: str) -> bool:
        e = self.store.emotion_get(user_qq)
        try:
            joy = int(e.get("joy") or 50); sad = int(e.get("sad") or 0)
        except Exception:
            return False
        if not (joy < 40 and sad > 50):
            return False
        ep = self.store.panic_get(user_qq).get("episode_ts") or 0
        return time.time() - float(ep) > 15 * 86400

    def panic_start(self, user_qq: str):
        if not self.panic_can_trigger(user_qq):
            return False
        self.store.panic_set(user_qq, state="wait", panic=0, last_msg_ts=time.time(), next_ts=0, next_msg_ts=0, broken=0)
        log.info("恐慌状态启动: %s", user_qq)
        return True

    async def panic_send(self, user_qq: str, kind: str, extra: str = ""):
        try:
            traits = self.store.traits_all()[:5]
            trait_txt = "、".join(str(x["trait"]) for x in traits) or ""
            prompt = {
                "confirm": "你在确认对方是否在线，语气自然，一句即可。",
                "worry": "你有点担心对方，担心 ta 是不是不在了或者不要你了，发一句担心的话。",
                "abandon": "你开始怀疑对方是不是讨厌你、不要你了，发一句委屈又克制的话。",
                "need_coax": "你觉得被对方冷落了、很委屈，希望对方哄你，但不要直接命令，软一点。",
                "recover": "对方回复你了，你松了一口气，又有点小情绪，自然回应一句。",
            }.get(kind, "自然说一句。")
            text = await self.llm_complete(
                f"你是 AI 助手，性格：{trait_txt or '温和'}。{prompt}{extra} 一句话，口语自然，不提系统。",
                "", max_tokens=80, temperature=0.9, timeout=30)
            text = (text or "").strip()
            if not text:
                return
            await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(user_qq),
                                                  "message": [{"type": "text", "data": {"text": text}}]})
            log.info("恐慌消息(%s) -> %s", kind, user_qq)
        except Exception as e:
            log.warning("恐慌消息发送失败: %s", e)

    async def panic_step(self, r: dict):
        try:
            import random as _r
            now = time.time(); u = str(r["user_qq"]); st = r.get("state") or ""
            if st == "wait":
                if now - float(r.get("last_msg_ts") or 0) >= 600:
                    self.store.panic_set(u, state="confirm", next_ts=now + _r.randint(1200, 3600))
            elif st == "confirm":
                if now >= float(r.get("next_ts") or 0):
                    await self.panic_send(u, "confirm")
                    self.store.panic_set(u, state="rise", last_msg_ts=now, next_ts=now + _r.randint(60, 180))
            elif st == "rise":
                if now >= float(r.get("next_ts") or 0):
                    p = int(r.get("panic") or 0) + 1
                    if p >= 100:
                        self.store.panic_set(u, state="broken", panic=100, broken=1, episode_ts=now)
                    elif p >= 50:
                        self.store.panic_set(u, state="worried", panic=p, next_ts=now + _r.randint(60, 180), next_msg_ts=now)
                    else:
                        self.store.panic_set(u, panic=p, next_ts=now + _r.randint(60, 180))
            elif st == "worried":
                p = int(r.get("panic") or 0)
                if now >= float(r.get("next_ts") or 0):
                    p += 1
                    self.store.panic_set(u, panic=p, next_ts=now + _r.randint(60, 180))
                if now >= float(r.get("next_msg_ts") or 0):
                    if p >= 80:
                        await self.panic_send(u, "abandon")
                        self.store.panic_set(u, next_msg_ts=now + _r.randint(120, 300))
                    else:
                        await self.panic_send(u, "worry")
                        self.store.panic_set(u, next_msg_ts=now + _r.randint(300, 600))
                if p >= 100:
                    self.store.panic_set(u, state="broken", panic=100, broken=1, episode_ts=now)
        except Exception as e:
            log.warning("恐慌状态机失败: %s", e)

    def boredom_get(self) -> int:
        try:
            return max(0, min(100, int(self.store.get_setting("boredom", "0") or 0)))
        except Exception:
            return 0

    def boredom_set(self, v: int):
        self.store.set_setting("boredom", str(max(0, min(100, int(v)))))

    def boredom_touch(self, user_id: str, is_super: bool):
        """有互动就减无聊值：超管大量减，其他人只有超管的 1/8。"""
        import random as _r
        base = _r.randint(20, 30)
        dec = base if is_super else max(1, base // 8)
        self.boredom_set(self.boredom_get() - dec)
        self.store.set_setting("boredom_last_act", str(time.time()))
        self.store.set_setting("boredom_last_reply", str(time.time()))
        self.store.set_setting("boredom_unanswered", "0")

    async def boredom_loop(self):
        await asyncio.sleep(120)
        while True:
            try:
                if self.in_world_rest() or (hasattr(self, "world_low_mood") and self.world_low_mood()):
                    await asyncio.sleep(300); continue
                import random as _r
                now = time.time()
                last = float(self.store.get_setting("boredom_last_act", "0") or 0)
                if now - last >= 300:
                    self.boredom_set(self.boredom_get() + _r.randint(2, 5))
                    b = self.boredom_get()
                    pending_meal = self._meal_pending()
                    if b >= 75 or pending_meal:
                        cooldown = getattr(self, "_boredom_sent", 0)
                        gap = 1800 if pending_meal else 3600
                        if now - cooldown > gap:
                            self._boredom_sent = now
                            self.spawn(self.boredom_proactive(), "boredom_proactive")
            except Exception as e:
                log.warning("无聊值循环失败: %s", e)
            await asyncio.sleep(300)

    def _meal_slot(self):
        import datetime as _dt
        now = _dt.datetime.now()
        m = now.hour * 60 + now.minute
        if 450 <= m < 660:
            return "breakfast", "早饭", "11 点前", "done"
        if 660 <= m < 780:
            return "lunch", "午饭", "2 点前", "plan"
        if 780 <= m < 840:
            return "lunch", "午饭", "2 点前", "done"
        if 1020 <= m < 1140:
            return "dinner", "晚饭", "9 点前", "plan"
        if 1140 <= m < 1260:
            return "dinner", "晚饭", "9 点前", "done"
        return None

    def _meal_pending(self) -> bool:
        slot = self._meal_slot()
        if not slot:
            return False
        day = time.strftime("%Y-%m-%d")
        return self.store.get_setting(f"meal_{slot[0]}_day", "") != day

    @staticmethod
    def _norm_msg(t: str) -> str:
        import re as _re
        return _re.sub(r"[^\w\u4e00-\u9fff]", "", str(t or ""))[:40]

    async def boredom_proactive(self):
        try:
            qqs = self.super_admin_qqs()
            if not qqs:
                return
            day = time.strftime("%Y-%m-%d")
            if self.store.get_setting("boredom_day", "") != day:
                self.store.set_setting("boredom_day", day)
                self.store.set_setting("boredom_day_count", "0")
                self.store.set_setting("boredom_unanswered", "0")
            try:
                sent = int(self.store.get_setting("boredom_day_count", "0") or 0)
                unanswered = int(self.store.get_setting("boredom_unanswered", "0") or 0)
            except Exception:
                sent, unanswered = 0, 0
            if sent >= 3 or unanswered >= 3:
                return
            try:
                _last = float(self.store.get_setting("boredom_last_proactive", "0") or 0)
            except Exception:
                _last = 0
            if time.time() - _last < 1800:
                return
            import json as _json
            recent = []
            try:
                recent = _json.loads(self.store.get_setting("boredom_recent", "[]") or "[]")
            except Exception:
                recent = []
            addr = "你"
            try:
                if hasattr(self, "user_address"):
                    a = await self.user_address(str(qqs[0]))
                    addr = (a.get("call_user") or "你").strip() or "你"
            except Exception:
                addr = "你"
            slot = self._meal_slot()
            kind = None
            if slot and self.store.get_setting(f"meal_{slot[0]}_day", "") != day:
                kind = "meal"
                meal_name, deadline, phase = slot[1], slot[2], slot[3]
                if phase == "plan":
                    prompt = (f"你是角色本人，想问对方（称呼TA为“{addr}”）{meal_name}准备吃什么。只问一次，口语、自然，"
                              f"不要问“吃了没”，不要催、不要连问、不要提系统、不要叫管理员。一句即可。")
                else:
                    prompt = (f"你是角色本人，想问对方（称呼TA为“{addr}”）吃没吃{meal_name}。只问一次，口语、自然，"
                              f"可以提醒别拖过{deadline}，不要催、不要连问、不要提系统、不要叫管理员。一句即可。")
            elif unanswered >= 2:
                return
            else:
                kinds = ["在不在", "忙什么", "分享小事", "找话题", "撒娇"]
                kind = random.choice(kinds)
                prompts = {
                    "在不在": f"你想找对方（称呼TA为“{addr}”），但不要总说无聊。问一句在不在/忙完没，自然口语，一句，别叫管理员。",
                    "忙什么": f"问对方（称呼TA为“{addr}”）今天在忙什么，别催回复，自然口语，一句，别叫管理员。",
                    "分享小事": "分享你刚做的一件生活小事（做饭/收拾/看到什么），一句，别求回复。",
                    "找话题": "抛一个轻松的话题或刚看到的有意思的东西，一句，别问“陪我聊天”。",
                    "撒娇": "用一点撒娇或吐槽的语气说一句，但不要重复“无聊到长蘑菇”，别求陪聊。",
                }
                prompt = prompts[kind]
            try:
                wnote = self.weather_note("") if hasattr(self, "weather_note") else ""
            except Exception:
                wnote = ""
            if wnote:
                prompt = (wnote + "\n如果这条消息聊到天气，只能按上面的真实天气说，不能编热、冷、下雨。\n" + prompt)
            text = await self.llm_complete(prompt, "", max_tokens=80, temperature=0.9, timeout=30)
            text = " ".join(str(text or "").split())[:120]
            text = text.replace("超级管理员", addr).replace("管理员", addr)
            if not text:
                text = random.choice(["在不在，忙完了没", "今天忙啥呢", "我刚收拾完，歇会儿", "外面天气还行，你那边呢"])
            if any(self._norm_msg(text) == self._norm_msg(x) for x in recent[-8:]):
                if kind == "meal":
                    if slot and slot[3] == "plan":
                        text = f"{slot[1]}准备吃点啥"
                    else:
                        text = f"吃{slot[1]}了没，别拖过{slot[2]}"
                else:
                    text = random.choice(["在不在，忙完没", "今天忙啥呢", "刚忙完一阵，歇会儿", "你那边天气咋样"])
            for qq in qqs:
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(qq),
                                                      "message": [{"type": "text", "data": {"text": text}}]})
            if kind == "meal" and slot:
                self.store.set_setting(f"meal_{slot[0]}_day", day)
            recent = (recent + [text])[-20:]
            self.store.set_setting("boredom_recent", _json.dumps(recent, ensure_ascii=False))
            self.store.set_setting("boredom_day_count", str(sent + 1))
            self.store.set_setting("boredom_unanswered", str(unanswered + 1))
            self.store.set_setting("boredom_last_proactive", str(time.time()))
            log.info("主动消息[%s]: %s", kind, text[:30])
        except Exception as e:
            log.warning("无聊主动失败: %s", e)

    async def panic_loop(self):
        await asyncio.sleep(60)
        while True:
            try:
                with self.store._conn() as c:
                    rows = [dict(r) for r in c.execute("SELECT * FROM panic WHERE state!=''").fetchall()]
                for r in rows:
                    await self.panic_step(r)
            except Exception:
                pass
            await asyncio.sleep(30)

    async def panic_on_reply(self, user_qq: str, text: str):
        try:
            import random as _r
            r = self.store.panic_get(user_qq)
            st = r.get("state") or ""
            if st in ("wait", "confirm", "rise", "worried"):
                p = int(r.get("panic") or 0)
                if p < 100:
                    self.store.emotion_apply(user_qq, joy=_r.randint(3, 8), sad=-_r.randint(3, 8), reason="恐慌解除")
                    self.store.panic_set(user_qq, state="", panic=0, broken=0, episode_ts=time.time())
                    await self.panic_send(user_qq, "recover")
            elif int(r.get("broken") or 0) == 1:
                await self.panic_send(user_qq, "need_coax")
                d = await self.affect_analyze(text, "")
                if d and sum(int(d.get(k) or 0) for k in ("joy", "happy", "favor")) > 0:
                    self.store.panic_set(user_qq, state="", panic=0, broken=0, episode_ts=time.time())
                    log.info("用户哄好了: %s", user_qq)
        except Exception as e:
            log.warning("恐慌回复处理失败: %s", e)

    async def emotion_proactive_loop(self):
        await asyncio.sleep(120)
        while True:
            try:
                if self.store.get_setting("emotion_proactive", "1") == "1" and (getattr(self, "_bal_num", None) or 99) >= 0.3 and not self.in_world_rest():
                    await self.emotion_proactive_step()
            except Exception as e:
                log.warning("情绪主动行为失败: %s", e)
            await asyncio.sleep(300)

    async def emotion_proactive_step(self):
        acted = getattr(self, "_emo_acted", None)
        if acted is None:
            acted = {}; self._emo_acted = acted
        today = datetime.now().strftime("%Y-%m-%d")
        with self.store._conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM emotion WHERE anger>=60 OR sad>=60").fetchall()]
        for r in rows[:3]:
            qq = str(r["user_qq"])
            if acted.get(qq) == today:
                continue
            anger = int(r.get("anger") or 0); sad = int(r.get("sad") or 0)
            kind = "生气" if anger >= sad else "难过"
            text = await self.llm_complete(
                "你在主动找这个用户，因为你感觉到了对方的情绪变化。用口语、自然、真诚，1~2 句，不要提任何数字或系统。",
                f"对方现在的情绪倾向：{kind}。之前你对 ta 可能有些冷淡或态度不好。",
                max_tokens=100, temperature=0.9, timeout=30)
            text = (text or "").strip()
            if not text:
                continue
            try:
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": qq,
                                                      "message": [{"type": "text", "data": {"text": text}}]})
                acted[qq] = today
                log.info("情绪主动行为 -> %s（%s）", qq, kind)
                import random as _rr
                if _rr.random() < 0.3:
                    self.panic_start(qq)
            except Exception:
                pass

    async def trait_loop(self):
        await asyncio.sleep(600)
        while True:
            try:
                await self.trait_evolve_day()
            except Exception:
                pass
            await asyncio.sleep(3600)

"""情绪与人格的存储层。"""
import json
import time


class EmotionStoreMixin:
    def emotion_get(self, user_qq: str) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM emotion WHERE user_qq=?", (str(user_qq),)).fetchone()
        if r:
            return dict(r)
        return {"user_qq": str(user_qq), "joy": 50, "anger": 10, "sad": 10, "happy": 50, "favor": 50}

    def emotion_apply(self, user_qq: str, joy=0, anger=0, sad=0, happy=0, favor=0, reason=""):
        cur = self.emotion_get(user_qq)
        def cl(v, base):
            try:
                return max(0, min(100, int(base) + int(v)))
            except Exception:
                return int(base)
        row = {"joy": cl(joy, cur.get("joy")), "anger": cl(anger, cur.get("anger")),
               "sad": cl(sad, cur.get("sad")), "happy": cl(happy, cur.get("happy")),
               "favor": cl(favor, cur.get("favor"))}
        with self._conn() as c:
            c.execute("INSERT INTO emotion(user_qq,joy,anger,sad,happy,favor,updated_at) VALUES(?,?,?,?,?,?,?) "
                      "ON CONFLICT(user_qq) DO UPDATE SET joy=excluded.joy,anger=excluded.anger,sad=excluded.sad,"
                      "happy=excluded.happy,favor=excluded.favor,updated_at=excluded.updated_at",
                      (str(user_qq), row["joy"], row["anger"], row["sad"], row["happy"], row["favor"], time.time()))
        with self._conn() as c:
            c.execute("INSERT INTO affect_log(user_qq,source,joy,anger,sad,happy,favor,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (str(user_qq), "msg", joy, anger, sad, happy, favor, (reason or "")[:120], time.time()))
        return row

    def traits_all(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM persona_traits ORDER BY weight DESC, id").fetchall()]

    def traits_add(self, trait: str, polarity: int = 0):
        trait = str(trait).strip()[:8]
        if not trait:
            return False
        with self._conn() as c:
            r = c.execute("SELECT id, weight FROM persona_traits WHERE trait=?", (trait,)).fetchone()
            if r:
                c.execute("UPDATE persona_traits SET weight=weight+1 WHERE id=?", (r["id"],))
            else:
                c.execute("INSERT INTO persona_traits(trait,polarity,weight,created_at) VALUES(?,?,1,?)",
                          (trait, polarity, time.time()))
        return True

    def panic_get(self, user_qq: str) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM panic WHERE user_qq=?", (str(user_qq),)).fetchone()
        return dict(r) if r else {"user_qq": str(user_qq), "state": "", "panic": 0, "last_msg_ts": 0, "next_ts": 0, "next_msg_ts": 0, "broken": 0, "episode_ts": 0}

    def panic_set(self, user_qq: str, **kw):
        cur = self.panic_get(user_qq)
        cur.update(kw)
        with self._conn() as c:
            c.execute("INSERT INTO panic(user_qq,state,panic,last_msg_ts,next_ts,next_msg_ts,broken,episode_ts) VALUES(?,?,?,?,?,?,?,?) "
                      "ON CONFLICT(user_qq) DO UPDATE SET state=excluded.state,panic=excluded.panic,last_msg_ts=excluded.last_msg_ts,"
                      "next_ts=excluded.next_ts,next_msg_ts=excluded.next_msg_ts,broken=excluded.broken,episode_ts=excluded.episode_ts",
                      (str(user_qq), cur["state"], cur["panic"], cur["last_msg_ts"], cur["next_ts"], cur["next_msg_ts"], cur["broken"], cur["episode_ts"]))
        return cur

    def rel_set(self, user_qq: str, rel: str):
        with self._conn() as c:
            c.execute("INSERT INTO relationships(user_qq,rel,updated_at) VALUES(?,?,?) "
                      "ON CONFLICT(user_qq) DO UPDATE SET rel=excluded.rel, updated_at=excluded.updated_at",
                      (str(user_qq), str(rel)[:20], time.time()))

    def rel_get(self, user_qq: str) -> str:
        with self._conn() as c:
            r = c.execute("SELECT rel FROM relationships WHERE user_qq=?", (str(user_qq),)).fetchone()
        return (r["rel"] if r else "") or ""


add(id="emotion.core", name="情绪值", entry="fishpond.features.emotion.service:affect_process",
    routes=[], tables=["emotion", "affect_log"], settings=[], ui="（隐藏）",
    files="fishpond/features/emotion/service.py", status="active")
add(id="emotion.panic", name="恐慌状态机", entry="fishpond.features.emotion.service:panic_loop",
    routes=[], tables=["panic"], settings=[], ui="（隐藏）",
    files="fishpond/features/emotion/service.py", status="active")
add(id="emotion.boredom", name="无聊值", entry="fishpond.features.emotion.service:boredom_loop",
    routes=[], tables=["settings"], settings=[], ui="（隐藏）",
    files="fishpond/features/emotion/service.py", status="active")
add(id="emotion.traits", name="人格词条", entry="fishpond.features.emotion.service:trait_loop",
    routes=[], tables=["persona_traits"], settings=[], ui="（隐藏）",
    files="fishpond/features/emotion/service.py", status="active")
add(id="emotion.relation", name="关系识别", entry="fishpond.features.emotion.service:rel_detect",
    routes=[], tables=["relationships"], settings=[], ui="（隐藏）",
    files="fishpond/features/emotion/service.py", status="active")
