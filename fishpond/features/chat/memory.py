"""记忆模块：记忆检索、提取、清理与后台接口，及存储层。"""
import asyncio
import hashlib
import json
import re
import secrets
import time
from datetime import datetime

import aiohttp.web as aiohttp_web

from fishpond.core.config import MEMORY_FEATURE
from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")

NOISE_WORDS = ('用户提醒', '用户要求', '用户希望', '用户让', '用户告知', '用户叫', '密钥', '部署包', '服务器', 'API', '接口', '安装', '配置', '更新版本', '操作步骤', '步骤')


def _store_cls(obj):
    """Bridge 用 obj.store，Store 自身直接用 type(obj)。"""
    return type(getattr(obj, "store", obj))


class MemoryMixin:
    def memory_enabled(self) -> bool:
        if not MEMORY_FEATURE:
            return False
        return self.store.get_setting("memory_enabled", "0") == "1"

    def memory_level(self, uid: str) -> str:
        return "high" if self.is_super_admin(uid) else "normal"

    def memory_scope_ok(self, mtype: str, uid: str) -> bool:
        if not self.memory_enabled():
            return False
        if mtype == "private":
            wl = self.store.users()
            return (not wl) or (str(uid) in [str(x) for x in wl])
        return True

    @staticmethod
    def memory_hit(content: str, text: str) -> bool:
        import re as _re
        clean = lambda x: _re.sub(r"[\s，。！？、,.!?：:；;\"'“”‘’（）()【】\[\]]+", "", str(x or ""))
        c, t = clean(content), clean(text)
        if not c or not t:
            return False
        if c in t:
            return True
        core = ChatStoreMixin.mem_core(content)
        if len(core) >= 2 and core in t:
            return True
        if len(c) <= 3:
            return False
        g2 = {c[i:i + 2] for i in range(len(c) - 1)}
        hits2 = [g for g in g2 if g in t]
        if len(hits2) >= 2:
            return True
        g3 = {c[i:i + 3] for i in range(len(c) - 2)}
        return any(g in t for g in g3)

    def memory_prompt(self, uid: str, level: str, query: str = "") -> str:
        if not self.memory_enabled():
            return ""
        key = "memory_super_inject" if level == "high" else "memory_normal_inject"
        inj = int(self.store.get_setting(key, "20" if level == "high" else "5") or (20 if level == "high" else 5))
        limit = 2000 if level == "high" else max(30, inj * 3)
        candidates = self.store.mem_by_owner(str(uid), None, limit, all_levels=True)
        # 过滤“机器人配置/后台/关键词”这类非人物记忆，避免 AI 把自己当助手聊设置
        noise = ("关键词", "触发词", "提示词", "后台", "部署", "API", "token", "观察者",
                 "省流模式", "FishPond", "机器人设置", "自动回复", "模型设置", "白名单")
        candidates = [c for c in candidates if not any(w in (c.get("content") or "") for w in noise)]
        if not candidates:
            return ""
        hits = [i for i in candidates if self.memory_hit(i.get("content", ""), query)]
        hits.sort(key=lambda i: (0 if i.get("level") == "high" else 1))
        items = hits[:max(1, inj)]
        if len(items) < max(1, inj):
            used_ids = {i["id"] for i in items}
            for c in candidates:
                if c["id"] in used_ids:
                    continue
                items.append(c)
                used_ids.add(c["id"])
                if len(items) >= max(1, inj):
                    break
        try:
            pending = getattr(self, "_pending_mem", {})
            pending[str(uid)] = items
            self._pending_mem = pending
        except Exception:
            pass
        lines = []
        for i in items:
            tag = "（永久）" if i.get("permanent") else ""
            lines.append("- " + i["content"] + tag)
        return "\n【你对这个人的记忆】\n" + "\n".join(lines)

    def commit_memory_usage(self, uid: str, user_text: str, reply: str):
        try:
            items = getattr(self, "_pending_mem", {}).pop(str(uid), [])
        except Exception:
            items = []
        if not items or not reply:
            return
        high_ids, normal_ids = [], []
        for i in items:
            content = i.get("content", "")
            if self.memory_hit(content, user_text) or self.memory_hit(content, reply):
                (high_ids if i.get("level") == "high" else normal_ids).append(i["id"])
        if not high_ids and not normal_ids:
            return
        try:
            self.store.mem_mark_used(high_ids, "high")
            self.store.mem_mark_used(normal_ids, "normal")
        except Exception:
            pass

    def schedule_memory_extract(self, uid: str, level: str, user_text: str, reply: str, mtype: str = "group", history=None):
        if not self.memory_enabled():
            return
        if not self.memory_scope_ok(mtype, uid):
            return
        every = max(1, int(self.store.get_setting("memory_extract_every", "3") or 3))
        cnt = getattr(self, "_mem_counter", {})
        cnt[str(uid)] = cnt.get(str(uid), 0) + 1
        self._mem_counter = cnt
        cue = any(w in (user_text or "") for w in (
            "我叫", "我是", "我喜欢", "我爱", "我最", "我讨厌", "我不喜欢", "我不吃",
            "我生日", "我养", "我住", "我对", "记住", "我叫作"))
        if not cue and cnt[str(uid)] % every != 0:
            return
        try:
            self.spawn(self.extract_memories(str(uid), level, user_text, reply, history), "extract_memories")
        except Exception:
            pass

    async def memory_cleanup_loop(self):
        if not MEMORY_FEATURE:
            return
        last = ""
        while True:
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                if last != today:
                    self.store.mem_cleanup(
                        super_days=int(self.store.get_setting("memory_super_days", "180") or 180),
                        normal_days=int(self.store.get_setting("memory_normal_days", "7") or 7),
                        super_max=int(self.store.get_setting("memory_super_limit", "500") or 500),
                        normal_max=int(self.store.get_setting("memory_normal_limit", "50") or 50),
                    )
                    last = today
                    log.info("记忆清理完成")
            except Exception as e:
                log.warning("记忆清理失败: %s", e)
            await asyncio.sleep(1800)

    async def api_memory_noise_preview(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        if acc.get("role") != "super":
            return aiohttp_web.json_response({"code": -1, "message": "没有权限"})
        total, items = self.store.mem_noise_preview()
        samples = [i["content"] for i in items[:10]]
        return aiohttp_web.json_response({"code": 0, "total": total, "noise": len(items), "samples": samples})

    async def api_memory_clean_noise(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        if acc.get("role") != "super":
            return aiohttp_web.json_response({"code": -1, "message": "没有权限"})
        n = self.store.mem_clean_noise()
        return aiohttp_web.json_response({"code": 0, "deleted": n})

    async def api_memory_ai_review(self, request):
        self.require_super(request)
        job = getattr(self, "_review_job", None)
        if job and job.get("status") == "running":
            return aiohttp_web.json_response({"code": 0, "job": job["id"], "total": job["total"], "running": True})
        rows = self.store.mem_list_all(None, None, None, 10_000_000)
        total = len(rows)
        if not total:
            return aiohttp_web.json_response({"code": 0, "ids": [], "items": [], "total": 0})
        self._review_job = {"id": secrets.token_hex(8), "total": total, "done": 0,
                            "status": "running", "ids": [], "items": [], "error": ""}
        self.spawn(self._review_worker(rows), "memory_review")
        return aiohttp_web.json_response({"code": 0, "job": self._review_job["id"], "total": total})

    async def api_memory_review_status(self, request):
        self.require_super(request)
        job = getattr(self, "_review_job", None)
        if not job:
            return aiohttp_web.json_response({"code": -1, "message": "没有正在进行的审核"})
        return aiohttp_web.json_response({
            "code": 0, "job": job["id"], "status": job["status"], "done": job["done"],
            "total": job["total"], "total_all": job["total"],
            "ids": job["ids"] if job["status"] == "done" else [],
            "items": job["items"] if job["status"] == "done" else [],
            "error": job["error"],
        })

    async def api_memory_delete_many(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        if acc.get("role") != "super":
            return aiohttp_web.json_response({"code": -1, "message": "没有权限"})
        data = await request.json()
        ids = data.get("ids") or []
        n = 0
        with self.store._conn() as c:
            for i in ids:
                try:
                    c.execute("DELETE FROM memories WHERE id=?", (int(i),))
                    n += 1
                except Exception:
                    pass
        return aiohttp_web.json_response({"code": 0, "deleted": n})

    async def api_memory_get(self, request):
        self.require_super(request)
        qq = (request.query.get("qq") or "").strip()
        kw = (request.query.get("kw") or "").strip()
        date = (request.query.get("date") or "").strip()
        items = self.store.mem_list_all(qq or None, kw or None, date or None, 10_000_000)
        for it in items:
            it["permanent"] = bool(it.get("permanent"))
            it["level_label"] = "超管" if it.get("level") == "high" else "普通"
        cfg = {
            "enabled": self.memory_enabled(),
            "super_days": int(self.store.get_setting("memory_super_days", "180") or 180),
            "normal_days": int(self.store.get_setting("memory_normal_days", "7") or 7),
            "super_limit": int(self.store.get_setting("memory_super_limit", "500") or 500),
            "normal_limit": int(self.store.get_setting("memory_normal_limit", "50") or 50),
            "super_inject": int(self.store.get_setting("memory_super_inject", "20") or 20),
            "normal_inject": int(self.store.get_setting("memory_normal_inject", "5") or 5),
            "extract_every": int(self.store.get_setting("memory_extract_every", "3") or 3),
            "review_model": self.store.get_setting("memory_review_model", "") or "",
        }
        return aiohttp_web.json_response({"code": 0, "items": items, "config": cfg})

    async def api_memory_add(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        if acc.get("role") != "super":
            return aiohttp_web.json_response({"code": -1, "message": "没有权限"})
        data = await request.json()
        qq = str(data.get("qq") or "").strip()
        content = str(data.get("content") or "").strip()
        level = "high" if data.get("level") == "high" else "normal"
        if not qq.isdigit() or not content:
            return aiohttp_web.json_response({"code": -1, "message": "QQ 和内容都不能为空"})
        if len(content) > 120:
            return aiohttp_web.json_response({"code": -1, "message": "内容太长（最多120字）"})
        self.store.mem_add(qq, content, level, "manual")
        return aiohttp_web.json_response({"code": 0})

    async def api_memory_update(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        if acc.get("role") != "super":
            return aiohttp_web.json_response({"code": -1, "message": "没有权限"})
        data = await request.json()
        mid = data.get("id")
        content = str(data.get("content") or "").strip()
        if not mid or not content:
            return aiohttp_web.json_response({"code": -1, "message": "参数错误"})
        self.store.mem_update(mid, content)
        return aiohttp_web.json_response({"code": 0})

    async def api_memory_delete(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        if acc.get("role") != "super":
            return aiohttp_web.json_response({"code": -1, "message": "没有权限"})
        data = await request.json()
        if data.get("qq"):
            self.store.mem_clear_owner(str(data.get("qq")))
        elif data.get("id"):
            self.store.mem_delete(data.get("id"))
        else:
            return aiohttp_web.json_response({"code": -1, "message": "参数错误"})
        return aiohttp_web.json_response({"code": 0})

    async def api_memory_config(self, request):
        self.require_super(request)
        acc = self.require_role(request, "user")
        if acc.get("role") != "super":
            return aiohttp_web.json_response({"code": -1, "message": "没有权限"})
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("memory_enabled", "1" if data.get("enabled") else "0")
        if "review_model" in data:
            self.store.set_setting("memory_review_model", str(data.get("review_model") or "").strip()[:64])
        for key, setting in (
            ("super_days", "memory_super_days"), ("normal_days", "memory_normal_days"),
            ("super_limit", "memory_super_limit"), ("normal_limit", "memory_normal_limit"),
            ("super_inject", "memory_super_inject"), ("normal_inject", "memory_normal_inject"),
            ("extract_every", "memory_extract_every"),
        ):
            if key in data:
                try:
                    self.store.set_setting(setting, str(max(1, int(data.get(key)))))
                except Exception:
                    pass
        return aiohttp_web.json_response({"code": 0})



class ChatStoreMixin:
    @staticmethod
    def mem_norm(text: str) -> str:
        import re as _re
        return _re.sub(r"[\s，。！？、,.!?：:；;\"'“”‘’（）()【】\[\]]+", "", str(text or "")).lower()

    def mem_dedupe(self):
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM memories ORDER BY permanent DESC, use_count DESC, id ASC").fetchall()]
            kept = []
            for r in rows:
                dup = None
                for k in kept:
                    if k["owner_qq"] != r["owner_qq"]:
                        continue
                    if self.mem_sim(r["content"], k["content"]):
                        dup = k
                        break
                if dup is None:
                    kept.append(r)
                    continue
                # 保留更有价值的一条
                keep, drop = dup, r
                if int(r.get("use_count") or 0) > int(dup.get("use_count") or 0):
                    keep, drop = r, dup
                if int(drop.get("permanent") or 0) and not int(keep.get("permanent") or 0):
                    keep, drop = drop, keep
                c.execute("DELETE FROM memories WHERE id=?", (drop["id"],))
                if keep is r:
                    kept = [x for x in kept if x["id"] != dup["id"]] + [r]

    @staticmethod
    def mem_core(text: str) -> str:
        t = ChatStoreMixin.mem_norm(text)
        for w in ("用户", "称呼为", "被称为", "称呼", "叫", "提到", "觉得", "喜欢", "习惯", "关注", "认为", "说", "的", "有点", "模式"):
            t = t.replace(w, "")
        return t

    @staticmethod
    def mem_sim(a: str, b: str) -> bool:
        na, nb = ChatStoreMixin.mem_core(a), ChatStoreMixin.mem_core(b)
        if not na or not nb:
            na, nb = ChatStoreMixin.mem_norm(a), ChatStoreMixin.mem_norm(b)
        if na == nb or (len(na) >= 2 and na in nb) or (len(nb) >= 2 and nb in na):
            return True
        if min(len(na), len(nb)) < 3:
            return False
        ga = {na[i:i + 2] for i in range(len(na) - 1)}
        gb = {nb[i:i + 2] for i in range(len(nb) - 1)}
        return len(ga & gb) / max(1, len(ga | gb)) >= 0.65

    @staticmethod
    def mem_is_noise(text: str) -> bool:
        t = str(text or "")
        return any(w in t for w in NOISE_WORDS)

    def mem_noise_preview(self):
        with self._conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM memories").fetchall()]
        items = [r for r in rows if self.mem_is_noise(r["content"])]
        return len(rows), items

    def mem_clean_noise(self) -> int:
        total, items = self.mem_noise_preview()
        if not items:
            return 0
        with self._conn() as c:
            for it in items:
                c.execute("DELETE FROM memories WHERE id=?", (it["id"],))
        return len(items)

    def mem_add(self, owner_qq, content, level="normal", source=""):
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO memories(owner_qq, level, content, source, created_at)"
                " VALUES(?,?,?,?,datetime('now','localtime'))",
                (str(owner_qq), level, content, source),
            )
            return int(cur.lastrowid)

    def mem_list_all(self, qq=None, keyword=None, date=None, limit=300):
        sql = "SELECT * FROM memories WHERE 1=1"
        args = []
        if qq:
            sql += " AND owner_qq=?"
            args.append(str(qq))
        if keyword:
            sql += " AND content LIKE ?"
            args.append(f"%{keyword}%")
        if date:
            sql += " AND date(created_at)=?"
            args.append(str(date))
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def mem_by_owner(self, owner_qq, level=None, limit=50, all_levels=False):
        with self._conn() as c:
            if level is None or all_levels:
                rows = c.execute(
                    "SELECT * FROM memories WHERE owner_qq=?"
                    " ORDER BY CASE WHEN level='high' THEN 0 ELSE 1 END,"
                    " COALESCE(last_used_at, created_at) DESC, use_count DESC, id DESC LIMIT ?",
                    (str(owner_qq), limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM memories WHERE owner_qq=? AND level=?"
                    " ORDER BY COALESCE(last_used_at, created_at) DESC, use_count DESC, id DESC LIMIT ?",
                    (str(owner_qq), level, limit),
                ).fetchall()
            return [dict(r) for r in rows]

    def mem_mark_used(self, ids, level):
        if not ids:
            return
        marks = ",".join("?" * len(ids))
        with self._conn() as c:
            c.execute(
                f"UPDATE memories SET use_count=use_count+1, last_used_at=datetime('now','localtime') WHERE id IN ({marks})",
                ids,
            )
            if level == "high":
                c.execute(
                    f"UPDATE memories SET permanent=1 WHERE id IN ({marks}) AND use_count>=3",
                    ids,
                )

    def mem_update(self, mid, content):
        with self._conn() as c:
            c.execute("UPDATE memories SET content=? WHERE id=?", (content, int(mid)))

    def mem_delete(self, mid):
        with self._conn() as c:
            c.execute("DELETE FROM memories WHERE id=?", (int(mid),))

    def mem_clear_owner(self, owner_qq):
        with self._conn() as c:
            c.execute("DELETE FROM memories WHERE owner_qq=?", (str(owner_qq),))

    def mem_cleanup(self, super_days=180, normal_days=7, super_max=500, normal_max=50):
        try:
            self.mem_dedupe()
        except Exception:
            pass
        now = time.time()
        with self._conn() as c:
            # 普通用户：按创建时间过期，且不做永久
            c.execute(
                "DELETE FROM memories WHERE level='normal' AND permanent=0"
                " AND created_at <= datetime('now','localtime', ?)",
                (f"-{int(normal_days)} days",),
            )
            # 超管：按最后使用/创建时间过期；3 次以上永久
            c.execute(
                "DELETE FROM memories WHERE level='high' AND permanent=0"
                " AND COALESCE(last_used_at, created_at) <= datetime('now','localtime', ?)",
                (f"-{int(super_days)} days",),
            )
            # 每人上限
            for lvl, cap in (("normal", normal_max), ("high", super_max)):
                cap = int(cap)
                owners = c.execute(
                    "SELECT owner_qq, COUNT(*) AS n FROM memories WHERE level=? AND permanent=0"
                    " GROUP BY owner_qq HAVING n > ?", (lvl, cap)
                ).fetchall()
                for row in owners:
                    c.execute(
                        "DELETE FROM memories WHERE id IN ("
                        " SELECT id FROM memories WHERE owner_qq=? AND level=? AND permanent=0"
                        " ORDER BY use_count DESC, id DESC LIMIT -1 OFFSET ?)",
                        (row["owner_qq"], lvl, cap),
                    )

    def list_personas(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT id, name, content, length(content) AS size FROM personas ORDER BY id").fetchall()]

    def get_persona(self, pid) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM personas WHERE id=?", (int(pid),)).fetchone()
            return dict(r) if r else None

    def save_persona(self, pid, name: str, content: str) -> int:
        now = time.time()
        with self._conn() as c:
            if pid:
                c.execute("UPDATE personas SET name=?, content=?, updated_at=? WHERE id=?", (name, content, now, int(pid)))
                return int(pid)
            cur = c.execute("INSERT INTO personas(name, content, created_at, updated_at) VALUES(?,?,?,?)", (name, content, now, now))
            return int(cur.lastrowid)

    def delete_persona(self, pid):
        with self._conn() as c:
            c.execute("DELETE FROM personas WHERE id=?", (int(pid),))

