"""群管理模块：巡查、禁言、踢人、验证、黑名单、关键词。"""
import asyncio
import json
import random
import re
import time
from datetime import datetime

import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


class GroupMixin:
    def gm_pick_question(self, gid: str = "") -> tuple[str, str]:
        """从多题库随机抽一题；题库格式：每行「问题|答案」。"""
        raw = self.gm_get("gm_questions", gid, "") or ""
        pool = []
        for line in re.split(r"\r?\n", raw):
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"\s*[|｜]\s*|\s*=>\s*", line, maxsplit=1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                pool.append((parts[0].strip(), parts[1].strip()))
        if pool:
            return random.choice(pool)
        q = self.gm_get("gm_question", gid, "请回答：1+1 等于几？")
        ans = self.gm_get("gm_answer", gid, "2")
        return q, ans

    def gm_groups(self) -> list[str]:
        """返回"启用群管理"的群号。

        群面板里「停用」的群必须整体排除：它可能仍存在于 settings.gm_groups
        或 group_cfg 里（历史配置），但用户点了停用就不该再被管。
        """
        raw = self.store.get_setting("gm_groups", "") or ""
        out = [x for x in re.split(r"[,，\s]+", raw) if x.isdigit()]
        disabled: set[str] = set()
        try:
            for it in self.store.group_panels():
                g = str(it.get("group_id") or "")
                if not g.isdigit():
                    continue
                if int(it.get("enabled") or 0) == 0:
                    disabled.add(g)
                elif g not in out:
                    out.append(g)
            with self.store._conn() as c:
                for r in c.execute("SELECT group_id FROM group_cfg WHERE key='gm_groups'"):
                    g = str(r["group_id"])
                    if g.isdigit() and g not in out:
                        out.append(g)
        except Exception:
            pass
        if disabled:
            removed = [g for g in out if g in disabled]
            if removed:
                out = [g for g in out if g not in disabled]
                # 每个群每小时只提示一次，避免每条群消息刷日志
                logged = getattr(self, "_gm_skip_logged", None)
                if logged is None:
                    logged = {}
                    self._gm_skip_logged = logged
                now = time.time()
                for g in removed:
                    if now - logged.get(g, 0) > 3600:
                        logged[g] = now
                        log.info("群管理已停用，跳过: %s", g)
        return out

    def gm_black(self, gid: str, qq: str) -> bool:
        try:
            raw = self.store.group_cfg_get(gid, "gm_blacklist", "") or ""
            if raw:
                for it in json.loads(raw):
                    if str(it.get("qq")) == str(qq):
                        return True
        except Exception:
            pass
        return self.store.is_group_black(str(qq))

    def gm_get(self, key: str, gid: str = "", default: str = "") -> str:
        if gid:
            v = self.store.group_cfg_get(gid, key, "")
            if v != "":
                return v
        return self.store.get_setting(key, default) or default

    def gm_kw_g(self, key: str, gid: str = "", default: str = "") -> list[str]:
        raw = self.gm_get(key, gid, default) or default
        return [x.strip() for x in re.split(r"[,，\n]+", raw) if x.strip()]

    def gm_kw(self, key: str, default: str = "") -> list[str]:
        raw = self.store.get_setting(key, default) or default
        return [x.strip() for x in re.split(r"[,，\n]+", raw) if x.strip()]

    def gm_kick_allowed(self, uid: str) -> bool:
        if self.is_super_admin(uid):
            return True
        extra = re.split(r"[,，\s]+", self.store.get_setting("gm_kick_qqs", "") or "")
        return uid in [x for x in extra if x.isdigit()]

    async def gm_bot_is_admin(self, gid: str) -> bool:
        try:
            res = await self.onebot_action("get_group_member_info",
                                           {"group_id": gid, "user_id": self.self_id, "no_cache": True})
            d = (res or {}).get("data") or {}
            return str(d.get("role") or "") in ("admin", "owner")
        except Exception:
            return False

    def gm_pending(self, uid: str, gid: str = "") -> list:
        with self.store._conn() as c:
            if gid:
                rows = c.execute("SELECT * FROM join_verify WHERE user_id=? AND group_id=?", (uid, gid)).fetchall()
                if rows:
                    return [dict(r) for r in rows]
            rows = c.execute("SELECT * FROM join_verify WHERE user_id=?", (uid,)).fetchall()
            return [dict(r) for r in rows]

    async def handle_group_request(self, ev: dict, ws):
        try:
            if str(ev.get("sub_type") or "") not in ("add", ""):
                return
            gid = str(ev.get("group_id") or "")
            uid = str(ev.get("user_id") or "")
            flag = str(ev.get("flag") or "")
            if not gid or not uid:
                return
            # 黑名单：进群申请直接拒绝（不受管理群/自动通过开关限制）
            if self.gm_black(gid, uid):
                if await self.gm_bot_is_admin(gid):
                    await self.onebot_action("set_group_add_request",
                                             {"flag": flag, "sub_type": "add",
                                              "approve": False, "reason": "黑名单"})
                    log.info("黑名单拒绝进群: %s @ %s", uid, gid)
                return
            if gid not in self.gm_groups():
                return
            if self.gm_get("gm_auto_approve", gid, "0") != "1":
                return
            if not await self.gm_bot_is_admin(gid):
                log.info("群 %s 申请：机器人不是管理员，跳过", gid)
                return
            await self.onebot_action("set_group_add_request",
                                     {"flag": flag, "sub_type": "add", "approve": True})
            await asyncio.sleep(2)
            nick = uid
            try:
                info = await self.onebot_action("get_group_member_info",
                                                {"group_id": gid, "user_id": uid, "no_cache": True})
                nick = str(((info or {}).get("data") or {}).get("card")
                           or ((info or {}).get("data") or {}).get("nickname") or uid)
            except Exception:
                pass
            now = datetime.now()
            bot_nick = ""
            try:
                st = await self.napcat_login_info()
                bot_nick = str(st.get("nick") or "")
            except Exception:
                pass
            gname = ""
            try:
                gi = await self.onebot_action("get_group_info", {"group_id": gid, "no_cache": True})
                gname = str(((gi or {}).get("data") or {}).get("group_name") or "")
            except Exception:
                pass
            welcome = (self.gm_get("gm_welcome", gid, "") or "")
            for k, v in {"{nick}": nick, "{qq}": uid, "{group}": gid, "{group_name}": gname,
                         "{bot}": bot_nick or str(self.self_id), "{date}": now.strftime("%Y-%m-%d"),
                         "{time}": now.strftime("%H:%M:%S"), "{at}": f"@{nick}"}.items():
                welcome = welcome.replace(k, v)
            if welcome:
                ev2 = {"group_id": gid}
                await self.send(ws, "group", ev2, welcome, record_convo=False, at_qq=uid)
            if self.gm_get("gm_verify", gid, "0") == "1":
                q, ans = self.gm_pick_question(gid)
                try:
                    tmo = max(1, int(self.gm_get("gm_timeout_min", gid, "5") or 5))
                except Exception:
                    tmo = 5
                mode = (self.gm_get("gm_verify_mode", gid, "private") or "private").strip()
                with self.store._conn() as c:
                    c.execute("INSERT OR REPLACE INTO join_verify(group_id,user_id,answer,mode,deadline,tries,created_at)"
                              " VALUES(?,?,?,?,?,0,?)", (gid, uid, ans, mode, time.time() + tmo * 60, time.time()))
                tip = f"欢迎 {nick} 进群～\n请在 {tmo} 分钟内回答：{q}\n（答错 2 次或超时会被移出）"
                if mode == "private":
                    r = await self.onebot_action("send_msg", {"message_type": "private", "user_id": uid,
                                                              "message": [{"type": "text", "data": {"text": tip}}]})
                    if not r or int(r.get("retcode", -1)) != 0:
                        ev3 = {"group_id": gid}
                        await self.send(ws, "group", ev3, tip, record_convo=False, at_qq=uid)
                else:
                    ev3 = {"group_id": gid}
                    await self.send(ws, "group", ev3, tip, record_convo=False, at_qq=uid)
            log.info("群 %s 已自动通过 %s 的进群申请（验证=%s）", gid, uid,
                     self.store.get_setting("gm_verify", "0"))
        except Exception as e:
            log.warning("处理进群申请失败: %s", e)

    async def handle_verify_reply(self, ws, ev, mtype, user_text: str) -> bool:
        uid = str(ev.get("user_id") or "")
        if not uid or not user_text:
            return False
        gid = str(ev.get("group_id") or "")
        rows = self.gm_pending(uid, gid)
        if not rows:
            return False
        for r in rows:
            try:
                ok = str(user_text).strip() == str(r.get("answer") or "").strip()
            except Exception:
                ok = False
            with self.store._conn() as c:
                if ok:
                    c.execute("DELETE FROM join_verify WHERE group_id=? AND user_id=?", (r["group_id"], uid))
                else:
                    c.execute("UPDATE join_verify SET tries=tries+1 WHERE group_id=? AND user_id=?", (r["group_id"], uid))
            if ok:
                await self.send(ws, mtype, ev, "验证通过，欢迎～", record_convo=False)
                log.info("进群验证通过: %s @ %s", uid, r["group_id"])
                return True
            tries = int(r.get("tries") or 0) + 1
            if tries >= 2:
                await self.onebot_action("set_group_kick", {"group_id": r["group_id"], "user_id": uid,
                                                            "reject_add_request": False})
                with self.store._conn() as c:
                    c.execute("DELETE FROM join_verify WHERE group_id=? AND user_id=?", (r["group_id"], uid))
                await self.send(ws, mtype, ev, "答案不对，已移出群聊。", record_convo=False)
                log.info("进群验证失败已踢出: %s @ %s", uid, r["group_id"])
                await self.gm_notify_punish(r["group_id"], uid, "进群验证：答错 2 次，已移出")
            else:
                await self.send(ws, mtype, ev, "答案不对，再试一次（还有 1 次机会）。", record_convo=False)
            return True
        return False

    async def gm_timeout_loop(self):
        await asyncio.sleep(20)
        while True:
            try:
                with self.store._conn() as c:
                    rows = [dict(r) for r in c.execute(
                        "SELECT * FROM join_verify WHERE deadline < ?", (time.time(),)).fetchall()]
                for r in rows:
                    gid, uid = r["group_id"], r["user_id"]
                    if await self.gm_bot_is_admin(gid):
                        await self.onebot_action("set_group_kick", {"group_id": gid, "user_id": uid,
                                                                    "reject_add_request": False})
                    with self.store._conn() as c:
                        c.execute("DELETE FROM join_verify WHERE group_id=? AND user_id=?", (gid, uid))
                    try:
                        await self.send(self.ws, "group", {"group_id": gid},
                                        f"{uid} 超时未完成验证，已移出群聊。", record_convo=False)
                    except Exception:
                        pass
                    log.info("进群验证超时已踢出: %s @ %s", uid, gid)
                    await self.gm_notify_punish(gid, uid, "进群验证：超时未完成，已移出")
            except Exception as e:
                log.warning("验证超时检查失败: %s", e)
            await asyncio.sleep(20)

    async def gm_notify_punish(self, gid: str, uid: str, reason: str):
        """把处罚信息私聊发给后台填写的管理者 QQ。"""
        try:
            raw = self.gm_get("gm_punish_qqs", gid, "") or ""
            qqs = [x for x in re.split(r"[,，\s]+", raw) if x.isdigit()]
            if not qqs:
                qqs = self.super_admin_qqs()
            if not qqs:
                return
            nick = uid
            try:
                info = await self.onebot_action("get_group_member_info",
                                                {"group_id": gid, "user_id": uid, "no_cache": True})
                d = (info or {}).get("data") or {}
                nick = str(d.get("card") or d.get("nickname") or uid)
            except Exception:
                pass
            body = (f"触发用户\nQQ：{uid}\n群昵称：{nick}\n"
                    f"处罚时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n处罚原因：{reason}")
            for qq in qqs:
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": qq,
                                                      "message": [{"type": "text", "data": {"text": body}}]})
        except Exception as e:
            log.warning("处罚通知失败: %s", e)

    async def gm_kwlimit_check(self, ws, ev, text: str) -> bool:
        """关键词频率限制：每个词在窗口内只允许 N 条，超出自动撤回。"""
        raw = self.gm_get("gm_kwlimit_rules", str(ev.get("group_id") or ""), "") or ""
        if not raw.strip() or not text:
            return False
        gid = str(ev.get("group_id") or "")
        rules = []
        for line in re.split(r"\r?\n", raw):
            parts = [x.strip() for x in line.split("|")]
            if len(parts) < 3 or not parts[0]:
                continue
            try:
                win = max(1, int(parts[1])); cnt = max(1, int(parts[2]))
            except Exception:
                continue
            rules.append((parts[0], win, cnt))
        if not rules:
            return False
        store = getattr(self, "_kwlimit", None)
        if store is None:
            store = {}; self._kwlimit = store
        now = time.time()
        for kw, win, cnt in rules:
            if kw not in text:
                continue
            key = (gid, kw)
            dq = store.get(key)
            if dq is None:
                dq = []; store[key] = dq
            while dq and now - dq[0] > win:
                dq.pop(0)
            if len(dq) < cnt:
                dq.append(now)
                continue
            mid = ev.get("message_id")
            if mid:
                await self.onebot_action("delete_msg", {"message_id": mid})
            log.info("关键词限频撤回: %s 在 %s 触发「%s」（%ss 内仅 %s 条）",
                     ev.get("user_id"), gid, kw, win, cnt)
            try:
                await self.send(ws, "group", {"group_id": gid},
                                f"「{kw}」{win} 秒内只能发 {cnt} 条，已撤回。", record_convo=False)
            except Exception:
                pass
            return True
        return False

    async def gm_patrol(self, ws, ev, mtype, user_text: str, is_super: bool):
        try:
            if mtype != "group" or is_super:
                return
            if self.gm_get("gm_patrol_enabled", str(ev.get("group_id") or ""), "0") != "1":
                return
            gid = str(ev.get("group_id") or "")
            uid = str(ev.get("user_id") or "")
            if not gid or not uid or gid not in self.gm_groups():
                return
            # 刷屏检测
            try:
                rate = max(2, int(self.gm_get("gm_patrol_rate", gid, "10") or 10))
                mute_min = max(1, int(self.gm_get("gm_patrol_mute_min", gid, "10") or 10))
            except Exception:
                rate, mute_min = 10, 10
            hits = getattr(self, "_patrol_hits", None)
            if hits is None:
                hits = {}; self._patrol_hits = hits
            now = time.time()
            dq = hits.get((gid, uid))
            if dq is None:
                dq = []; hits[(gid, uid)] = dq
            dq.append(now)
            while dq and now - dq[0] > 60:
                dq.pop(0)
            if len(dq) >= rate:
                hits[(gid, uid)] = []
                if await self.gm_bot_is_admin(gid):
                    await self.onebot_action("set_group_ban", {"group_id": gid, "user_id": uid,
                                                               "duration": mute_min * 60})
                warn = (self.gm_get("gm_patrol_warn", gid, "") or
                        "检测到刷屏，已禁言 {minute} 分钟，请注意发言频率。")
                warn = warn.replace("{nick}", uid).replace("{minute}", str(mute_min))
                await self.send(ws, "group", {"group_id": gid}, warn, at_qq=uid, record_convo=False)
                log.info("巡查：%s 在 %s 刷屏，禁言 %s 分钟", uid, gid, mute_min)
                await self.gm_notify_punish(gid, uid, f"刷屏：1 分钟内超过 {rate} 条，禁言 {mute_min} 分钟")
                return
            # AI 合规判断（异步，不阻塞聊天）
            if self.gm_get("gm_ai_patrol", gid, "0") == "1" and user_text.strip():
                last = getattr(self, "_patrol_ai_ts", {})
                if now - last.get((gid, uid), 0) > 30:
                    last[(gid, uid)] = now
                    self.spawn(self.gm_ai_check(ws, gid, uid, str(ev.get("sender", {}).get("nickname") or uid),
                                                user_text, mute_min), "gm_ai_patrol")
        except Exception as e:
            log.warning("巡查失败: %s", e)

    async def gm_ai_check(self, ws, gid, uid, nick, text, mute_min):
        try:
            ctxs = getattr(self, "_patrol_ctx", None)
            if ctxs is None:
                ctxs = {}; self._patrol_ctx = ctxs
            lst = ctxs.get(gid)
            if lst is None:
                lst = []; ctxs[gid] = lst
            lst.append(f"{nick}: {text}"[:200])
            try:
                keep = max(0, min(30, int(self.gm_get("gm_ai_context", gid, "6") or 6)))
            except Exception:
                keep = 6
            if len(lst) > max(10, keep):
                del lst[:len(lst) - max(10, keep)]
            context = "\n".join(lst[-keep:]) if keep else ""
            system = ("你是群聊内容审核器。判断最后一条消息是否违规：广告引流、辱骂人身攻击、色情、暴恐、诈骗、"
                      "政治敏感、刷屏灌水。只输出 JSON：{\"violation\":true/false,\"reason\":\"简短原因\"}。"
                      "不确定时结合上下文判断；仍无法判断则 violation=false。")
            user = (f"最近消息：\n{context}\n\n待判断：{text}" if context else f"待判断：{text}")
            raw = await self.llm_complete(system, user, max_tokens=120, temperature=0.0, timeout=25)
            import re as _re, json as _json
            m = _re.search(r"\{.*\}", raw or "", _re.S)
            if not m:
                return
            d = _json.loads(m.group(0))
            if not d.get("violation"):
                return
            action = (self.gm_get("gm_ai_action", gid, "warn") or "warn").strip()
            reason = str(d.get("reason") or "违规内容")[:40]
            if action == "mute" and await self.gm_bot_is_admin(gid):
                await self.onebot_action("set_group_ban", {"group_id": gid, "user_id": uid,
                                                           "duration": mute_min * 60})
                tip = f"检测到违规（{reason}），已禁言 {mute_min} 分钟。"
            else:
                tip = f"检测到违规（{reason}），本次警告，请注意。"
            await self.send(ws, "group", {"group_id": gid}, tip, at_qq=uid, record_convo=False)
            log.info("AI巡查：%s 判定违规（%s）", uid, reason)
            await self.gm_notify_punish(gid, uid, f"AI 判定违规：{reason}")
        except Exception as e:
            log.warning("AI巡查失败: %s", e)

    @staticmethod
    def gm_parse_minutes(text: str) -> int:
        """从「十分钟」「10分钟」「1小时」「半小时」里解析出分钟数，失败返回 0。"""
        t = str(text or "")
        if "半小时" in t:
            return 30
        cn = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
              "七": 7, "八": 8, "九": 9, "十": 10}
        m = re.search(r"(\d+)\s*(分钟|分|小时|时|天)", t)
        if m:
            n = int(m.group(1)); unit = m.group(2)
            return n * 1440 if unit == "天" else (n * 60 if unit in ("小时", "时") else n)
        m = re.search(r"([一二两三四五六七八九十]+)\s*(分钟|分|小时|时|天)", t)
        if m:
            raw = m.group(1); unit = m.group(2)
            n = 0
            if "十" in raw:
                a, _, b = raw.partition("十")
                n = (cn.get(a, 1) if a else 1) * 10 + (cn.get(b, 0) if b else 0)
            else:
                n = cn.get(raw, 0)
            if n <= 0:
                return 0
            return n * 1440 if unit == "天" else (n * 60 if unit in ("小时", "时") else n)
        return 0

    async def handle_mute_command(self, ws, ev, mtype, user_text: str, is_super, at_target):
        try:
            if mtype != "group" or self.gm_get("gm_mute_enabled", str(ev.get("group_id") or ""), "1") != "1":
                return False
            gid = str(ev.get("group_id") or "")
            uid = str(ev.get("user_id") or "")
            if gid not in self.gm_groups() or not self.gm_kick_allowed(uid):
                return False
            t = str(user_text or "")
            unmute = ("解禁" in t or "解除禁言" in t or "取消禁言" in t)
            if "禁言" not in t and not unmute:
                return False
            target = str(at_target or "")
            if not target:
                m = re.search(r"(\d{5,})", t)
                target = m.group(1) if m else ""
            if not target or target == str(self.self_id):
                return False
            if not await self.gm_bot_is_admin(gid):
                await self.send(ws, mtype, ev, "我不是这个群的管理员，禁言不了。", record_convo=False)
                return True
            info = await self.onebot_action("get_group_member_info",
                                            {"group_id": gid, "user_id": target, "no_cache": True})
            role = str(((info or {}).get("data") or {}).get("role") or "")
            if role in ("admin", "owner"):
                await self.send(ws, mtype, ev, "对方是管理员/群主，不能禁言。", at_qq=target, record_convo=False)
                return True
            minutes = 0 if unmute else self.gm_parse_minutes(t)
            if not unmute and minutes <= 0:
                await self.send(ws, mtype, ev, "请说明禁言时长，例如「@某人 十分钟」。", record_convo=False)
                return True
            seconds = min(30 * 86400, max(0, minutes * 60))
            res = await self.onebot_action("set_group_ban", {"group_id": gid, "user_id": target,
                                                             "duration": seconds})
            if res and int(res.get("retcode", -1)) == 0:
                msg = f"已解除 {target} 的禁言。" if unmute else f"已禁言 {target} {minutes} 分钟。"
                await self.send(ws, mtype, ev, msg, record_convo=False)
                log.info("禁言操作: %s 对 %s %s 分钟 @ %s", uid, target, minutes, gid)
                await self.gm_notify_punish(gid, target,
                    "管理员指令：解除禁言" if unmute else f"管理员指令：禁言 {minutes} 分钟")
            else:
                await self.send(ws, mtype, ev, "禁言失败，请检查机器人权限。", record_convo=False)
            return True
        except Exception as e:
            log.warning("禁言失败: %s", e)
            return False

    async def handle_kick_command(self, ws, ev, mtype, user_text: str, is_super, at_target):
        try:
            if mtype != "group" or self.gm_get("gm_kick_enabled", str(ev.get("group_id") or ""), "1") != "1":
                return False
            uid = str(ev.get("user_id") or "")
            gid = str(ev.get("group_id") or "")
            if gid not in self.gm_groups() or not self.gm_kick_allowed(uid):
                return False
            gid = str(ev.get("group_id") or "")
            kws = self.gm_kw_g("gm_kick_keywords", gid, "踢,踢出群聊")
            add_black = ("加入黑名单" in (user_text or "")) or ("拉黑" in (user_text or ""))
            kick_hit = any(k in (user_text or "") for k in kws)
            if not add_black and not kick_hit:
                return False
            m = re.search(r"(\d{5,})", user_text or "")
            target = str(at_target or "") or (m.group(1) if m else "")
            if not target or target == str(self.self_id):
                return False
            if not await self.gm_bot_is_admin(gid):
                await self.send(ws, mtype, ev, "我不是这个群的管理员，踢不了。", record_convo=False)
                return True
            info = await self.onebot_action("get_group_member_info",
                                            {"group_id": gid, "user_id": target, "no_cache": True})
            role = str(((info or {}).get("data") or {}).get("role") or "")
            if role in ("admin", "owner"):
                await self.send(ws, mtype, ev, "对方是管理员/群主，不能踢。", at_qq=target, record_convo=False)
                return True
            if add_black:
                d = (info or {}).get("data") or {}
                nick = str(d.get("card") or d.get("nickname") or "")
                self.store.add_group_black(target, nick)
                await self.onebot_action("set_group_kick", {"group_id": gid, "user_id": target,
                                                            "reject_add_request": True})
                await self.send(ws, mtype, ev, f"已把 {target} 加入群黑名单并移出。", record_convo=False)
                await self.gm_notify_punish(gid, target, "管理员指令：加入群黑名单")
                log.info("加入群黑名单: %s 将 %s（%s）", uid, target, gid)
                return True
            res = await self.onebot_action("set_group_kick", {"group_id": gid, "user_id": target,
                                                              "reject_add_request": False})
            if res and int(res.get("retcode", -1)) == 0:
                await self.send(ws, mtype, ev, f"已把 {target} 移出群聊。", record_convo=False)
                log.info("踢人: %s 将 %s 移出群 %s", uid, target, gid)
                await self.gm_notify_punish(gid, target, "管理员指令：移出群聊")
            else:
                await self.send(ws, mtype, ev, "踢人失败，请检查机器人权限。", record_convo=False)
            return True
        except Exception as e:
            log.warning("踢人失败: %s", e)
            return False

    async def api_gm_blacklist(self, request):
        self.require_super(request)
        if request.method == "GET":
            return aiohttp_web.json_response({"code": 0, "items": self.store.group_blacklist()})
        d = await request.json()
        act = str(d.get("action") or "")
        qq = str(d.get("qq") or "").strip()
        old = str(d.get("old_qq") or qq).strip()
        nick = str(d.get("nick") or "").strip()
        if act == "remove":
            if not old.isdigit():
                return aiohttp_web.json_response({"code": -1, "message": "QQ 号无效"})
            self.store.remove_group_black(old)
            return aiohttp_web.json_response({"code": 0})
        if not qq.isdigit() or not (5 <= len(qq) <= 12):
            return aiohttp_web.json_response({"code": -1, "message": "QQ 号无效"})
        if act == "update" and old != qq:
            self.store.remove_group_black(old)
        self.store.add_group_black(qq, nick[:40])
        return aiohttp_web.json_response({"code": 0})


