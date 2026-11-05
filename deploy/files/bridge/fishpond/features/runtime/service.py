"""运行模块：启动循环、备份、统计、后台辅助接口。"""
import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.core.config import SCRIPT_HUB
from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


def _base_dir():
    root = Path(__file__).resolve().parents[3]
    if (root / "bot.py").is_file():
        return root
    alt = root / "bridge"
    return alt if alt.is_dir() else root


BASE = _base_dir()
STICKER_DIR = BASE / "stickers"
END_PHRASES = ['没你事了', '没你事', '滚吧', '滚蛋', '闭嘴', '别说了', '别接话', '不用你了', '不需要你', '一边去', '走开', '退下', '散了吧', '你可以走了', '别理我', '歇着吧', '没你说话的份']
BORED_LINES = ['安静得有点过分了，你们说全世界最安静的地方是哪儿？', '突然想问问，你们午饭都吃啥了？我还在纠结', '话说鱼会口渴吗？在线等，不着急', '有没有人跟我一样，明明很困但就是不想睡', '我怀疑这个群被施了静音咒，有人能解开吗', '如果发呆能赚钱，我现在应该已经财富自由了', '刚看到一只猫在晒太阳，你们说它脑子里在想什么', '突然好奇：你们手机里最舍不得删的一张照片是什么', '好无聊啊，有没有人来讲个冷笑话，我先讲：企鹅为什么不怕冷', '问一下，你们觉得世界上先有鸡还是先有蛋（认真脸）', '这个点大家都在忙什么？摸鱼的扣个 1', '天塌下来也先聊两句再跑啊，你们说是不是', '刚才发呆十分钟，感觉自己像个加载中的网页', '有人在线吗，出来吱一声，让我知道我没对着空气说话', '突然想到，如果今天不用上班，你们最想去哪儿']


