#!/usr/bin/env python3
"""QQ <-> DeepSeek 桥接机器人

通过 OneBot 11 WebSocket 连接 NapCat，接收 QQ 消息，调用 DeepSeek API 回复。

特性：
- 群聊仅 @机器人 时触发（防止刷屏），私聊直接回复
- 每会话保留最近 N 条上下文（内存中，不落盘）
- 每会话限流，避免刷屏/API 消耗
- 忽略机器人自己和其他机器人账号的消息
- 自动重连 NapCat
"""
import asyncio
import json
import logging
import os
import time
from collections import deque
from pathlib import Path

import aiohttp
import yaml
from aiohttp import web as aiohttp_web

BASE = Path(__file__).resolve().parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("qqbridge")

LOG_RING = deque(maxlen=60)


class RingHandler(logging.Handler):
    def emit(self, record):
        try:
            LOG_RING.append(self.format(record))
        except Exception:
            pass


_ring = RingHandler()
_ring.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
log.addHandler(_ring)
logging.getLogger().addHandler(_ring)


def load_config() -> dict:
    cfg_path = BASE / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return cfg


class Bridge:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.onebot = cfg.get("onebot", {})
        self.ds = cfg.get("deepseek", {})
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.api_base = (self.ds.get("base_url") or "https://api.deepseek.com").rstrip("/")
        self.model = self.ds.get("model") or "deepseek-chat"
        self.system_prompt = self.ds.get("persona") or "你是QQ里的AI助手，回答简洁友好、说人话。"
        self.temperature = float(self.ds.get("temperature", 0.7))
        self.max_reply_chars = int(self.ds.get("max_reply_chars", 800))
        self.timeout = int(self.ds.get("timeout", 60))

        trig = cfg.get("trigger", {})
        self.group_at_only = bool(trig.get("group_at_only", True))

        ctx = cfg.get("context", {})
        self.max_messages = int(ctx.get("max_messages", 12))
        self.session_ttl = int(ctx.get("session_ttl_seconds", 1800))
        self.max_sessions = int(ctx.get("max_sessions", 200))

        self.min_interval = float(cfg.get("rate_limit_seconds", 3))
        self.sessions: dict[str, dict] = {}
        self.last_reply: dict[str, float] = {}
        self.self_id = "0"
        self.http: aiohttp.ClientSession | None = None
        self._stop = False
        self.connected = False
        self.connected_at: float | None = None
        self.started_at = time.time()
        self.last_event_at: float | None = None
        self.last_message: dict | None = None
        self.msg_count = 0
        self.reply_count = 0

    # ---------- 会话上下文 ----------
    def session(self, key: str) -> dict:
        now = time.time()
        s = self.sessions.get(key)
        if s is None or now - s["ts"] > self.session_ttl:
            s = {"history": deque(maxlen=self.max_messages), "ts": now, "lock": asyncio.Lock()}
            self.sessions[key] = s
            self._gc(now)
        s["ts"] = now
        return s

    def _gc(self, now: float):
        if len(self.sessions) <= self.max_sessions:
            return
        dead = [k for k, v in self.sessions.items() if now - v["ts"] > self.session_ttl]
        for k in dead[: len(self.sessions) - self.max_sessions]:
            self.sessions.pop(k, None)

    # ---------- DeepSeek ----------
    async def ask_deepseek(self, session: dict, user_text: str) -> str:
        if not self.api_key:
            return "（未配置 DeepSeek API Key，请联系管理员）"
        messages = [{"role": "system", "content": self.system_prompt}]
        messages += list(session["history"])
        messages.append({"role": "user", "content": user_text})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            async with self.http.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    err = (data or {}).get("error", {}).get("message", str(resp.status))
                    log.warning("DeepSeek API 错误: %s", err)
                    return "（AI 服务暂时不可用，稍后再试）"
                text = data["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning("DeepSeek 调用异常: %s", e)
            return "（AI 服务暂时不可用，稍后再试）"
        text = text.strip()
        if len(text) > self.max_reply_chars:
            text = text[: self.max_reply_chars] + "…"
        session["history"].append({"role": "user", "content": user_text})
        session["history"].append({"role": "assistant", "content": text})
        return text

    # ---------- OneBot ----------
    async def ws_loop(self):
        url = self.onebot.get("ws_url") or "ws://127.0.0.1:3001"
        headers = {}
        token = (self.onebot.get("access_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        backoff = 3
        while not self._stop:
            try:
                log.info("连接 NapCat: %s", url)
                async with self.http.ws_connect(url, headers=headers, heartbeat=30) as ws:
                    backoff = 3
                    self.connected = True
                    self.connected_at = time.time()
                    log.info("已连接，开始接收消息")
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                            continue
                        try:
                            ev = json.loads(msg.data)
                        except json.JSONDecodeError:
                            continue
                        if ev.get("post_type") == "meta_event" and ev.get("meta_event_type") == "lifecycle":
                            self.self_id = str(ev.get("self_id", "0"))
                            log.info("机器人 QQ 号: %s", self.self_id)
                        if ev.get("post_type") != "message":
                            continue
                        self.last_event_at = time.time()
                        asyncio.create_task(self.handle_message(ev, ws))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.connected = False
                log.warning("连接异常: %s，%ss 后重连", e, backoff)
            if self._stop:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def handle_message(self, ev: dict, ws):
        mtype = ev.get("message_type")
        if mtype not in ("group", "private"):
            return
        self_id = str(ev.get("self_id") or self.self_id)
        self.self_id = self_id
        user_id = str(ev.get("user_id", ""))
        if user_id == self_id:
            return
        sender = ev.get("sender") or {}
        if sender.get("bot"):
            return

        # 解析文本与 @ 情况
        texts, at_me = [], False
        for seg in ev.get("message") or []:
            st, sd = seg.get("type"), seg.get("data") or {}
            if st == "text":
                texts.append(str(sd.get("text", "")))
            elif st == "at":
                if str(sd.get("qq")) == self_id:
                    at_me = True
        user_text = "".join(texts).strip()
        if not user_text:
            return

        if mtype == "group":
            if self.group_at_only and not at_me:
                return
            key = f"g{ev.get('group_id')}"
            gid = ev.get("group_id")
        else:
            key = f"p{user_id}"

        # 限流
        now = time.time()
        if now - self.last_reply.get(key, 0) < self.min_interval:
            return
        self.last_reply[key] = now

        self.msg_count += 1
        self.last_message = {
            "time": time.strftime("%H:%M:%S"),
            "session": key,
            "user": sender.get("nickname", user_id),
            "text": user_text[:100],
        }
        session = self.session(key)
        if session["lock"].locked():
            return
        async with session["lock"]:
            log.info("收到[%s] %s: %s", key, sender.get("nickname", user_id), user_text[:80])
            reply = await self.ask_deepseek(session, user_text)
            self.reply_count += 1
            await self.send(ws, mtype, ev, reply)

    async def send(self, ws, mtype: str, ev: dict, text: str):
        params = {"message": text}
        if mtype == "group":
            params["message_type"] = "group"
            params["group_id"] = ev.get("group_id")
        else:
            params["message_type"] = "private"
            params["user_id"] = ev.get("user_id")
        try:
            await ws.send_text(json.dumps({"action": "send_msg", "params": params, "echo": f"r{time.time()}"}))
        except Exception as e:
            log.warning("发送失败: %s", e)

    async def status_app(self):
        app = aiohttp_web.Application()

        async def page(request):
            def fmt(ts):
                return time.strftime("%m-%d %H:%M:%S", time.localtime(ts)) if ts else "-"

            state = "在线" if self.connected else "离线"
            state_cls = "ok" if self.connected else "bad"
            last = self.last_message or {}
            logs_html = "".join(
                '<div>' + (line.replace("<", "&lt;")) + "</div>" for line in list(LOG_RING)[-25:]
            ) or "<div>(暂无日志)</div>"
            html = f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>QQ DeepSeek Bot</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#0f1115;color:#e6e6e6;padding:18px;margin:0;font-size:15px}}
h1{{font-size:18px;margin:0 0 14px}}
.card{{background:#181b22;border-radius:12px;padding:14px 16px;margin-bottom:12px}}
.row{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #242833}}
.row:last-child{{border-bottom:none}}
.k{{color:#8b93a5}}
.ok{{color:#4ade80;font-weight:600}}
.bad{{color:#f87171;font-weight:600}}
pre{{background:#0b0d11;border-radius:10px;padding:10px;overflow:auto;font-size:11px;line-height:1.5;color:#9aa4b8;margin:0}}
h2{{font-size:14px;color:#8b93a5;margin:0 0 8px}}
</style>
<h1>QQ DeepSeek Bot 状态</h1>
<div class="card">
<div class="row"><span class="k">桥接连接</span><span class="{state_cls}">{state}</span></div>
<div class="row"><span class="k">机器人 QQ</span><span>{self.self_id or '-'}</span></div>
<div class="row"><span class="k">模型</span><span>{self.model}</span></div>
<div class="row"><span class="k">API Key</span><span>{"已配置" if self.api_key else "未配置"}</span></div>
<div class="row"><span class="k">运行时长</span><span>{int(time.time()-self.started_at)} 秒</span></div>
<div class="row"><span class="k">收 / 发消息</span><span>{self.msg_count} / {self.reply_count}</span></div>
<div class="row"><span class="k">最近消息</span><span>{last.get("time","-")} {last.get("user","")}: {(last.get("text","") or "")[:12]}</span></div>
</div>
<div class="card"><h2>最近日志</h2><pre>{logs_html}</pre></div>
<p style="color:#555;font-size:12px">每 10 秒自动刷新 · 日志全文 <a href="/logs" style="color:#60a5fa">/logs</a></p>"""
            return aiohttp_web.Response(text=html, content_type="text/html", charset="utf-8")

        async def status_json(request):
            return aiohttp_web.json_response(
                {
                    "ok": True,
                    "bridge_connected": self.connected,
                    "connected_at": (
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.connected_at))
                        if self.connected_at
                        else None
                    ),
                    "uptime_seconds": int(time.time() - self.started_at),
                    "bot_qq": self.self_id,
                    "model": self.model,
                    "api_key_configured": bool(self.api_key),
                    "last_event_time": (
                        time.strftime("%H:%M:%S", time.localtime(self.last_event_at))
                        if self.last_event_at
                        else None
                    ),
                    "last_message": self.last_message,
                    "messages_received": self.msg_count,
                    "replies_sent": self.reply_count,
                    "sessions": len(self.sessions),
                },
                dumps=lambda o: json.dumps(o, ensure_ascii=False, indent=2),
            )

        async def logs(request):
            return aiohttp_web.Response(
                text="\n".join(LOG_RING) or "(no logs yet)",
                content_type="text/plain",
                charset="utf-8",
            )

        app.router.add_get("/", page)
        app.router.add_get("/status", status_json)
        app.router.add_get("/logs", logs)
        runner = aiohttp_web.AppRunner(app)
        await runner.setup()
        site = aiohttp_web.TCPSite(runner, "127.0.0.1", 8099)
        await site.start()
        log.info("状态页: http://127.0.0.1:8099/")

    async def run(self):
        if not self.api_key:
            log.warning("未设置 DEEPSEEK_API_KEY，机器人会回复提示语")
        self.http = aiohttp.ClientSession()
        status_task = asyncio.create_task(self.status_app())
        try:
            await self.ws_loop()
        finally:
            status_task.cancel()
            await self.http.close()


def main():
    cfg = load_config()
    bridge = Bridge(cfg)
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
