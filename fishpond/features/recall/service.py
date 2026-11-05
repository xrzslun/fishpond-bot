"""撤回上报模块。"""
import asyncio
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

import aiohttp
from datetime import datetime
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


class RecallMixin:
    def recall_window_ok(self) -> bool:
        """撤回上报时间段，支持跨午夜（如 22:00-06:00）。"""
        try:
            start = (self.store.get_setting("recall_start", "00:00") or "00:00")[:5]
            end = (self.store.get_setting("recall_end", "23:59") or "23:59")[:5]
            now = datetime.now().strftime("%H:%M")
            if start == end:
                return True
            if start < end:
                return start <= now <= end
            return now >= start or now <= end
        except Exception:
            return True

    async def handle_recall(self, ev: dict, ws):
        """撤回通知：私聊转发超管；可选把撤回内容重新发回群。"""
        try:
            if str(ev.get("notice_type") or "") == "friend_recall":
                self.cancel_task_by_msg(str(ev.get("user_id") or ""), str(ev.get("message_id") or ""))
        except Exception:
            pass
        try:
            if self.store.get_setting("recall_enabled", "1") != "1":
                return
            if not self.recall_window_ok():
                return
            admins = self.super_admin_qqs()
            if not admins:
                return
            mid = str(ev.get("message_id") or "")
            cache = getattr(self, "_recall_msgs", {}) or {}
            hit = cache.pop(mid, None) if mid else None
            uid = str(ev.get("user_id") or (hit or {}).get("user") or "")
            nick = (hit or {}).get("nick") or ""
            text = (hit or {}).get("text") or "（未缓存：可能是图片/语音，或机器人重启前的消息）"
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            gid = str(ev.get("group_id") or (hit or {}).get("group") or "")
            src = f"群号{gid}" if gid else "私聊"
            body = (f"撤回信息：{text}\n"
                    f"撤回账号：{uid}" + (f"（{nick}）" if nick else "") + f"\n"
                    f"撤回时间：{ts}\n"
                    f"来自：{src}")
            if not uid:
                return
            imgs = [u for u in ((hit or {}).get("images") or []) if str(u).startswith("http")][:4]
            for qq in admins:
                await ws.send_str(json.dumps({"action": "send_msg", "params": {
                    "message": [{"type": "text", "data": {"text": body}}],
                    "message_type": "private", "user_id": str(qq)}}, ensure_ascii=False))
                for u in imgs:
                    await ws.send_str(json.dumps({"action": "send_msg", "params": {
                        "message": [{"type": "image", "data": {"file": u}}],
                        "message_type": "private", "user_id": str(qq)}}, ensure_ascii=False))
                    await asyncio.sleep(0.4)
            # 可选：把撤回内容重新发回原群
            if (gid and hit and self.store.get_setting("recall_echo_group", "0") == "1"
                    and (hit or {}).get("text")):
                echo = (f"【撤回】{nick or uid} 撤回了：{text}\n"
                        f"撤回账号：{uid}\n撤回时间：{ts}")
                await ws.send_str(json.dumps({"action": "send_msg", "params": {
                    "message": [{"type": "text", "data": {"text": echo}}],
                    "message_type": "group", "group_id": str(gid)}}, ensure_ascii=False))
                for u in imgs:
                    await asyncio.sleep(0.4)
                    await ws.send_str(json.dumps({"action": "send_msg", "params": {
                        "message": [{"type": "image", "data": {"file": u}}],
                        "message_type": "group", "group_id": str(gid)}}, ensure_ascii=False))
                log.info("撤回内容已回发群 %s", gid)
            log.info("撤回已上报超管: %s（%s）", uid, text[:40])
        except Exception as e:
            log.warning("撤回上报失败: %s", e)

    async def api_recall_config(self, request):
        self.require_super(request)
        if request.method == "GET":
            return aiohttp_web.json_response({"code": 0,
                "enabled": self.store.get_setting("recall_enabled", "1") == "1",
                "start": self.store.get_setting("recall_start", "00:00"),
                "end": self.store.get_setting("recall_end", "23:59"),
                "echo_group": self.store.get_setting("recall_echo_group", "0") == "1"})
        data = await request.json()
        self.store.set_setting("recall_enabled", "1" if data.get("enabled") else "0")
        st = str(data.get("start") or "00:00")[:5]
        en = str(data.get("end") or "23:59")[:5]
        self.store.set_setting("recall_start", st)
        self.store.set_setting("recall_end", en)
        self.store.set_setting("recall_echo_group", "1" if data.get("echo_group") else "0")
        return aiohttp_web.json_response({"code": 0, "start": st, "end": en})


add(id="recall.core", name="撤回上报",
    entry="fishpond.features.recall.service:recall_window_ok",
    routes=["/api/recall/*"] if "recall" == "voice" else [], tables=[],
    settings=["recall_*"], ui="机器人/超级管理员/撤回",
    files="fishpond/features/recall/service.py", status="active")
