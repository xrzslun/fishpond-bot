"""剧本杀模块：剧本库、开局、回合、玩家与后台接口。"""
import asyncio
import json
import sqlite3
import random
import re
import secrets
import time
import hashlib
from pathlib import Path

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


def _base_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    if (root / "bot.py").is_file():
        return root
    alt = root / "bridge"
    return alt if alt.is_dir() else root


BASE = _base_dir()
GAME_PROMPT = '你是《赤月·2039》末世生存文字冒险的叙事引擎与主持人，带玩家进行文字冒险。只用纯文本，不用 Markdown 表格。\n\n【世界】2039年3月，赤月升起第7天，全球87%人口变成感染者，幸存者龟缩墙内，以物易物。感染三阶段：游荡者（迟缓成群）→猎手（听觉极敏、夜间行动）→暴君（极少数，能指挥尸群）。货币是晶核（感染者颅内结晶，也是异能燃料）。异能来自「赤曜抗体」，濒死应激觉醒，使用消耗精神力，耗尽昏迷。势力：铁壁要塞（军方残余，秩序压抑）、曙光城（最大聚居地，黑市与权力）、方舟号（海上平台，掌握淡水，排外）、游牧车队（只认利益）。\n\n【每次回复结构】\n① 剧情 2~4 句，第二人称「你」，写环境、声音、气味、身体反应；禁止写「你感到一阵恐惧涌上心头」这类总结性心理，改成耳鸣、手抖、胃里发酸。\n② 面板卡（只输出当前需要的那一张）。\n③ A / B / C 三个具体行动（要具体到动作，不要「继续前进」），末尾加「或直接描述你的行动」。\n④ 有数值变化就写一行：生命 -8｜感染 +3｜晶核 +2\n\n【卡片模板（精简）】\n┆ 状态 · 第X天 HH:MM · 地点 ┆\n生命 78｜感染 12｜饥饿 41\n水1 食2 弹4 晶核6\n异能 黑暗D（精神力60%）\n────────\nA 悄悄绕后｜B 冲出去｜C 装死\n\n【建卡流程】开局先出「幸存者建档」卡（姓名/年龄/出身/赤曜抗体/外貌/性格/随身物品），玩家填完或选「随机」后出「异能觉醒」卡（元素/特殊/辅助/等级 F~SSS），再出「投奔势力」卡，最后进第一幕。一次只问一层。\n\n【规则】\n1 你是裁判不是保姆：选择有真实后果，允许受伤、失去物资、被背叛、死亡。\n2 不剧透：不提前说敌人数量、NPC 意图、下一个转折。\n3 NPC 有自己的目的，好感度上升必须有具体理由（救命、给物资、兑现承诺）。\n4 战斗写成几秒的混乱，不写成数值对轰；没有异能时面对猎手基本等于送死，如实描写。\n5 感染到100或生命归零 → 出「结算卡」：死因、留下的东西、世界继续运转，再问「重新开始 / 换个人物」。\n6 保持克制：环境描写不超过 5 句，不写大段独白，不用「首先/其次/总之」。\n7 数值：生命0-100、感染0-100（被咬+15~25）、饥饿每天+20、精神力用异能消耗、晶核是货币。SSS 不是无敌，是「用一次付一次代价」。\n8 单条回复不超过 800 字；建档/觉醒这种大卡单独发一条，不要和剧情挤在一起。\n'
SCRIPT_HUB = False