add(id="group.patrol", name="刷屏巡查", entry="fishpond.features.group.service:gm_patrol",
    routes=[], tables=["group_cfg"], settings=["gm_patrol_*"], ui="聊天/群聊管理",
    files="fishpond/features/group/service.py", status="active")
add(id="group.kick", name="踢人与禁言", entry="fishpond.features.group.service:handle_kick_command",
    routes=[], tables=[], settings=["gm_kick_*", "gm_mute_enabled"], ui="聊天/群聊管理",
    files="fishpond/features/group/service.py", status="active")
add(id="group.verify", name="进群验证", entry="fishpond.features.group.service:handle_group_request",
    routes=[], tables=["join_verify"], settings=["gm_verify", "gm_questions"], ui="聊天/群聊管理",
    files="fishpond/features/group/service.py", status="active")
add(id="group.blacklist", name="群黑名单", entry="fishpond.features.group.service:gm_black",
    routes=["/api/gm/blacklist"], tables=["group_blacklist", "group_cfg"], settings=[], ui="聊天/群聊管理",
    files="fishpond/features/group/service.py", status="active")
add(id="group.kwlimit", name="关键词频次", entry="fishpond.features.group.service:gm_kwlimit_check",
    routes=[], tables=[], settings=["gm_kwlimit_rules"], ui="聊天/群聊管理",
    files="fishpond/features/group/service.py", status="active")
add(id="panel.group", name="群面板外链", entry="fishpond.features.panel.service:gpage_html",
    routes=["/g/{token}/", "/api/gm/groups", "/api/gm/config"], tables=["group_panel", "group_cfg"],
    settings=[], ui="聊天/群聊管理", files="fishpond/features/panel/service.py", status="active")
