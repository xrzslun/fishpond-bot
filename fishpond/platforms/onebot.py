"""平台层：OneBot/NapCat 连接、动作调用与消息发送。"""
import asyncio
from collections import deque
import json
import hashlib
import re
import secrets
import time
from pathlib import Path

import aiohttp

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


class OneBotMixin:
    async def napcat_credential(self) -> str | None:
        if self.napcat_cred and time.time() < self.napcat_cred_exp:
            return self.napcat_cred
        h = hashlib.sha256((self.napcat_token + ".napcat").encode()).hexdigest()
        try:
            async with self.http.post(
                f"{self.napcat_url}/api/auth/login",
                json={"hash": h},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None)
                if data.get("code") == 0:
                    self.napcat_cred = data["data"]["Credential"]
                    self.napcat_cred_exp = time.time() + 600
                    return self.napcat_cred
        except Exception as e:
            log.warning("NapCat 登录失败: %s", e)
        return None

    async def napcat_api(self, path: str, method: str = "POST", payload: dict | None = None) -> dict:
        for attempt in (1, 2):
            cred = await self.napcat_credential()
            if not cred:
                return {"code": -1, "message": "NapCat 连接失败"}
            try:
                async with self.http.request(
                    method,
                    f"{self.napcat_url}{path}",
                    headers={"Authorization": f"Bearer {cred}"},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json(content_type=None)
            except Exception as e:
                log.warning("NapCat 接口异常 %s: %s", path, e)
                return {"code": -1, "message": f"接口异常: {e}"}
            # NapCat 重启后旧凭据会失效，表现为 401 Unauthorized：清缓存重登一次
            msg = str(data.get("message") or "").lower()
            if attempt == 1 and ("unauthorized" in msg or data.get("code") == 401):
                self.napcat_cred = None
                self.napcat_cred_exp = 0
                continue
            return data
        return {"code": -1, "message": "NapCat 鉴权失败（已重试）"}

    async def napcat_login_info(self, force: bool = False) -> dict:
        now = time.time()
        cache = getattr(self, "_profile_cache", None)
        if cache and not force and now - cache[1] < 60:
            return cache[0]
        info = await self.napcat_api("/api/QQLogin/GetQQLoginInfo")
        if info.get("code") == 0 and info.get("data"):
            d = info["data"]
            uin = str(d.get("uin") or d.get("uid") or "").strip()
            out = {"online": bool(uin), "uin": uin or None, "nick": d.get("nick"), "stale": bool(d.get("online")) and not uin}
        else:
            out = {"online": False, "uin": None, "nick": None}
        self._profile_cache = (out, now)
        return out

    async def fresh_nick(self) -> str | None:
        now = time.time()
        cached = getattr(self, "_nick_self_cache", None)
        if cached and now - cached[1] < 30:
            return cached[0]
        try:
            res = await self.onebot_action("get_stranger_info", {"user_id": int(self.self_id)})
            if isinstance(res, dict) and res.get("status") == "ok":
                nick = str((res.get("data") or {}).get("nick") or "").strip()
                if nick:
                    self._nick_self_cache = (nick, now)
                    return nick
        except Exception:
            pass
        return None

    async def onebot_action(self, action: str, params: dict, timeout: float = 10.0):
        ws = getattr(self, "ws", None)
        if ws is None:
            return None
        return await self.onebot_call(ws, action, params, timeout)

    async def onebot_call(self, ws, action: str, params: dict, timeout: float = 6.0):
        echo = f"c{secrets.token_hex(6)}"
        fut = asyncio.get_running_loop().create_future()
        self.ws_futures[echo] = fut
        try:
            await ws.send_str(json.dumps({"action": action, "params": params, "echo": echo}))
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception as e:
            log.warning("OneBot 调用 %s 失败: %s", action, e)
            return None
        finally:
            self.ws_futures.pop(echo, None)

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
                    self.ws = ws
                    backoff = 3
                    self.connected = True
                    self.connected_at = time.time()
                    if self.offline_since:
                        mins = int((time.time() - self.offline_since) / 60)
                        self.offline_since = None
                        self._last_offline_note = 0.0
                        self._offline_notified_at = 0.0
                        log.info("已恢复连接（此前离线约 %s 分钟，期间重试 %s 次）", mins, self._disconnects)
                        self._disconnects = 0
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
                        if isinstance(ev, dict) and str(ev.get("echo") or "").startswith("snd"):
                            rc = ev.get("retcode")
                            if rc in (0, 1, None):
                                self._send_fail = None
                            else:
                                self._send_fail = {"at": time.time(), "code": rc,
                                                   "msg": str(ev.get("wording") or ev.get("message") or "")[:120]}
                                log.warning("发送失败（判定 QQ 可能已掉线）: code=%s %s", rc, self._send_fail["msg"])
                            continue
                        if isinstance(ev, dict) and ev.get("echo") in self.ws_futures:
                            fut = self.ws_futures.get(ev["echo"])
                            if fut and not fut.done():
                                fut.set_result(ev)
                            continue
                        if ev.get("post_type") == "meta_event" and ev.get("meta_event_type") == "lifecycle":
                            self.self_id = str(ev.get("self_id", "0"))
                            log.info("机器人 QQ 号: %s", self.self_id)
                        if ev.get("post_type") == "request":
                            if str(ev.get("request_type") or "") == "group":
                                self.spawn(self.handle_group_request(ev, ws), "group_request")
                            else:
                                self.spawn(self.handle_friend_request(ev, ws), "friend_request")
                            continue
                        if ev.get("post_type") == "notice":
                            log.info("收到 notice 事件: %s", json.dumps(ev, ensure_ascii=False)[:300])
                            if str(ev.get("notice_type") or "") in ("group_recall", "friend_recall"):
                                self.spawn(self.handle_recall(ev, ws), "handle_recall")
                            continue
                        if ev.get("post_type") != "message":
                            continue
                        self.last_event_at = time.time()
                        if ev.get("message_type") == "group" and ev.get("group_id"):
                            self.group_activity[str(ev.get("group_id"))] = time.time()
                        self.spawn(self.handle_message(ev, ws), "handle_message")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.connected = False
                self._disconnects += 1
                now = time.time()
                if not self.offline_since:
                    self.offline_since = now
                    self._last_offline_note = now
                    log.warning("连接异常: %s，%ss 后重连（开始离线）", e, backoff)
                elif now - self._last_offline_note >= 600:
                    self._last_offline_note = now
                    mins = int((now - self.offline_since) / 60)
                    log.warning("仍未连上（离线约 %s 分钟，累计重试 %s 次）: %s",
                                mins, self._disconnects, e)
            if self._stop:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def send(self, ws, mtype: str, ev: dict, text: str, record_convo: bool = True, at_qq=None):
        # 测试模式：本该发到群/别人的消息，全部改送超管，避免测试时打扰真实用户
        _tgt = self.test_redirect_target()
        if _tgt and str(ev.get("user_id") or "") != _tgt:
            _from = ("群" + str(ev.get("group_id"))) if mtype == "group" else ("用户" + str(ev.get("user_id") or ""))
            text = f"[测试转发·{_from}] {text}"
            mtype, at_qq = "private", None
            ev = {**ev, "user_id": _tgt}
        if at_qq and mtype == "group" and isinstance(text, str):
            # 正文里如果模型自己写了 @某人，会和系统 at 重复；而且可能用过期的旧昵称
            text = re.sub(r"^\s*@[^\s@，,：:]{1,20}[\s，,：:]*", "", text, count=1)
        try:
            if self.loop_guard_blocked(mtype, ev, str(text)):
                log.warning("发送被防循环拦截[%s]", mtype)
                return
        except Exception:
            pass
        log.info("发送文字[%s]: %s", mtype, str(text)[:60])
        self.remember_outgoing(text)
        if at_qq and mtype == "group":
            message = [{"type": "at", "data": {"qq": str(at_qq)}}, {"type": "text", "data": {"text": text}}]
        else:
            message = text
        params = {"message": message}
        if mtype == "group":
            params["message_type"] = "group"
            params["group_id"] = ev.get("group_id")
        else:
            params["message_type"] = "private"
            params["user_id"] = ev.get("user_id")
        try:
            await ws.send_str(json.dumps({"action": "send_msg", "params": params, "echo": f"snd{time.time()}"}))
            if mtype == "group":
                gid = str(ev.get("group_id"))
                uid = str(ev.get("user_id") or "")
                now = time.time()
                if uid and record_convo:
                    self.open_conversation(gid, uid)
                self.group_last_reply[gid] = now
                self.group_reply_times.setdefault(gid, deque()).append(now)
        except Exception as e:
            log.warning("发送失败: %s", e)


add(id="platform.onebot", name="OneBot 连接", entry="fishpond.platforms.onebot:OneBotMixin",
    routes=[], tables=[], settings=["onebot_*"], ui="后台整体",
    files="fishpond/platforms/onebot.py", status="active")