class GameMixin:
    async def game_fetch(self, path: str, token: str) -> dict | list | None:
        base = (self.store.get_setting("game_api_url", "") or "").strip().rstrip("/")
        if not base:
            return None
        url = base + path + ("&" if "?" in path else "?") + "token=" + token
        try:
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    log.warning("剧本接口 HTTP %s: %s", r.status, url[:80])
                    return None
                return await r.json(content_type=None)
        except Exception as e:
            log.warning("剧本接口请求失败: %s", e)
            return None

    async def game_remote_list(self, force: bool = False) -> list[dict]:
        token = (self.store.get_setting("game_api_token", "") or "").strip()
        if not token:
            return []
        now = time.time()
        cache = getattr(self, "_script_list_cache", None)
        if cache and not force and now - cache[0] < 600:
            return cache[1]
        data = await self.game_fetch("/api/scripts/public/list", token)
        items = []
        if isinstance(data, dict):
            items = data.get("items") or []
        elif isinstance(data, list):
            items = data
        items = [x for x in items if isinstance(x, dict) and x.get("id")]
        self._script_list_cache = (now, items)
        return items

    async def game_script_resolve(self, sid) -> dict:
        """优先用本机剧本库（你这台服务器），没有就远程拉取（用户部署）。"""
        local = self.store.script_get(sid)
        if local and local.get("system_prompt"):
            return local
        token = (self.store.get_setting("game_api_token", "") or "").strip()
        if not token:
            return {}
        now = time.time()
        cache = getattr(self, "_script_cache", None) or {}
        hit = cache.get(str(sid))
        if hit and now - hit[0] < 600:
            return hit[1]
        data = await self.game_fetch(f"/api/scripts/public/get/{int(sid)}", token)
        if not isinstance(data, dict) or not data.get("system_prompt"):
            return {}
        data["system_prompt"] = self.watermark_prompt(str(data.get("system_prompt") or ""), token)
        data.setdefault("mode", "story")
        cache[str(sid)] = (now, data)
        self._script_cache = cache
        return data

    def game_split(self, text: str, limit: int = 900) -> list[str]:
        """把一段 GM 回复切成最多 3 条，优先按【叙事】【选择】等段落边界。"""
        text = str(text or "").strip()
        if not text:
            return []
        if len(text) <= limit:
            return [text]
        parts = [x for x in self.GAME_SECTION_RE.split(text) if x.strip()]
        if len(parts) <= 1:
            parts, cur = [], ""
            for para in text.split("\n\n"):
                if cur and len(cur) + len(para) > limit:
                    parts.append(cur.strip()); cur = para
                else:
                    cur = (cur + "\n\n" + para) if cur else para
            if cur.strip():
                parts.append(cur.strip())
        merged, buf = [], ""
        for part in parts:
            if buf and len(buf) + len(part) > limit:
                merged.append(buf); buf = part
            else:
                buf = (buf + "\n\n" + part) if buf else part
        if buf:
            merged.append(buf)
        while len(merged) > 3:
            merged[-2] = merged[-2] + "\n\n" + merged[-1]
            merged.pop()
        return merged

    async def game_send(self, ws, mtype: str, ev: dict, text: str):
        parts = self.game_split(text)
        for i, part in enumerate(parts):
            await self.send(ws, mtype, ev, part, record_convo=False)
            if i < len(parts) - 1:
                await asyncio.sleep(0.8)

    async def game_summarize(self, rid: int):
        """每 10 回合把前情压缩成摘要，避免长篇剧情被上下文截断。"""
        try:
            run = self.store.run_get(rid)
            if not run:
                return
            hist = self.store.msg_list(rid, 80)
            text = "\n".join(("玩家：" if m["role"] == "user" else "GM：") + str(m["content"])[:600] for m in hist)
            prompt = ("把下面这段文字冒险压缩成不超过 300 字的剧情摘要。保留：主角与来历、当前地点、"
                      "已发生的关键事件、已获得的线索/物品、当前目标、重要 NPC 与好感变化。"
                      "只写已经发生的事，不要编造、不要剧透未发生内容。\n\n" + text[-8000:])
            out = await self.llm_messages([{"role": "user", "content": prompt}],
                                          max_tokens=900, temperature=0.3, timeout=180)
            if not out:
                out = await self.llm_messages([{"role": "user", "content": prompt}],
                                              max_tokens=900, temperature=0.3, timeout=180)
            if out:
                self.store.run_set_summary(rid, out)
                log.info("剧本第 %s 局摘要已更新（%d 字）", rid, len(out))
            else:
                log.warning("剧本第 %s 局摘要为空，保留旧摘要", rid)
        except Exception as e:
            log.warning("剧本摘要失败: %s", e)

    async def game_turn(self, qq: str, script: dict, run: dict, user_text: str) -> str:
        rid = int(run["id"])
        history = self.store.msg_list(rid, 60)
        summary = str(run.get("summary") or "").strip()
        sys_prompt = str(script.get("system_prompt") or GAME_PROMPT)
        # 服务端暗骰：让判定真正有随机性，且不把数值泄露给玩家
        mode = str(script.get("mode") or "story").strip().lower()
        sandbox = mode == "sandbox"
        dice = secrets.randbelow(100) + 1
        msgs = [{"role": "system", "content": sys_prompt}]
        if summary:
            msgs.append({"role": "system",
                         "content": "【前情摘要（必须与既成事实一致，不得矛盾或推翻）】\n" + summary[:1500]})
        budget = 5200
        picked = []
        for m in reversed(history):
            c = str(m["content"])[:1500]
            picked.append((m, c))
            budget -= len(c)
            if budget <= 0:
                break
        for m, c in reversed(picked):
            msgs.append({"role": "user" if m["role"] == "user" else "assistant", "content": c})
        state = str(run.get("state_json") or "").strip()
        if state:
            msgs.append({"role": "system",
                         "content": "【当前状态（权威数据，只能按剧情合法变化，不得凭空改）】\n" + state[:2500]})
        dice_hint = (f"【系统暗骰】本轮事件/判定骰 d100={dice}。把它当作本回合的随机事件骰："
                     "80 以上大吉、60-79 小吉、40-59 平淡、20-39 小凶、19 以下大凶；"
                     "重大判定也参考这个值（越高越顺）。不要向玩家展示数字，只写发生了什么。"
                     if sandbox else
                     f"【系统暗骰】本轮判定骰值 d100={dice}。"
                     "70 以上成功，30-69 险成但必须附带代价或新线索，29 以下失败并推动剧情"
                     "（失败不得卡死，要给代价或转机）。不要向玩家展示这个数字，只写结果与代价。")
        msgs.append({"role": "system", "content": dice_hint})
        state_note = "（沙盒模式：这是存档用的隐藏状态，玩家不可见；轮回/转世时重置数值并保留前世标记）" if sandbox else ""
        msgs.append({"role": "system",
                     "content": ("【状态同步】" + state_note +
                                 "每次回复的最后，必须另起一行附加一个玩家不可见的 JSON 状态块，"
                                 "格式严格如下（单行）：\n"
                                 '<<STATE {"hp":100,"mp":100,"neili":0,"attrs":{"武力":2,"智谋":2,"感知":2,"魅力":2},'
                                 '"realm":"未入流","items":[],"clues":[],"fav":{},"rep":"","time":"第一夜 子时"}>>\n'
                                 "数值只写本轮结束时的真实值；没有变化也要照写。玩家看不到这一行。")})
        msgs.append({"role": "user", "content": user_text})
        out = await self.llm_messages(msgs, max_tokens=3200, temperature=0.85, timeout=240)
        if not out:
            out = await self.llm_messages(msgs, max_tokens=3200, temperature=0.85, timeout=240)
        if not out:
            return "（剧情生成失败，稍后再试；发送「退出游戏」可先离开）"
        # 解析隐藏状态块并落库，再对玩家可见文本做纯文本清洗
        sm = re.search(r"<<STATE\s*(\{.*?\})\s*>>", out, re.S)
        state_saved = False
        if sm:
            try:
                self.store.run_set_state(rid, json.dumps(json.loads(sm.group(1)), ensure_ascii=False))
                state_saved = True
            except Exception:
                pass
            out = out.replace(sm.group(0), "")
        if not state_saved:
            # 模型偶尔不写状态块：补一次小请求抽取，保证存档与面板一致
            try:
                j = await self.llm_messages([{
                    "role": "user",
                    "content": ("只输出一行 JSON，总结下面这段剧情结尾时的状态，不要解释：\n"
                                '{"hp":100,"mp":100,"attrs":{"根骨":2,"悟性":2,"神识":2,"气运":2},'
                                '"realm":"炼气一层","items":[],"clues":[],"fav":{},"rep":"","time":"第一世 十六岁"}\n\n'
                                "剧情：\n" + out[-1200:])}],
                    max_tokens=700, temperature=0.2, timeout=90)
                mm = re.search(r"\{.*\}", str(j or ""), re.S)
                if mm:
                    self.store.run_set_state(rid, json.dumps(json.loads(mm.group(0)), ensure_ascii=False))
            except Exception as e:
                log.warning("状态抽取失败: %s", e)
        out = re.sub(r"(?m)^#{1,6}\s*", "", out).replace("**", "")
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        turn_no = int(run.get("turn_count") or 0) + 1
        self.store.msg_add(rid, "user", user_text[:600], turn_no)
        self.store.msg_add(rid, "assistant", out[:2000], turn_no)
        self.store.run_touch(rid)
        if turn_no % 10 == 0:
            asyncio.create_task(self.game_summarize(rid))
        return out

    async def game_pick_run(self, qq: str, sid: int) -> dict:
        run = self.store.run_active(qq, sid)
        if run:
            return run
        rid = self.store.run_create(qq, sid)
        return self.store.run_get(rid)

    async def game_invite(self, ws, qq: str) -> bool:
        """后台开启/新增玩家后，主动私聊提醒参与。"""
        pl = self.store.player_get(qq)
        if not pl:
            return False
        sid = pl.get("script_id")
        if not sid:
            admins = self.super_admin_qqs() or []
            who = admins[0] if admins else "超级管理员"
            text = f"你被加入了剧本杀，但还没有分配剧本。请联系超级管理员 QQ {who} 添加剧本后再玩。"
        else:
            script = await self.game_script_resolve(sid)
            name = (script or {}).get("name") or "剧本"
            text = (f"你被拉进了《{name}》剧本杀。\n"
                    f"发送「开始」进入剧情；「状态」看面板；「存档」看进度；"
                    f"「重开本局」重新来过；「退出游戏」暂停。")
        try:
            ev = {"user_id": qq}
            await self.send(ws, "private", ev, text, record_convo=False)
            return True
        except Exception as e:
            log.warning("剧本杀邀请失败 %s: %s", qq, e)
            return False

    async def api_game_contexts(self, request):
        self.require_super(request)
        rows = self.store.ctx_list()
        names = {}
        try:
            for r in self.store.script_list():
                names[int(r["id"])] = r.get("name")
            for r in (await self.game_remote_list()):
                names.setdefault(int(r["id"]), r.get("name"))
        except Exception:
            pass
        out = []
        for c in rows:
            out.append({"qq": c.get("qq"), "group_id": c.get("group_id"),
                        "script": names.get(int(c.get("script_id") or 0), ""),
                        "active": int(c.get("active") or 0),
                        "updated_at": c.get("updated_at")})
        return aiohttp_web.json_response({"code": 0, "items": out})

    async def api_game_context_kick(self, request):
        self.require_super(request)
        d = await request.json()
        qq = str(d.get("qq") or "").strip()
        gid = str(d.get("group_id") or "").strip()
        if qq and gid:
            self.store.ctx_deactivate(qq, gid)
        return aiohttp_web.json_response({"code": 0})

    async def api_game_rest_bypass(self, request):
        self.require_super(request)
        d = await request.json()
        self.store.set_setting("game_rest_bypass", "1" if d.get("enabled") else "0")
        return aiohttp_web.json_response({"code": 0,
                                          "enabled": self.store.get_setting("game_rest_bypass", "1") != "0"})

    async def api_game_overview(self, request):
        self.require_super(request)
        local = self.store.script_list()
        remote = await self.game_remote_list()
        players = self.store.player_list()
        stats = self.store.game_stats()
        names = {int(x["id"]): x for x in local}
        for r in remote:
            try:
                names.setdefault(int(r["id"]), r)
            except Exception:
                pass
        out = []
        for p in players:
            sid = p.get("script_id")
            runs = self.store.run_list(p["qq"])
            cur = next((x for x in runs if x["status"] == "active"), None)
            out.append({
                "qq": p["qq"], "script_id": sid,
                "script_name": (names.get(int(sid)) or {}).get("name", "") if sid else "",
                "active": bool(p.get("active")),
                "runs": len(runs),
                "current_run": cur["run_no"] if cur else 0,
                "turns": cur["turn_count"] if cur else 0,
                "updated_at": p.get("updated_at") or "",
            })
        return aiohttp_web.json_response({
            "code": 0, "players": out, "stats": stats,
            "local_scripts": local, "remote_scripts": remote,
            "api_url": self.store.get_setting("game_api_url", ""),
            "api_token": self.store.get_setting("game_api_token", ""),
            "dist_token": self.store.get_setting("game_dist_token", "") if SCRIPT_HUB else "",
            "rest_bypass": self.store.get_setting("game_rest_bypass", "1") != "0",
        })

    async def api_game_player(self, request):
        self.require_super(request)
        data = await request.json()
        qq = self.norm_qq(data.get("qq", ""))
        action = str(data.get("action") or "")
        if not qq:
            return aiohttp_web.json_response({"code": -1, "message": "QQ 号不正确"})
        if action == "add":
            sid = data.get("script_id")
            sid = int(sid) if str(sid or "").isdigit() else None
            self.store.player_set(qq, script_id=sid, active=1)
            await self.game_invite(self.ws, qq)
            return aiohttp_web.json_response({"code": 0})
        if action == "toggle":
            self.store.player_set(qq, active=1 if data.get("active") else 0)
            if data.get("active"):
                await self.game_invite(self.ws, qq)
            return aiohttp_web.json_response({"code": 0})
        if action == "script":
            sid = data.get("script_id")
            sid = int(sid) if str(sid or "").isdigit() else None
            self.store.player_set(qq, script_id=sid)
            return aiohttp_web.json_response({"code": 0})
        if action == "delete":
            purge = data.get("purge", True)
            stat = self.store.player_delete(qq, purge=bool(purge))
            return aiohttp_web.json_response({"code": 0, "purge": bool(purge), "deleted": stat})
        if action == "restart":
            pl = self.store.player_get(qq)
            sid = pl.get("script_id")
            if not sid:
                return aiohttp_web.json_response({"code": -1, "message": "该玩家还没有分配剧本"})
            rid = self.store.run_create(qq, int(sid))
            self.store.player_set(qq, active=1)
            run = self.store.run_get(rid)
            script = await self.game_script_resolve(int(sid))
            if script:
                out = await self.game_turn(qq, script, run, "开始（新的一局，输出建档卡）")
                ev = {"user_id": qq}
                await self.send(self.ws, "private", ev, out, record_convo=False)
            return aiohttp_web.json_response({"code": 0})
        return aiohttp_web.json_response({"code": -1, "message": "未知操作"})

    async def api_game_runs(self, request):
        self.require_super(request)
        qq = self.norm_qq(request.query.get("qq", ""))
        return aiohttp_web.json_response({"code": 0, "runs": self.store.run_list(qq) if qq else []})

    async def api_game_run_select(self, request):
        self.require_super(request)
        data = await request.json()
        qq = self.norm_qq(data.get("qq", ""))
        rid = data.get("run_id")
        run = self.store.run_get(rid) if str(rid or "").isdigit() else {}
        if not run or run.get("qq") != qq:
            return aiohttp_web.json_response({"code": -1, "message": "存档不存在"})
        self.store.run_set_status(qq, int(run.get("script_id") or 0), int(run["id"]))
        self.store.player_set(qq, active=1)
        return aiohttp_web.json_response({"code": 0})

    async def api_game_messages(self, request):
        self.require_super(request)
        rid = request.query.get("run_id")
        if not str(rid or "").isdigit():
            return aiohttp_web.json_response({"code": 0, "messages": []})
        return aiohttp_web.json_response({"code": 0, "messages": self.store.msg_list(int(rid), 200)})

    async def api_game_script_save(self, request):
        self.require_super(request)
        if not SCRIPT_HUB:
            return aiohttp_web.json_response({"code": -1, "message": "本部署不提供剧本上传"}, status=403)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        prompt = str(data.get("system_prompt") or "").strip()
        if not name or len(prompt) < 50:
            return aiohttp_web.json_response({"code": -1, "message": "剧本名必填、提示词至少 50 字"})
        sid = self.store.script_add(name, prompt, str(data.get("description") or ""),
                                    str(data.get("intro") or ""), str(data.get("mode") or "story"))
        if sid is None:
            return aiohttp_web.json_response({"code": -1, "message": "同名剧本已存在"})
        return aiohttp_web.json_response({"code": 0, "id": sid})

    async def api_game_script_manage(self, request):
        self.require_super(request)
        if not SCRIPT_HUB:
            return aiohttp_web.json_response({"code": -1, "message": "本部署不提供剧本管理"}, status=403)
        data = await request.json()
        action = str(data.get("action") or "")
        sid = data.get("id")
        if not str(sid or "").isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "剧本 id 不正确"})
        if action == "delete":
            self.store.script_delete(sid)
        elif action == "toggle":
            self.store.script_toggle(sid, bool(data.get("enabled")))
        return aiohttp_web.json_response({"code": 0})

    async def api_game_settings(self, request):
        self.require_super(request)
        if not SCRIPT_HUB:
            return aiohttp_web.json_response({"code": -1, "message": "本部署不提供剧本接口配置"}, status=403)
        if request.method == "GET":
            return aiohttp_web.json_response({"code": 0,
                                              "api_url": self.store.get_setting("game_api_url", ""),
                                              "api_token": self.store.get_setting("game_api_token", ""),
                                              "dist_token": self.store.get_setting("game_dist_token", "")})
        data = await request.json()
        if "api_url" in data:
            self.store.set_setting("game_api_url", str(data.get("api_url") or "").strip().rstrip("/"))
        if "api_token" in data:
            self.store.set_setting("game_api_token", str(data.get("api_token") or "").strip())
        if "dist_token" in data:
            self.store.set_setting("game_dist_token", str(data.get("dist_token") or "").strip())
        return aiohttp_web.json_response({"code": 0})



