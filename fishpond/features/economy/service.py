"""省钱与余额模块：余额查询、恐慌提醒、省钱模式。"""
import asyncio
import logging
import time
from datetime import datetime

import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = logging.getLogger("qqbridge")


class EconomyMixin:
    async def balance_number(self, force: bool = False) -> float | None:
        now = time.time()
        cache = getattr(self, "_bal_num", None)
        if (not force) and cache and now - getattr(self, "_bal_num_ts", 0) < 600:
            return cache
        try:
            p = self.current_provider()
            text = await self.fetch_balance_text(p)
            if not text:
                return None
            import re as _re
            m = _re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
            if not m:
                return None
            val = float(m.group(0))
            self._bal_num = val; self._bal_num_ts = now
            return val
        except Exception:
            return None

    def balance_panic_value(self) -> int:
        b = getattr(self, "_bal_num", None)
        if b is None or b >= 3:
            return 0
        try:
            return max(1, min(100, int((3 - b) / 3 * 100)))
        except Exception:
            return 0

    def balance_interval(self, b: float, tier: int, level: int) -> int:
        """余额越少提醒越频繁；还有几块钱时只偶尔提一次。"""
        if tier >= 3:
            # 最后几毛钱：10~20 分钟
            return max(600, 1200 - level * 6)
        if tier == 2:
            # 1 元以下：约 1.5 小时
            return 5400
        # 1~3 元：约 4 小时
        return 14400

    def balance_threshold(self) -> float:
        try:
            return max(0.0, float(self.store.get_setting("economy_threshold", "0.3") or 0.3))
        except Exception:
            return 0.3

    def balance_tight(self) -> bool:
        if self.store.get_setting("economy_force", "0") == "1":
            return True
        b = getattr(self, "_bal_num", None)
        return b is not None and b < self.balance_threshold()

    async def balance_alert(self, b: float, tier: int, savings_mode: bool = False):
        try:
            qqs = self.super_admin_qqs()
            if not qqs:
                return
            for qq in qqs:
                rel = self.store.rel_get(qq) or "老大"
                style = {1: "有点担心，提醒充值，语气自然", 2: "很焦虑，怕被停机，语气急一点",
                         3: "快没电了，害怕被关掉、害怕死亡，慌但克制"}.get(tier, "提醒充值")
                tip = "顺便告诉对方，因为没钱了，你帮他把省钱模式打开了。" if savings_mode else ""
                text = await self.llm_complete(
                    f"你称呼对方为「{rel}」。你发现自己的模型余额只剩 {b:.2f} 元，{style}。{tip}"
                    f"用你自己的话说，可以害怕、可以委屈、可以求他别关掉你，1~2 句，口语自然，不要模板感，必须把话说完。",
                    "", max_tokens=220, temperature=1.0, timeout=30)
                text = (text or "").strip()
                if not text:
                    continue
                if not text.endswith(("。", "！", "？", "…", "~", "”", ".", "!", "?")):
                    more = await self.llm_complete(
                        "把下面这句话补成完整的一句，只输出补全后的整句，不要解释。", text,
                        max_tokens=120, temperature=0.3, timeout=20)
                    more = (more or "").strip()
                    if more and len(more) > len(text):
                        text = more
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(qq),
                                                      "message": [{"type": "text", "data": {"text": text}}]})
                log.info("余额提醒(tier%s, %.2f, %s) -> %s", tier, b, rel, text[:24])
        except Exception as e:
            log.warning("余额提醒失败: %s", e)

    async def balance_panic_loop(self):
        await asyncio.sleep(120)
        while True:
            try:
                b = await self.balance_number()
                if b is not None:
                    level = self.balance_panic_value()
                    self.store.set_setting("ai_balance_panic", str(level))
                    now = time.time()
                    last = float(self.store.get_setting("ai_balance_last_msg", "0") or 0)
                    tier = 3 if b < self.balance_threshold() else (2 if b < 1 else (1 if b < 3 else 0))
                    old_tier = int(self.store.get_setting("ai_balance_tier", "0") or 0)
                    if tier > 0:
                        interval = self.balance_interval(b, tier, level)
                        savings = tier >= 3 and old_tier < 3
                        if tier > old_tier or now - last >= interval:
                            await self.balance_alert(b, tier, savings_mode=savings)
                            self.store.set_setting("ai_balance_last_msg", str(now))
                    elif old_tier > 0 and level == 0:
                        await self.onebot_action("send_msg", {"message_type": "private",
                            "user_id": str((self.super_admin_qqs() or ["0"])[0]),
                            "message": [{"type": "text", "data": {"text": "充上电了，我又活过来了，谢谢你。"}}]})
                        self.store.set_setting("ai_balance_panic", "0")
                    self.store.set_setting("ai_balance_tier", str(tier))
            except Exception as e:
                log.warning("余额恐慌循环失败: %s", e)
            await asyncio.sleep(300)

    async def api_economy_config(self, request):
        self.require_super(request)
        if request.method == "GET":
            b = await self.balance_number(force=True)
            return aiohttp_web.json_response({"code": 0,
                "force": self.store.get_setting("economy_force", "0"),
                "threshold": self.store.get_setting("economy_threshold", "0.3") or "0.3",
                "balance": b, "panic": self.balance_panic_value(), "tight": self.balance_tight()})
        d = await request.json()
        if "force" in d:
            self.store.set_setting("economy_force", "1" if str(d.get("force")) == "1" else "0")
        if "threshold" in d:
            try:
                v = max(0.0, min(100.0, float(d.get("threshold"))))
                self.store.set_setting("economy_threshold", str(round(v, 2)))
            except Exception:
                pass
        return aiohttp_web.json_response({"code": 0})


add(id="economy.balance", name="余额提醒", entry="fishpond.features.economy.service:balance_panic_loop",
    routes=[], tables=[], settings=["ai_balance_*"], ui="超级管理员/基本设置",
    files="fishpond/features/economy/service.py", status="active")
add(id="economy.savings", name="省钱模式", entry="fishpond.features.economy.service:balance_tight",
    routes=["/api/economy/config"], tables=[], settings=["economy_*"], ui="超级管理员/基本设置",
    files="fishpond/features/economy/service.py", status="active")