class RuntimeMixin:
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

        vis = cfg.get("vision", {})
        self.vision_enabled = bool(vis.get("enabled", True))
        self.max_images = int(vis.get("max_images", 2))
        self.max_side = int(vis.get("max_side", 1024))
        self.max_bytes = int(vis.get("max_bytes", 6_000_000))

        trig = cfg.get("trigger", {})
        self.group_at_only = bool(trig.get("group_at_only", True))
        self.keywords = [str(k) for k in (trig.get("keywords") or []) if str(k).strip()]

        ctx = cfg.get("context", {})
        self.max_messages = int(ctx.get("max_messages", 12))
        self.session_ttl = int(ctx.get("session_ttl_seconds", 1800))
        self.max_sessions = int(ctx.get("max_sessions", 200))

        self.min_interval = float(cfg.get("rate_limit_seconds", 3))

        admin_cfg = cfg.get("admin", {})
        self.store = Store(BASE / admin_cfg.get("db_path", "data.db"))
        self.keywords_seed = [str(k) for k in (trig.get("keywords") or []) if str(k).strip()]
        if not self.store.end_phrases():
            for phrase in END_PHRASES:
                self.store.add_end_phrase(phrase)
        if not self.store.bored_lines():
            for line in BORED_LINES:
                self.store.add_bored_line(line)
        seed_prefix = {str(k): str(v) for k, v in (cfg.get("reply_prefix") or {}).items()}
        if not self.store.prefix_map():
            for qq, pref in seed_prefix.items():
                self.store.set_prefix(qq, pref)
        if not self.store.keywords():
            for w in self.keywords_seed:
                self.store.add_keyword(w)
        self.ensure_default_admin(admin_cfg)

        STICKER_DIR.mkdir(parents=True, exist_ok=True)
        self.napcat_cfg = cfg.get("napcat", {})
        self.napcat_url = (self.napcat_cfg.get("webui_url") or "http://127.0.0.1:6099").rstrip("/")
        self.napcat_token = self.napcat_cfg.get("webui_token", "")
        self.napcat_cred = None
        self.napcat_cred_exp = 0
        self.qr_cooldown = float(self.napcat_cfg.get("qr_cooldown_seconds", 60))
        self.qr_valid_seconds = float(self.napcat_cfg.get("qr_valid_seconds", 100))
        self.last_qr_ts = 0.0
        self.group_activity: dict[str, float] = {}
        self.active_convos: dict[tuple[str, str], float] = {}
        self.group_reply_times: dict[str, deque] = {}
        self.group_last_reply: dict[str, float] = {}
        import shutil as _shutil
        self._ffmpeg_ok = bool(_shutil.which("ffmpeg"))
        log.info("启动版本 %s | ffmpeg=%s | 语音引擎=%s", self.app_version(),
                 "ok" if self._ffmpeg_ok else "missing",
                 self.store.get_setting("voice_engine", "tts"))
        if not self._ffmpeg_ok:
            asyncio.get_running_loop().create_task(self.install_ffmpeg())
        if not self._ffmpeg_ok:
            log.warning("未安装 ffmpeg：语音将使用纯 Python 去提示音（无法转 mp3）")
        if not (self.store.get_setting("game_dist_token", "") or "").strip():
            self.store.set_setting("game_dist_token", secrets.token_hex(16))
        ctx_cfg = cfg.get("context", {})
        self.continue_seconds = int(ctx_cfg.get("group_continue_seconds", 180))
        self.group_max_replies = int(ctx_cfg.get("group_max_replies_per_minute", 6))
        self.max_active_users = int(ctx_cfg.get("group_max_active_users", 3))
        self.cleanup_interval = max(180, int(ctx_cfg.get("cleanup_interval_seconds", 180)))
        self.webui_path = str((cfg.get("webui") or {}).get("path") or "/")
        self.last_super_at = 0.0
        self._sent_guard = deque(maxlen=300)
        self._loop_guard: dict[str, float] = {}
        self._msg_rate: dict[str, list] = {}
        self._suspect: dict[str, float] = {}
        self.ws_futures: dict[str, asyncio.Future] = {}
        self._bg_tasks: set = set()
        self._nick_cache: dict[tuple, tuple] = {}
        self._update_cache: tuple[dict, float] | None = None
        self.voice_enabled = False
        self.last_bored_send: dict[str, float] = {}
        self.bored_next: dict[str, int] = {}
        self.ws = None

        self.sessions: dict[str, dict] = {}
        self.last_reply: dict[str, float] = {}
        self.self_id = "0"
        self.http: aiohttp.ClientSession | None = None
        self._stop = False
        self.connected = False
        self.connected_at: float | None = None
        # 掉线跟踪（用于日志降噪 + 后台横幅 + 外部推送）
        self.offline_since: float | None = None
        self._last_offline_note = 0.0
        self._offline_notified_at = 0.0
        self._disconnects = 0
        self.started_at = time.time()
        self.last_event_at: float | None = None
        self.last_message: dict | None = None
        self.msg_count = 0
        self.reply_count = 0
        self.auth_sessions: dict[str, dict] = {}
        self._send_fail = None
        self.messenger = ProactiveMessenger(self)

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

    @staticmethod
    def norm_qq(value) -> str:
        text = str(value or "").strip()
        # 全角数字 -> 半角，去掉常见空白/分隔符
        text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        text = text.replace(" ", "").replace("\u3000", "")
        return text

    def super_admin_qqs(self) -> list[str]:
        raw = self.store.get_setting("super_admin_qqs", "") or ""
        out = []
        for part in raw.replace("，", ",").split(","):
            q = self.norm_qq(part)
            if q and q.isdigit() and q not in out:
                out.append(q)
        return out

    async def stats_heartbeat(self):
        """每 10 分钟上报一次心跳，证明这台部署还活着。"""
        await asyncio.sleep(8)
        while True:
            ok = False
            try:
                if self.store.get_setting("stats_enabled", "1") != "1":
                    await asyncio.sleep(3600)
                    continue
                iid = self.store.get_setting("install_id", "")
                if not iid:
                    iid = secrets.token_hex(12)
                    self.store.set_setting("install_id", iid)
                import platform
                payload = {"install_id": iid, "version": self.app_version(), "os": platform.platform()[:60]}
                async with self.http.post("https://xrzs.cloud/updates/checkin", json=payload,
                                          timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    await resp.read()
                ok = True
            except Exception:
                pass
            try:
                interval = int(self.store.get_setting("stats_heartbeat_seconds", "600"))
            except Exception:
                interval = 600
            interval = max(60, min(86400, interval))
            await asyncio.sleep(interval if ok else 120)

    def is_super_admin(self, user_id: str) -> bool:
        uid = self.norm_qq(user_id)
        return bool(uid) and uid in self.super_admin_qqs()

    def spawn(self, coro, label: str = ""):
        async def runner():
            try:
                await coro
            except Exception:
                log.exception("后台任务失败: %s", label or "unknown")
        task = asyncio.create_task(runner())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    @staticmethod
    def now_phrase():
        now = datetime.now()
        h = now.hour
        period = ("凌晨" if h < 5 else "早上" if h < 9 else "上午" if h < 12
                  else "中午" if h < 14 else "下午" if h < 18 else "晚上")
        return f"{period} {now.hour}:{now.minute:02d}", now.strftime("%Y年%m月%d日")

    async def notify_super(self, ws, text: str):
        for qq in self.super_admin_qqs():
            try:
                log.info("通知超管[%s]: %s", qq, str(text)[:60])
                await self.onebot_call(ws, "send_private_msg", {"user_id": int(qq), "message": text})
            except Exception as e:
                log.warning("私聊超管 %s 失败: %s", qq, e)

    @staticmethod
    def leading_beep_seconds(pcm: bytes, sr: int = 24000) -> float:
        """裁掉音频开头「人声之前」的一切杂音（提示音/滴声/水印音），返回应裁掉的秒数。

        做法：逐 20ms 扫描，把「稳定纯音」（窄带占比高 + 峰值和音量都很稳）和静音当作前缀，
        遇到**连续 2 个有能量、且不像稳定纯音**的窗口，就认为人声开始了，裁到它前面 0.12 秒。
        这样不依赖提示音的具体频率，500Hz、900Hz、2000Hz 都能处理；首字仍留 0.12s 保护。
        """
        try:
            import numpy as np
        except Exception:
            return 0.0
        if not pcm:
            return 0.0
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        win = int(sr * 0.02)
        limit = min(len(x), int(sr * 2.5))
        last_tone = -1
        prev_peak, prev_rms = 0.0, 0.0
        speech_at = -1
        run = 0
        i = 0
        idx = 0
        while i + win <= limit:
            c = x[i:i + win]
            rms = float(np.sqrt(np.mean(c * c)))
            peak, band = 0.0, 0.0
            if rms > 0.008:
                spec = np.abs(np.fft.rfft(c * np.hanning(len(c))))
                freqs = np.fft.rfftfreq(len(c), 1.0 / sr)
                if spec.size:
                    pk = int(np.argmax(spec))
                    peak = float(freqs[pk])
                    lo, hi = max(0, pk - 8), min(len(spec), pk + 9)
                    band = float(np.sum(spec[lo:hi])) / (float(np.sum(spec)) + 1e-9)
            if rms <= 0.008:
                run = 0
            else:
                stable = (band > 0.6 and
                          (prev_peak == 0.0 or (abs(peak - prev_peak) < 20 and abs(rms - prev_rms) < max(0.004, prev_rms * 0.2))))
                if stable:
                    last_tone = idx
                    prev_peak, prev_rms = peak, rms
                    run = 0
                else:
                    run += 1
                    if run >= 2:
                        speech_at = idx - 1
                        break
                    prev_peak, prev_rms = 0.0, 0.0
            i += win
            idx += 1
        dur = len(x) / sr
        if speech_at > 0:
            cut = speech_at * win / sr - 0.12
            if 0.1 <= cut <= 2.2 and (dur - cut) >= 0.6:
                return round(cut, 2)
            return 0.0
        if last_tone >= 3:
            cut = (last_tone + 1) * win / sr - 0.05
            if 0.15 <= cut <= 2.2 and (dur - cut) >= 0.8:
                return round(cut, 2)
            return 0.0
        log.info("未检测到开头提示音")
        return 0.0

    def backup_db(self, keep: int = 7) -> str:
        try:
            bdir = BASE / "backups"
            bdir.mkdir(parents=True, exist_ok=True)
            day = time.strftime("%Y%m%d")
            if list(bdir.glob(f"data-{day}-*.db")):
                return ""
            name = "data-" + time.strftime("%Y%m%d-%H%M%S") + ".db"
            target = bdir / name
            src = sqlite3.connect(self.store.path)
            dst = sqlite3.connect(target)
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            files = sorted(bdir.glob("data-*.db"))
            for old in files[:-keep]:
                try:
                    old.unlink()
                except Exception:
                    pass
            log.info("数据库备份完成: %s", target)
            return str(target)
        except Exception as e:
            log.warning("数据库备份失败: %s", e)
            return ""

    async def backup_loop(self):
        await asyncio.sleep(30)
        while not self._stop:
            self.backup_db(7)
            await asyncio.sleep(24 * 3600)

    def cleanup_disk(self, keep_days: int = 7):
        """清理旧备份、旧快照和旧 .bak，避免磁盘无限增长。"""
        import shutil
        now = time.time()
        removed = 0
        try:
            for f in BASE.glob("bot.py.bak.*"):
                try:
                    if now - f.stat().st_mtime > keep_days * 86400:
                        f.unlink()
                        removed += 1
                except Exception:
                    pass
            snap_root = BASE / "snapshots"
            if snap_root.is_dir():
                snaps = sorted([d for d in snap_root.iterdir()
                                if d.is_dir() and (d / "meta.json").is_file()], key=lambda p: p.name)
                for d in snaps[:-3]:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            bak_root = BASE / "backups"
            if bak_root.is_dir():
                for f in bak_root.glob("data-*.db"):
                    try:
                        if now - f.stat().st_mtime > keep_days * 2 * 86400:
                            f.unlink()
                            removed += 1
                    except Exception:
                        pass
        except Exception as e:
            log.warning("磁盘清理失败: %s", e)
        if removed:
            log.info("磁盘清理: 删除 %s 个旧文件/目录", removed)

    async def cleanup_loop(self):
        while not self._stop:
            await asyncio.sleep(self.cleanup_interval)
            try:
                today = time.strftime("%Y-%m-%d")
                if getattr(self, "_wake_clean_day", "") != today:
                    self.store.wake_cleanup(30)
                    self.store.wake_reply_cleanup(7)
                    self._wake_clean_day = today
                    self.cleanup_disk()
            except Exception:
                pass
            now = time.time()
            expired = [k for k, v in self.active_convos.items() if v <= now]
            for k in expired:
                self.active_convos.pop(k, None)
            if expired:
                log.info("临时接话数据清理: 删除 %d 条过期记录", len(expired))

    async def install_ffmpeg(self) -> bool:
        """缺 ffmpeg 时尝试自动安装（仅在有免密 sudo 时，失败不报错）。"""
        import shutil as _sh
        import subprocess as _sp
        if _sh.which("ffmpeg"):
            self._ffmpeg_ok = True
            return True
        try:
            check = _sp.run(["sudo", "-n", "true"], capture_output=True, timeout=5)
            if check.returncode != 0:
                log.warning("缺少 ffmpeg，且没有免密 sudo；请手动执行: sudo apt-get install -y ffmpeg")
                return False
            for cmd in (["sudo", "-n", "apt-get", "install", "-y", "-qq", "ffmpeg"],
                        ["sudo", "-n", "dnf", "install", "-y", "ffmpeg"],
                        ["sudo", "-n", "apk", "add", "--no-cache", "ffmpeg"]):
                try:
                    r = _sp.run(cmd, capture_output=True, timeout=240)
                except Exception:
                    continue
                if r.returncode == 0 and _sh.which("ffmpeg"):
                    self._ffmpeg_ok = True
                    log.info("已自动安装 ffmpeg（%s）", cmd[2])
                    return True
        except Exception as e:
            log.warning("自动安装 ffmpeg 失败: %s", e)
        log.warning("ffmpeg 仍不可用，将使用纯 Python 去提示音（无法转 mp3）")
        return False

    # ---------- 运维观测（健康/错误/诊断） ----------
    def error_bucket(self):
        b = getattr(self, "_err_bucket", None)
        if b is None:
            b = {}
            self._err_bucket = b
        return b

    def install_error_capture(self):
        import logging
        import traceback

        bucket = self.error_bucket()

        class _Handler(logging.Handler):
            def emit(self, record):
                if record.levelno < logging.ERROR:
                    return
                try:
                    msg = record.getMessage()[:180]
                    key = f"{record.name}: {msg}"
                    now = time.time()
                    it = bucket.get(key)
                    if it is None:
                        it = {"count": 0, "first": now, "last": now, "sample": ""}
                        bucket[key] = it
                    it["count"] += 1
                    it["last"] = now
                    if not it["sample"] and record.exc_info:
                        it["sample"] = "".join(traceback.format_exception(*record.exc_info))[-1200:]
                except Exception:
                    pass

        h = _Handler()
        h.setLevel(logging.ERROR)
        logging.getLogger().addHandler(h)

    def db_report(self):
        expected = ["settings", "memories", "admins", "providers", "stickers", "group_panel",
                    "group_cfg", "bili_notes", "emotion", "panic", "persona_traits", "relationships",
                    "affect_log", "scripts", "runs", "join_verify", "group_blacklist"]
        out = {"ok": True, "missing": [], "tables": 0, "quick_check": ""}
        try:
            with self.store._conn() as c:
                rows = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                out["tables"] = len(rows)
                out["missing"] = [t for t in expected if t not in rows]
                try:
                    out["quick_check"] = str(c.execute("PRAGMA quick_check").fetchone()[0])
                except Exception:
                    out["quick_check"] = "unknown"
        except Exception as exc:
            out["ok"] = False
            out["error"] = str(exc)[:200]
        if out["missing"] or out["quick_check"] not in ("ok", "unknown", ""):
            out["ok"] = False
        return out

    def health_snapshot(self):
        import shutil
        issues = []
        try:
            du = shutil.disk_usage(str(BASE))
            free_gb = du.free / (1024 ** 3)
        except Exception:
            free_gb = -1
        if 0 <= free_gb < 1:
            issues.append(f"磁盘剩余 {free_gb:.2f}GB")
        mem_avail = -1
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        mem_avail = int(line.split()[1]) / 1024
                        break
        except Exception:
            pass
        if 0 <= mem_avail < 200:
            issues.append(f"可用内存 {mem_avail:.0f}MB")
        db = self.db_report()
        if not db["ok"]:
            issues.append("数据库异常" + (f"（缺表 {','.join(db['missing'])}）" if db["missing"] else ""))
        if not self.connected:
            issues.append("NapCat 未连接")
        return {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "disk_free_gb": round(free_gb, 2),
                "mem_available_mb": round(mem_avail, 0), "napcat": self.connected,
                "db": db, "issues": issues}

    async def health_loop(self):
        await asyncio.sleep(120)
        while True:
            try:
                snap = self.health_snapshot()
                if snap["issues"]:
                    sent = getattr(self, "_health_sent", None)
                    if sent is None:
                        sent = {}
                        self._health_sent = sent
                    now = time.time()
                    fresh = [i for i in snap["issues"] if now - sent.get(i, 0) > 3600]
                    if fresh:
                        for i in fresh:
                            sent[i] = now
                        text = "⚠️ 运行异常\n" + "\n".join(fresh)
                        for qq in self.super_admin_qqs():
                            try:
                                await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(qq),
                                                                      "message": [{"type": "text", "data": {"text": text}}]})
                            except Exception:
                                pass
                        log.warning("健康巡检异常: %s", "; ".join(fresh))
                # 更新后健康确认：启动稳定 3 分钟后清除 pending 标记
                pending = BASE / ".update_pending"
                if pending.is_file():
                    try:
                        if time.time() - pending.stat().st_mtime > 180 and not snap["issues"]:
                            pending.unlink(missing_ok=True)
                    except Exception:
                        pass
            except Exception as e:
                log.warning("健康巡检失败: %s", e)
            await asyncio.sleep(600)

    async def api_health(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({"code": 0, **self.health_snapshot()})

    async def api_errors(self, request):
        self.require_super(request)
        items = sorted(self.error_bucket().items(), key=lambda kv: -kv[1]["count"])[:20]
        out = [{"key": k, "count": v["count"],
                "first": time.strftime("%m-%d %H:%M", time.localtime(v["first"])),
                "last": time.strftime("%m-%d %H:%M", time.localtime(v["last"])),
                "sample": v["sample"][-500:]} for k, v in items]
        return aiohttp_web.json_response({"code": 0, "items": out})

    async def api_diag_pack(self, request):
        self.require_super(request)
        import io
        import json as _json
        import zipfile
        buf = io.BytesIO()
        safe_keys = []
        try:
            with self.store._conn() as c:
                for k, v in c.execute("SELECT key,value FROM settings"):
                    sv = str(v or "")
                    low = k.lower()
                    if any(x in low for x in ("key", "token", "pass", "secret", "cookie")):
                        sv = "***"
                    safe_keys.append([k, sv[:200]])
                tables = {r[0]: None for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                counts = {}
                for t in list(tables)[:60]:
                    try:
                        counts[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    except Exception:
                        pass
        except Exception as e:
            safe_keys = [["error", str(e)]]
            counts = {}
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("version.txt", self.app_version())
            zf.writestr("health.json", _json.dumps(self.health_snapshot(), ensure_ascii=False, indent=2))
            zf.writestr("db.json", _json.dumps({"tables": counts}, ensure_ascii=False, indent=2))
            zf.writestr("settings.json", _json.dumps(safe_keys, ensure_ascii=False, indent=2))
            zf.writestr("errors.json", _json.dumps(
                [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "sample"}} for k, v in self.error_bucket().items()],
                ensure_ascii=False, indent=2))
            zf.writestr("logs.txt", "\n".join(list(self.log_ring()))[-20000:])
        data = buf.getvalue()
        return aiohttp_web.Response(body=data, content_type="application/zip",
                                    headers={"Content-Disposition": 'attachment; filename="fishpond-diag.zip"'})

    async def tunnel_sync_loop(self):
        """临时隧道重启后自动同步新域名，避免后台还显示旧链接。"""
        import re as _re
        while True:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "journalctl", "-u", "cloudflared-tunnel", "-n", "300", "--no-pager",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                found = _re.findall(rb"https://[a-z0-9-]+\.trycloudflare\.com", out or b"")
                if found:
                    url = found[-1].decode()
                    if self.store.get_setting("current_tunnel_url", "") != url:
                        self.store.set_setting("current_tunnel_url", url)
                        try:
                            (BASE / "tunnel_url").write_text(url, encoding="utf-8")
                        except Exception:
                            pass
                        log.info("临时隧道已同步: %s", url)
            except Exception:
                pass
            await asyncio.sleep(300)

    async def run(self):
        if not self.api_key:
            log.warning("未设置 DEEPSEEK_API_KEY，机器人会回复提示语")
        self.http = aiohttp.ClientSession()
        self.install_error_capture()
        self.spawn(self.health_loop(), "health_loop")
        admin_task = asyncio.create_task(self.start_admin_server())
        bored_task = asyncio.create_task(self.bored_loop())
        cleanup_task = asyncio.create_task(self.cleanup_loop())
        backup_task = asyncio.create_task(self.backup_loop())
        try:
            n = self.store.image_cleanup_stale(10)
            if n:
                log.info("清理了 %s 条卡住的生图任务", n)
        except Exception:
            pass
        reminder_task = asyncio.create_task(self.messenger.loop())
        update_watch_task = asyncio.create_task(self.update_watch_loop())
        mem_task = asyncio.create_task(self.memory_cleanup_loop())
        self.spawn(self.bili_auto_loop(), "bili_auto_loop")
        self.spawn(self.bili_acct_loop(), "bili_acct_loop")
        self.spawn(self.tunnel_sync_loop(), "tunnel_sync")
        self.spawn(self.bili_proactive_loop(), "bili_proactive_loop")
        self.spawn(self.trait_loop(), "trait_loop")
        self.spawn(self.emotion_proactive_loop(), "emotion_proactive")
        self.spawn(self.panic_loop(), "panic_loop")
        self.spawn(self.boredom_loop(), "boredom_loop")
        self.spawn(self.balance_panic_loop(), "balance_panic_loop")
        self.spawn(self.world_loop(), "world_loop")
        if True:
            self.spawn(self.gm_timeout_loop(), "gm_timeout")
        stats_task = asyncio.create_task(self.stats_heartbeat())
        try:
            await self.ws_loop()
        finally:
            admin_task.cancel()
            bored_task.cancel()
            cleanup_task.cancel()
            await self.http.close()

    @staticmethod
    def role_allowed(role: str, rel_path: str) -> bool:
        if role == "viewer":
            return not rel_path.startswith("/api/login-logs")
        if role == "super":
            return True
        admin_paths = ("/api/status", "/api/logs", "/api/group-reply", "/api/group-rate", "/api/conversations",
                       "/api/keywords", "/api/prefix", "/api/auto", "/api/end-phrase", "/api/stickers",
                       "/api/bored", "/api/whitelist", "/api/accounts", "/api/login-logs", "/api/me",
                       "/api/tokens")
        user_paths = ("/api/whitelist", "/api/login-logs", "/api/me", "/api/tokens")
        if role == "admin":
            return any(rel_path.startswith(p) for p in admin_paths)
        if role == "user":
            return any(rel_path.startswith(p) for p in user_paths)
        return False

    @staticmethod
    def client_ip(request) -> str:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
        real = request.headers.get("X-Real-IP", "")
        if real:
            return real.strip()
        ip = request.remote or ""
        if ip in ("::1", "::ffff:127.0.0.1"):
            ip = "127.0.0.1"
        return ip

    async def ip_location(self, ip: str) -> str:
        if not ip or ip.startswith(("127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.", "::1")):
            return "内网"
        cache = getattr(self, "_ip_loc_cache", {})
        hit = cache.get(ip)
        if hit and time.time() - hit[1] < 3600:
            return hit[0]
        try:
            async with self.http.get(
                f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,isp",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                d = await resp.json(content_type=None)
            if d.get("status") == "success":
                parts = [d.get("country"), d.get("regionName"), d.get("city")]
                loc = " ".join([p for p in parts if p])
                if d.get("isp"):
                    loc += " · " + str(d.get("isp"))
                loc = loc.strip() or "未知"
            else:
                loc = "未知"
        except Exception:
            loc = ""
        cache[ip] = (loc, time.time())
        self._ip_loc_cache = cache
        return loc

    def master_ok(self, request) -> bool:
        token = (os.environ.get("FISHPOND_MASTER_TOKEN") or "").strip()
        return bool(token) and request.headers.get("X-Master-Token", "") == token

    async def api_status(self, request):
        if not self.master_ok(request):
            self.require_auth(request)
        info = await self.napcat_login_info()
        fresh = await self.fresh_nick()
        if fresh:
            info = {**info, "nick": fresh}
        # NapCat 有时显示在线但会话已失效（发送返回 1200）：10 分钟内有发送失败就按离线算
        send_fail = getattr(self, "_send_fail", None) or {}
        fail_recent = bool(send_fail) and (time.time() - float(send_fail.get("at") or 0) < 600)
        info = {**info, "online": bool(info.get("online")) and not fail_recent,
                "send_failed": fail_recent,
                "send_error": (send_fail.get("msg") or "") if fail_recent else ""}
        need_login = (not bool(info.get("online"))) or fail_recent or bool(
            self.offline_since and (time.time() - self.offline_since) > 120)
        return aiohttp_web.json_response(
            {
                "code": 0,
                "bridge_connected": self.connected,
                "offline_minutes": int((time.time() - self.offline_since) / 60) if self.offline_since else 0,
                "need_login": need_login,
                "qq": info,
                "self_id": self.self_id,
                "model": self.model,
                "messages": self.msg_count,
                "replies": self.reply_count,
                "uptime": int(time.time() - self.started_at),
                "last_message": self.last_message,
                "last_event_at": self.last_event_at,
                "groups_wl": self.store.groups(),
                "users_wl": self.store.users(),
                "admins": self.store.admins(),
                "usage_today": self.usage_today(),
            }
        )

    def record_usage(self, usage: dict | None, kind: str, uid: str = "", gid: str = ""):
        """记录一次模型调用的 token 用量：写日志 + 落库（token_usage 表）。"""
        if not isinstance(usage, dict):
            return
        p = int(usage.get("prompt_tokens") or 0)
        c = int(usage.get("completion_tokens") or 0)
        if not (p or c):
            return
        log.info("[tokens] %s prompt=%s completion=%s total=%s", kind, p, c, p + c)
        try:
            model = ""
            try:
                model = str((self.current_provider() or {}).get("model") or self.model or "")
            except Exception:
                model = str(self.model or "")
            self.store.token_add(kind, p, c, model=model, uid=uid, gid=gid)
        except Exception as e:
            log.warning("记录 token 用量失败: %s", e)

    def usage_today(self) -> dict:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            return (self.store.token_stats(today, today).get("summary") or {})
        except Exception:
            return {}

    async def api_tokens(self, request):
        self.require_role(request, "user")
        rng = str(request.query.get("range") or "today")
        if rng not in self.TOKEN_RANGES:
            rng = "today"
        label, back_start, back_end = self.TOKEN_RANGES[rng]
        today = datetime.now().date()

        def d(n):
            return (today - timedelta(days=int(n))).strftime("%Y-%m-%d")

        if back_start is None:
            start, end = "", ""
        else:
            start, end = d(back_start), d(back_end)
        data = self.store.token_stats(start, end, recent=60)
        return aiohttp_web.json_response({
            "code": 0, "range": rng, "label": label,
            "start": start, "end": end, **data,
        })

    def test_redirect_target(self) -> str:
        """测试模式下把所有外发消息改送这里；返回空串表示不拦截。"""
        try:
            if self.store.get_setting("test_redirect", "0") != "1":
                return ""
            t = (self.store.get_setting("test_redirect_qq", "") or "").strip()
            if t:
                return t
            admins = self.super_admin_qqs()
            return str(admins[0]) if admins else ""
        except Exception:
            return ""

    async def api_test_send(self, request):
        self.require_super(request)
        d = await request.json()
        qq = str(d.get("qq") or "").strip()
        text = str(d.get("text") or "").strip()[:300]
        if not qq or not text:
            return aiohttp_web.json_response({"code": -1, "message": "qq 和 text 都要填"})
        try:
            r = await self.onebot_action("send_msg", {
                "message_type": "private", "user_id": qq,
                "message": [{"type": "text", "data": {"text": text}}]})
            ok = bool(r) and (r.get("status") in ("ok", "async") or r.get("retcode") == 0)
            return aiohttp_web.json_response({"code": 0 if ok else -1, "result": str(r)[:300]})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": str(e)[:160]})

    async def api_testmode(self, request):
        self.require_super(request)
        if request.method == "POST":
            d = await request.json()
            self.store.set_setting("test_redirect", "1" if d.get("enabled") else "0")
            if "qq" in d:
                self.store.set_setting("test_redirect_qq", str(d.get("qq") or "").strip())
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("test_redirect", "0") == "1",
            "qq": self.store.get_setting("test_redirect_qq", ""),
            "target": self.test_redirect_target(),
            "super_admins": self.super_admin_qqs(),
            "checks": len(self.SELFCHECK_ITEMS),
        })

    async def api_qr(self, request):
        if not self.master_ok(request):
            self.require_super(request)   # 申请二维码会动 QQ 登录态，只允许超管
        try:
            body = await request.json()
        except Exception:
            body = {}
        force = bool((body or {}).get("force"))
        now = time.time()

        def render(qr: str):
            """把 NapCat 返回的链接/图片转成可直接 <img src> 的 data url。"""
            out = {"code": 0, "qrcodeurl": qr}
            if not qr:
                return {"code": -1, "message": "NapCat 没有返回二维码"}
            if qr.startswith("data:"):
                out["qrcode"] = qr
            elif qr.startswith(("http://", "https://")):
                try:
                    import io as _io
                    import qrcode as _qr
                    img = _qr.make(qr)
                    buf = _io.BytesIO()
                    img.save(buf, format="PNG")
                    out["qrcode"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
                except Exception as e:
                    log.warning("二维码生成失败: %s", e)
                    return {"code": -1, "message": f"二维码生成失败: {e}"}
            else:
                out["qrcode"] = "data:image/png;base64," + qr
            return out

        # 1) 缓存未过期就直接复用（扫码期间反复申请会互相作废）
        cache = getattr(self, "_qr_cache", None)
        if not force and cache and now - cache["ts"] < self.qr_valid_seconds:
            out = render(cache["url"])
            out["cached"] = True
            out["age"] = int(now - cache["ts"])
            return aiohttp_web.json_response(out)

        # 2) 需要新码：Refresh 才会真正换新（Get 会一直返回同一个旧码）
        resp = await self.napcat_api("/api/QQLogin/RefreshQRcode")
        data = resp.get("data") or {}
        url = data.get("qrcodeurl") or data.get("qrcode") or ""
        if resp.get("code") != 0 or not url:
            msg = str(resp.get("message") or "")
            resp2 = await self.napcat_api("/api/QQLogin/GetQQLoginQrcode")
            d2 = resp2.get("data") or {}
            url = d2.get("qrcode") or d2.get("qrcodeurl") or ""
            if not url and "logined" in (msg + str(resp2.get("message") or "")).lower():
                info = await self.napcat_api("/api/QQLogin/GetQQLoginInfo")
                d = info.get("data") or {}
                if not str(d.get("uin") or d.get("uid") or "").strip():
                    return aiohttp_web.json_response({
                        "code": -1, "need_restart": True,
                        "message": "NapCat 登录状态卡死：它认为已登录，但账号信息是空的。点「重启 NapCat」清掉状态，再申请二维码。",
                    })
            if not url:
                detail = f"{msg or resp2.get('message') or '未知原因'}"
                if ("超时" in detail or "未返回" in detail or "没给出二维码" in detail):
                    self._qr_fail = getattr(self, "_qr_fail", 0) + 1
                    now2 = time.time()
                    if self._qr_fail >= 3 and now2 - getattr(self, "_qr_auto_ts", 0) > 600:
                        self._qr_fail = 0
                        self._qr_auto_ts = now2
                        self.spawn(self.restart_napcat_container(), "napcat_auto_restart")
                        log.warning("二维码连续失败，自动重启 NapCat: %s", self.napcat_container())
                        return aiohttp_web.json_response({
                            "code": -1, "need_restart": True,
                            "message": "NapCat 无响应，已自动重启；等 30 秒后再点「刷新二维码」",
                        })
                return aiohttp_web.json_response({
                    "code": -1, "message": f"NapCat 没给出二维码：{detail}",
                })
        self._qr_cache = {"url": url, "ts": now}
        out = render(url)
        out["cached"] = False
        out["age"] = 0
        return aiohttp_web.json_response(out)

    def napcat_container(self) -> str:
        return (os.environ.get("FISHPOND_NAPCAT_CONTAINER") or "napcat").strip() or "napcat"

    async def restart_napcat_container(self) -> tuple[bool, str]:
        name = self.napcat_container()
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "-n", "docker", "restart", name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, err = await asyncio.wait_for(proc.communicate(), timeout=90)
            if proc.returncode == 0:
                log.info("已重启 NapCat 容器: %s", name)
                return True, ""
            return False, (err.decode("utf-8", "ignore")[:120] or "无权限执行 docker")
        except Exception as e:
            return False, str(e)[:120]

    async def api_napcat_restart(self, request):
        self.require_super(request)
        ok, err = await self.restart_napcat_container()
        if ok:
            return aiohttp_web.json_response({"code": 0, "message": "NapCat 已重启，等 20~30 秒后再申请二维码"})
        return aiohttp_web.json_response({"code": -1, "message": "重启失败：" + (err or "未知原因")})

    async def _restart_soon(self):
        await asyncio.sleep(1.5)
        try:
            log.warning("更新完成，进程内重启")
            os.execv(sys.executable, [sys.executable, str(BASE / "bot.py")])
        except Exception as e:
            log.error("重启失败，请手动 systemctl restart qqbot-bridge: %s", e)
            await self.report_update_failure(f"新版本已写入但重启失败: {e}")

    async def api_bot_profile(self, request):
        self.require_super(request)
        force = request.query.get("refresh") == "1"
        if force:
            now = time.time()
            last = getattr(self, "_last_profile_force", 0)
            if now - last < 10:
                force = False
            else:
                self._last_profile_force = now
        info = await self.napcat_login_info(force=force)
        try:
            res = await self.onebot_action("get_login_info", {})
            if isinstance(res, dict) and res.get("status") == "ok":
                d = res.get("data") or {}
                if d.get("nickname"):
                    info = {"online": True, "uin": str(d.get("user_id") or info.get("uin") or ""), "nick": str(d.get("nickname"))}
        except Exception:
            pass
        uin = str(info.get("uin") or self.self_id or "")
        fresh = await self.fresh_nick()
        if fresh:
            info = {**info, "uin": uin, "nick": fresh}
        return aiohttp_web.json_response({
            "code": 0,
            "uin": uin,
            "nick": info.get("nick") or "",
            "online": bool(info.get("online")),
            "avatar": f"https://q1.qlogo.cn/g?b=qq&nk={uin}&s=640" if uin else "",
        })

    async def api_bot_nick(self, request):
        self.require_super(request)
        data = await request.json()
        nick = str(data.get("nickname") or "").strip()
        if not nick or len(nick) > 36:
            return aiohttp_web.json_response({"code": -1, "message": "昵称需为 1~36 个字符"})
        if getattr(self, "ws", None) is None:
            return aiohttp_web.json_response({"code": -1, "message": "机器人未连接，暂时无法修改"})
        res = await self.onebot_action("set_qq_profile", {"nickname": nick})
        ok = bool(res) and (res.get("status") in ("ok", "async") or res.get("retcode") == 0)
        if not ok:
            return aiohttp_web.json_response({"code": -1, "message": f"修改失败：{str(res)[:120]}"})
        return aiohttp_web.json_response({"code": 0})

    async def api_bot_avatar(self, request):
        self.require_super(request)
        data = await request.json()
        url = str(data.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return aiohttp_web.json_response({"code": -1, "message": "请填 http/https 图片地址"})
        if getattr(self, "ws", None) is None:
            return aiohttp_web.json_response({"code": -1, "message": "机器人未连接，暂时无法修改"})
        res = await self.onebot_action("set_qq_avatar", {"file": url})
        ok = bool(res) and (res.get("status") in ("ok", "async") or res.get("retcode") == 0)
        if not ok:
            return aiohttp_web.json_response({"code": -1, "message": f"修改失败（NapCat 可能不支持该接口）：{str(res)[:120]}"})
        return aiohttp_web.json_response({"code": 0})

    async def _review_worker(self, rows):
        job = self._review_job
        try:
            def progress(n):
                if job:
                    job["done"] = min(job["total"], job["done"] + n)
            ids = await self.ai_review_memories(rows, progress)
            by_id = {r["id"]: r for r in rows}
            reasons = getattr(self, "_last_review_reasons", {})
            job["ids"] = ids
            job["items"] = [{"id": i, "content": by_id[i]["content"], "reason": reasons.get(i, "")}
                            for i in ids if i in by_id]
            job["done"] = job["total"]
            job["status"] = "done"
        except Exception as e:
            log.exception("记忆审核失败")
            job["status"] = "error"
            job["error"] = str(e)[:200]

    async def api_scripts_public_list(self, request):
        if not SCRIPT_HUB:
            raise aiohttp_web.HTTPNotFound(text="not found")
        if str(request.query.get("token") or "") != self.store.get_setting("game_dist_token", ""):
            raise aiohttp_web.HTTPForbidden(text="token invalid")
        items = [{"id": r["id"], "name": r["name"], "description": r.get("description") or "",
                  "mode": r.get("mode") or "story"}
                 for r in self.store.script_list(only_enabled=True)]
        return aiohttp_web.json_response({"code": 0, "items": items})

    async def api_scripts_public_get(self, request):
        if not SCRIPT_HUB:
            raise aiohttp_web.HTTPNotFound(text="not found")
        if str(request.query.get("token") or "") != self.store.get_setting("game_dist_token", ""):
            raise aiohttp_web.HTTPForbidden(text="token invalid")
        sid = request.match_info.get("sid", "")
        row = self.store.script_get(sid) if str(sid).isdigit() else {}
        if not row or not row.get("enabled"):
            raise aiohttp_web.HTTPNotFound(text="script not found")
        tag = str(request.query.get("token") or "")[:24]
        return aiohttp_web.json_response({
            "id": row["id"], "name": row["name"],
            "system_prompt": self.watermark_prompt(str(row.get("system_prompt") or ""), tag),
            "intro": row.get("intro") or "",
            "mode": row.get("mode") or "story",
        })

    @staticmethod
    def parse_balance_text(d) -> str:
        if not isinstance(d, dict):
            return ""
        infos = d.get("balance_infos")
        if isinstance(infos, list) and infos:
            parts = []
            for i in infos:
                if not isinstance(i, dict):
                    continue
                total = i.get("total_balance")
                if total in (None, ""):
                    continue
                cur = str(i.get("currency") or "")
                parts.append(f"{cur} {total}".strip())
            if parts:
                return " / ".join(parts)
        data = d.get("data") if isinstance(d.get("data"), dict) else {}
        tc = data.get("total_credits")
        tu = data.get("total_usage")
        if tc is not None and tu is not None:
            try:
                return f"剩余 {round(float(tc) - float(tu), 4)}"
            except Exception:
                pass
        for src in (d, data):
            for k in ("balance", "total_balance", "credits", "remain", "quota"):
                v = src.get(k) if isinstance(src, dict) else None
                if v not in (None, ""):
                    return str(v)
        return ""

    async def fetch_balance_text(self, row) -> str:
        base = (row.get("base_url") or "").rstrip("/")
        key = row.get("api_key") or ""
        if not base or not key:
            return ""
        headers = {"Authorization": f"Bearer {key}"}
        low = base.lower()
        urls = []
        if "deepseek" in low:
            urls.append(base + "/user/balance")
        elif "siliconflow" in low:
            urls.append(base + "/user/info")
        elif "openrouter" in low:
            urls.append(base + "/credits")
        urls += [base + "/user/balance", base + "/user/info"]
        seen = []
        for url in urls:
            if url in seen:
                continue
            seen.append(url)
            try:
                async with self.http.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                text = self.parse_balance_text(data)
                if text:
                    return text
            except Exception:
                continue
        return ""

    def _stk_state(self, **kw):
        st = getattr(self, "_sticker_install", None)
        if st is None:
            st = {"running": False, "done": False, "added": 0, "skipped": 0, "message": "", "ts": time.time()}
        st.update(kw)
        self._sticker_install = st
        try:
            self.store.set_setting("sticker_import_state", json.dumps(
                {k: st.get(k) for k in ("running", "done", "added", "skipped", "message", "ts")}, ensure_ascii=False))
        except Exception:
            pass
        return st

    def _gp_ok(self, request, token: str):
        row = self.db_panel_by_token(token)
        if not row:
            return None
        if int(row["enabled"] or 0) == 0:
            return None
        sid = request.cookies.get("fp_gp_sid", "")
        hit = getattr(self, "_gp_sess", {}).get(sid)
        if hit and hit[0] == token and hit[1] > time.time():
            return row
        return None

    async def gadmin_login(self, request):
        token = str(request.match_info.get("token") or "")
        code = str(request.query.get("code") or "")
        hit = (getattr(self, "_gp_codes", {}) or {}).get(code)
        row = self.db_panel_by_token(token)
        if not hit or not row or hit[0] != token or hit[1] < time.time():
            return aiohttp_web.json_response({"code": -1, "message": "登录链接已失效"}, status=403)
        (getattr(self, "_gp_codes", {}) or {}).pop(code, None)
        if int(row["enabled"] or 0) == 0:
            return aiohttp_web.json_response({"code": -1, "message": "该群面板已停用"}, status=403)
        sid = secrets.token_urlsafe(24)
        sess = getattr(self, "_gp_sess", None)
        if sess is None:
            sess = {}; self._gp_sess = sess
        sess[sid] = (token, time.time() + 7 * 86400)
        resp = aiohttp_web.HTTPFound(f"{self.webui_prefix()}/g/{token}/")
        resp.set_cookie("fp_gp_sid", sid, max_age=7 * 86400, httponly=True, samesite="Lax", path="/")
        raise resp

    async def api_gr_get(self, request):
        self.require_auth(request)
        whitelist = self.store.groups()
        groups = whitelist or sorted(self.group_activity.keys())
        return aiohttp_web.json_response({
            "code": 0,
            "whitelist_empty": not bool(whitelist),
            "groups": groups,
            "always": self.store.always_groups(),
            "continue_seconds": int(float(self.store.get_setting("group_continue_seconds", str(self.continue_seconds)) or 180)),
            "max_replies": int(float(self.store.get_setting("group_max_replies", str(self.group_max_replies)) or 6)),
            "max_active_users": int(float(self.store.get_setting("max_active_users", str(self.max_active_users)) or 3)),
            "thrifty": self.store.get_setting("thrifty_mode", "0") == "1",
            "at_reply": self.store.get_setting("reply_at_enabled", "0") == "1",
            "end_phrase_enabled": self.store.get_setting("end_phrase_enabled", "1") == "1",
            "end_phrase_reply": self.store.get_setting("end_phrase_reply", "好的，那我退下了"),
        })

    async def api_gr_config(self, request):
        self.require_auth(request)
        data = await request.json()
        if "continue_seconds" in data:
            try:
                secs = max(30, int(float(data.get("continue_seconds"))))
            except (TypeError, ValueError):
                return aiohttp_web.json_response({"code": -1, "message": "接话时间需为秒数（≥30）"})
            self.store.set_setting("group_continue_seconds", str(secs))
        if "max_replies" in data:
            try:
                cap = max(1, int(float(data.get("max_replies"))))
            except (TypeError, ValueError):
                return aiohttp_web.json_response({"code": -1, "message": "频率需为整数条/分钟"})
            self.store.set_setting("group_max_replies", str(cap))
        if "max_active_users" in data:
            try:
                n = max(1, int(float(data.get("max_active_users"))))
            except (TypeError, ValueError):
                return aiohttp_web.json_response({"code": -1, "message": "人数需为整数"})
            self.store.set_setting("max_active_users", str(n))
        if "at_reply" in data:
            self.store.set_setting("reply_at_enabled", "1" if data.get("at_reply") else "0")
        if "thrifty" in data:
            self.store.set_setting("thrifty_mode", "1" if data.get("thrifty") else "0")
        if "end_phrase" in data:
            self.store.set_setting("end_phrase_enabled", "1" if data.get("end_phrase") else "0")
        if "end_phrase_reply" in data:
            text = str(data.get("end_phrase_reply") or "").strip()
            self.store.set_setting("end_phrase_reply", text[:100])
        return aiohttp_web.json_response({"code": 0})

    async def api_gr_always(self, request):
        self.require_auth(request)
        data = await request.json()
        gid = str(data.get("group_id") or "").strip()
        if not gid.isdigit():
            return aiohttp_web.json_response({"code": -1, "message": "群号需为纯数字"})
        self.store.set_always_group(gid, bool(data.get("enabled")))
        return aiohttp_web.json_response({"code": 0})


add(id="world.engine", name="世界引擎", entry="fishpond.features.world.service:WorldMixin",
    routes=["/api/world/state", "/api/world/config", "/api/world/tasks", "/api/world/check", "/api/world/trend", "/api/world/summary", "/api/weather", "/api/weather/loc", "/api/bili/account/status", "/api/bili/account/config", "/api/bili/account/qr", "/api/bili/account/qr/poll", "/api/bili/account/action", "/api/bili/account/logs"], tables=["world_state", "world_events"],
    settings=["world_enabled", "world_scale"], ui="机器人/世界",
    files="fishpond/features/world/service.py", status="active")
add(id="runtime.health", name="健康巡检", entry="fishpond.features.runtime.service:health_loop",
    routes=["/api/health"], tables=[], settings=[], ui="超级管理员/基本设置",
    files="fishpond/features/runtime/service.py", status="active")
add(id="runtime.errors", name="错误面板", entry="fishpond.features.runtime.service:api_errors",
    routes=["/api/errors"], tables=[], settings=[], ui="超级管理员/基本设置",
    files="fishpond/features/runtime/service.py", status="active")
add(id="runtime.diag", name="诊断包", entry="fishpond.features.runtime.service:api_diag_pack",
    routes=["/api/diag/pack"], tables=[], settings=[], ui="超级管理员/基本设置",
    files="fishpond/features/runtime/service.py", status="active")
add(id="core.runtime", name="运行与备份", entry="fishpond.features.runtime.service:run",
    routes=["/api/status", "/api/tokens"], tables=[], settings=["app_version"], ui="（核心）",
    files="fishpond/features/runtime/service.py", status="active")