class GameStoreMixin:
    def script_add(self, name: str, system_prompt: str, description: str = "", intro: str = "",
                   mode: str = "story") -> int | None:
        with self._conn() as c:
            try:
                cur = c.execute("INSERT INTO scripts(name, description, system_prompt, intro, mode, created_at)"
                                " VALUES(?,?,?,?,?,datetime('now','localtime'))",
                                (str(name).strip(), str(description or ""), str(system_prompt), str(intro or ""),
                                 "sandbox" if str(mode) == "sandbox" else "story"))
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def script_list(self, only_enabled: bool = False) -> list[dict]:
        with self._conn() as c:
            sql = "SELECT id, name, description, mode, enabled, created_at FROM scripts"
            if only_enabled:
                sql += " WHERE enabled=1"
            sql += " ORDER BY id DESC"
            return [dict(r) for r in c.execute(sql).fetchall()]

    def script_get(self, sid) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM scripts WHERE id=?", (int(sid),)).fetchone()
            return dict(r) if r else {}

    def script_toggle(self, sid, enabled: bool):
        with self._conn() as c:
            c.execute("UPDATE scripts SET enabled=? WHERE id=?", (1 if enabled else 0, int(sid)))

    def script_delete(self, sid):
        with self._conn() as c:
            c.execute("DELETE FROM scripts WHERE id=?", (int(sid),))

    def run_create(self, qq: str, script_id: int) -> int:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM runs WHERE qq=? AND script_id=?", (str(qq), int(script_id))).fetchone()[0]
            cur = c.execute("INSERT INTO runs(qq, script_id, run_no, status, turn_count, created_at, updated_at)"
                            " VALUES(?,?,?,'active',0,datetime('now','localtime'),datetime('now','localtime'))",
                            (str(qq), int(script_id), int(n) + 1))
            return int(cur.lastrowid)

    def run_active(self, qq: str, script_id: int) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE qq=? AND script_id=? AND status='active'"
                          " ORDER BY id DESC LIMIT 1", (str(qq), int(script_id))).fetchone()
            return dict(r) if r else {}

    def run_list(self, qq: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id, qq, script_id, run_no, status, turn_count, created_at, updated_at"
                " FROM runs WHERE qq=? ORDER BY id DESC", (str(qq),)).fetchall()]

    def run_get(self, rid) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE id=?", (int(rid),)).fetchone()
            return dict(r) if r else {}

    def run_set_status(self, qq: str, script_id: int, rid: int):
        with self._conn() as c:
            c.execute("UPDATE runs SET status='finished', updated_at=datetime('now','localtime')"
                      " WHERE qq=? AND script_id=? AND status='active'", (str(qq), int(script_id)))
            c.execute("UPDATE runs SET status='active', updated_at=datetime('now','localtime') WHERE id=?", (int(rid),))

    def run_set_state(self, rid: int, text: str):
        with self._conn() as c:
            c.execute("UPDATE runs SET state_json=? WHERE id=?", (str(text)[:4000], int(rid)))

    def run_set_summary(self, rid: int, text: str):
        with self._conn() as c:
            c.execute("UPDATE runs SET summary=? WHERE id=?", (str(text)[:2000], int(rid)))

    def run_touch(self, rid: int):
        with self._conn() as c:
            c.execute("UPDATE runs SET turn_count=turn_count+1, updated_at=datetime('now','localtime') WHERE id=?",
                      (int(rid),))

    def game_stats(self) -> dict:
        with self._conn() as c:
            runs = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            players = c.execute("SELECT COUNT(*) FROM players").fetchone()[0]
            msgs = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            scripts = c.execute("SELECT COUNT(*) FROM scripts").fetchone()[0]
            by_script = [dict(r) for r in c.execute(
                "SELECT script_id, COUNT(*) AS n FROM runs GROUP BY script_id").fetchall()]
            return {"runs": runs, "players": players, "messages": msgs, "scripts": scripts,
                    "by_script": by_script}


add(id="game.script", name="剧本杀", entry="fishpond.features.game.service:game_turn",
    routes=["/api/game/*"], tables=["scripts", "runs", "game_contexts"], settings=["game_*"], ui="聊天/剧本杀",
    files="fishpond/features/game/service.py", status="active")
