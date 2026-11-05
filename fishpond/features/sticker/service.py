"""表情包模块：发送、收录、上传、群主表情包导入。"""
import asyncio
from collections import deque
import base64
import io
import json
import random
import re
import secrets
import time
import zipfile
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
STICKER_DIR = BASE / "stickers"
DEFAULT_PACK_BASE = "https://xrzs.cloud"


class StickerMixin:
    def sticker_pack_token(self) -> str:
        tok = self.store.get_setting("sticker_pack_token", "")
        if not tok:
            tok = secrets.token_hex(8)
            self.store.set_setting("sticker_pack_token", tok)
        return tok

    async def api_stickerpack_list(self, request):
        base = (self.store.get_setting("public_base_url", "") or "").rstrip("/")
        with self.store._conn() as c:
            rows = {r["filename"]: r["description"] for r in c.execute("SELECT filename,description FROM stickers")}
        items = []
        for name in self.store.stickers():
            prefix = self.webui_prefix()
            items.append({"filename": name, "description": rows.get(name, ""),
                          "url": f"{base}{prefix}/api/stickerpack/file?name={name}"})
        return aiohttp_web.json_response({"code": 0, "items": items, "count": len(items)})

    async def api_stickerpack_info(self, request):
        self.require_super(request)
        base = (self.store.get_setting("public_base_url", "") or "").rstrip("/")
        return aiohttp_web.json_response({"code": 0, "token": self.sticker_pack_token(),
                                          "base": base, "count": len(self.store.stickers())})

    async def api_stickerpack_file(self, request):
        name = str(request.query.get("name") or "")
        path = (STICKER_DIR / name).resolve()
        if not str(path).startswith(str(STICKER_DIR.resolve())) or not path.is_file():
            raise aiohttp_web.HTTPNotFound()
        return aiohttp_web.FileResponse(path)

    def _pack_jobs(self) -> dict:
        if not hasattr(self, "_pack_job_map"):
            self._pack_job_map = {}
        return self._pack_job_map

    async def api_stickers_import_remote(self, request):
        self.require_super(request)
        d = await request.json()
        base = str(d.get("base") or "").strip().rstrip("/") or DEFAULT_PACK_BASE
        token = str(d.get("token") or "")
        if not base.startswith("http"):
            return aiohttp_web.json_response({"code": -1, "message": "地址格式不对"})
        import uuid as _uuid
        job = _uuid.uuid4().hex[:12]
        self._pack_jobs()[job] = {"state": "running", "total": 0, "done": 0, "added": 0, "error": ""}
        asyncio.get_running_loop().create_task(self._pack_import_job(job, base, token))
        return aiohttp_web.json_response({"code": 0, "job": job})

    async def api_stickers_repair(self, request):
        self.require_super(request)
        added = 0
        for p in STICKER_DIR.glob("*"):
            if not p.is_file():
                continue
            with self.store._conn() as c:
                row = c.execute("SELECT 1 FROM stickers WHERE filename=?", (p.name,)).fetchone()
            if not row:
                self.store.add_sticker(p.name)
                added += 1
        return aiohttp_web.json_response({"code": 0, "added": added})

    async def api_stickers_import_status(self, request):
        self.require_super(request)
        job = str(request.query.get("job") or "")
        return aiohttp_web.json_response({"code": 0, "job": self._pack_jobs().get(job) or {"state": "missing"}})

    async def _pack_import_job(self, job: str, base: str, token: str):
        info = self._pack_jobs()[job]
        try:
            params = {"token": token} if token else {}
            async with self.http.get(f"{base}/api/stickerpack/list", params=params,
                                     timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json(content_type=None)
            if not isinstance(data, dict) or data.get("code") != 0:
                info["state"] = "failed"
                info["error"] = (data or {}).get("message") or "对方返回异常"
                return
            items = data.get("items") or []
            info["total"] = len(items)
            sem = asyncio.Semaphore(6)

            async def one(it):
                name = str(it.get("filename") or "")
                if not name:
                    info["done"] += 1
                    return
                if (STICKER_DIR / name).exists():
                    # 旧版本同步过但没登记的文件，这里补登记
                    try:
                        self.store.add_sticker(name)
                    except Exception:
                        pass
                    info["done"] += 1
                    return
                async with sem:
                    try:
                        blob = None
                        for _try in range(2):
                            try:
                                async with self.http.get(it["url"], timeout=aiohttp.ClientTimeout(total=300, sock_read=120)) as r:
                                    if r.status == 200:
                                        blob = await r.read()
                                        break
                            except Exception:
                                continue
                        if blob is None:
                            info["done"] += 1
                            return
                        if len(blob) > 5 * 1024 * 1024:
                            info["done"] += 1
                            return
                        (STICKER_DIR / name).write_bytes(blob)
                        self.store.add_sticker(name)
                        desc = str(it.get("description") or "")
                        if desc:
                            with self.store._conn() as c:
                                c.execute("UPDATE stickers SET description=? WHERE filename=?", (desc, name))
                        info["added"] += 1
                    except Exception:
                        pass
                    info["done"] += 1

            await asyncio.gather(*[one(it) for it in items])
            info["state"] = "done"
        except Exception as e:
            info["state"] = "failed"
            info["error"] = str(e)[:120]

    def sticker_url(self, name: str) -> str:
        base = (self.store.get_setting("public_base_url", "") or "").rstrip("/")
        return f"{base}/stickers/{name}" if base else ""

    async def serve_sticker(self, request):
        name = request.match_info["name"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise aiohttp_web.HTTPNotFound()
        path = STICKER_DIR / name
        if not path.exists():
            raise aiohttp_web.HTTPNotFound()
        return aiohttp_web.FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    async def api_stickers(self, request):
        self.require_auth(request)
        names = self.store.stickers()
        desc_map = {d["filename"]: (d.get("description") or "") for d in self.store.sticker_descriptions()}
        return aiohttp_web.json_response({
            "code": 0,
            "stickers": [{"name": n, "url": self.sticker_url(n),
                          "description": desc_map.get(n, "")} for n in names],
            "probability": int(self.store.get_setting("sticker_probability", "0") or 0),
            "daily_limit": int(self.store.get_setting("sticker_daily_limit", "12") or 12),
            "mode": self.store.get_setting("sticker_mode", "smart"),
            "base": (self.store.get_setting("public_base_url", "") or ""),
        })

    async def api_sticker_upload(self, request):
        self.require_auth(request)
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or not getattr(field, "filename", None):
                return aiohttp_web.json_response({"code": -1, "message": "没有收到文件"})
            data = await field.read()
            if len(data) > 2 * 1024 * 1024:
                return aiohttp_web.json_response({"code": -1, "message": "图片不能超过 2MB"})
            ext = Path(field.filename).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                return aiohttp_web.json_response({"code": -1, "message": "只支持 png/jpg/gif/webp"})
            name = secrets.token_hex(8) + ext
            (STICKER_DIR / name).write_bytes(data)
            self.store.add_sticker(name)
            host = str(request.host or "").strip()
            if host and not host.startswith(("127.0.0.1", "localhost", "192.168.", "10.", "172.")):
                self.store.set_setting("public_base_url", f"https://{host}")
            return aiohttp_web.json_response({"code": 0, "name": name})
        except Exception as e:
            log.warning("表情包上传失败: %s", e)
            return aiohttp_web.json_response({"code": -1, "message": "上传失败"})

    async def _install_sticker_pack(self, url: str):
        import io as _io, zipfile as _zip, pathlib as _pl
        st = self._sticker_install
        try:
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=300)) as r:
                if r.status != 200:
                    self._stk_state(running=False, message=f"下载失败 HTTP {r.status}")
                    return
                raw = await r.read()
            if not raw or len(raw) > 80 * 1024 * 1024:
                self._stk_state(running=False, message="包为空或超过 80MB")
                return
            zf = _zip.ZipFile(_io.BytesIO(raw))
            manifest = {}
            if "manifest.json" in zf.namelist():
                try:
                    for it in json.loads(zf.read("manifest.json").decode("utf-8")):
                        if isinstance(it, dict) and it.get("name"):
                            manifest[str(it["name"])] = str(it.get("description") or "")
                except Exception:
                    pass
            sdir = BASE / "stickers"; sdir.mkdir(parents=True, exist_ok=True)
            have = set(self.store.stickers())
            ok_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
            added = skipped = 0
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                base = _pl.PurePosixPath(name).name
                if _pl.Path(base).suffix.lower() not in ok_ext or not base or base in have:
                    skipped += 1
                    continue
                try:
                    data = zf.read(name)
                except Exception:
                    skipped += 1
                    continue
                if not data or len(data) > 6 * 1024 * 1024:
                    skipped += 1
                    continue
                try:
                    (sdir / base).write_bytes(data)
                    self.store.add_sticker(base)
                    desc = manifest.get(base) or manifest.get(name)
                    if desc:
                        self.store.set_sticker_description(base, desc)
                    have.add(base); added += 1
                except Exception:
                    skipped += 1
                self._stk_state(added=added, skipped=skipped, ts=time.time())
            self._stk_state(running=False, done=True, added=added, skipped=skipped,
                            message=f"已新增 {added} 张，跳过 {skipped} 张（重复/无效）")
            log.info("一键表情包：新增 %s，跳过 %s", added, skipped)
        except Exception as e:
            self._stk_state(running=False, message=f"导入失败: {e}"[:300])
            log.warning("一键表情包失败: %s", e)

    async def api_stickers_install_pack(self, request):
        self.require_super(request)
        st = getattr(self, "_sticker_install", None)
        if st is None:
            try:
                st = json.loads(self.store.get_setting("sticker_import_state", "") or "{}") or None
                if st:
                    self._sticker_install = st
            except Exception:
                st = None
        if st and st.get("running") and time.time() - float(st.get("ts") or 0) < 900:
            return aiohttp_web.json_response({"code": 0, "started": False, "message": "正在导入，请稍候…"})
        url = (self.store.get_setting("sticker_pack_url", "") or
               "https://xrzs.cloud/dl/stickers-pack.zip").strip()
        self._stk_state(running=True, done=False, added=0, skipped=0,
                        message="正在下载并导入…", ts=time.time())
        asyncio.create_task(self._install_sticker_pack(url))
        return aiohttp_web.json_response({"code": 0, "started": True, "message": "已开始导入，请稍候…"})

    async def api_stickers_install_status(self, request):
        self.require_super(request)
        st = getattr(self, "_sticker_install", None)
        if st is None:
            try:
                st = json.loads(self.store.get_setting("sticker_import_state", "") or "{}")
            except Exception:
                st = {}
        if not st:
            st = {"running": False, "done": False, "message": ""}
        if st.get("running") and time.time() - float(st.get("ts") or 0) > 900:
            st = self._stk_state(running=False, done=False, message="导入超时，请重试")
        return aiohttp_web.json_response({"code": 0, **st})

    async def api_sticker_upload_many(self, request):
        self.require_auth(request)
        saved, failed = 0, 0
        try:
            reader = await request.multipart()
            count = 0
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name not in ("files", "file") or not getattr(part, "filename", None):
                    continue
                count += 1
                if count > 50:
                    await part.read()
                    failed += 1
                    continue
                data = await part.read()
                ext = Path(part.filename).suffix.lower()
                if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp") or len(data) > 2 * 1024 * 1024:
                    failed += 1
                    continue
                name = secrets.token_hex(8) + ext
                (STICKER_DIR / name).write_bytes(data)
                self.store.add_sticker(name)
                saved += 1
            host = str(request.host or "").strip()
            if host and not host.startswith(("127.0.0.1", "localhost", "192.168.", "10.", "172.")):
                self.store.set_setting("public_base_url", f"https://{host}")
        except Exception as e:
            log.warning("批量上传表情失败: %s", e)
        return aiohttp_web.json_response({"code": 0, "saved": saved, "failed": failed})

    async def api_sticker_add_urls(self, request):
        self.require_auth(request)
        data = await request.json()
        urls = [str(u).strip() for u in (data.get("urls") or []) if str(u).strip()]
        saved, failed = 0, 0
        for url in urls[:200]:
            if not url.startswith(("http://", "https://")):
                failed += 1
                continue
            if not await self.is_public_url(url):
                failed += 1
                continue
            try:
                async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        failed += 1
                        continue
                    blob = await resp.read()
                if len(blob) > 2 * 1024 * 1024:
                    failed += 1
                    continue
                ctype = (resp.headers.get("Content-Type") or "").lower()
                ext = ".png"
                for e in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                    if e in url.lower() or e.strip(".") in ctype:
                        ext = e
                        break
                name = secrets.token_hex(8) + ext
                (STICKER_DIR / name).write_bytes(blob)
                self.store.add_sticker(name)
                saved += 1
            except Exception:
                failed += 1
        host = str(request.host or "").strip()
        if host and not host.startswith(("127.0.0.1", "localhost", "192.168.", "10.", "172.")):
            self.store.set_setting("public_base_url", f"https://{host}")
        return aiohttp_web.json_response({"code": 0, "saved": saved, "failed": failed})

    async def api_sticker_desc(self, request):
        self.require_auth(request)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        desc = str(data.get("description") or "").strip()[:300]
        if not name:
            return aiohttp_web.json_response({"code": -1, "message": "参数错误"})
        self.store.set_sticker_description(name, desc)
        return aiohttp_web.json_response({"code": 0})

    async def api_sticker_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        self.store.remove_sticker(name)
        try:
            (STICKER_DIR / name).unlink(missing_ok=True)
        except Exception:
            pass
        return aiohttp_web.json_response({"code": 0})

    async def api_sticker_config(self, request):
        self.require_auth(request)
        data = await request.json()
        if "probability" in data:
            try:
                prob = max(0, min(100, int(float(data.get("probability")))))
            except (TypeError, ValueError):
                return aiohttp_web.json_response({"code": -1, "message": "概率需为 0-100 的整数"})
            self.store.set_setting("sticker_probability", str(prob))
        if "daily_limit" in data:
            try:
                self.store.set_setting("sticker_daily_limit", str(max(0, min(100, int(data.get("daily_limit") or 0)))))
            except Exception:
                pass
        if data.get("mode") in ("random", "smart"):
            self.store.set_setting("sticker_mode", data["mode"])
        host = str(request.host or "").strip()
        if host and not host.startswith(("127.0.0.1", "localhost", "192.168.", "10.", "172.")):
            self.store.set_setting("public_base_url", f"https://{host}")
        return aiohttp_web.json_response({"code": 0})

    async def describe_sticker(self, data: bytes) -> str:
        provider = self.current_provider() or {}
        if not provider.get("api_key"):
            return ""
        if not self.vision_enabled:
            return ""
        img = self.encode_image(data)
        prompt = ("这是一张聊天表情包。用一句简短中文描述它的情绪/用途（如：无语、嘲笑、点赞、委屈、狗头），"
                  "并原样列出图片里出现的文字。格式：含义：xxx；文字：xxx（没有文字就写无）")
        payload = {
            "model": provider.get("model") or self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": img}},
            ]}],
            "temperature": 0.3,
            "max_tokens": 120,
        }
        try:
            # 这里原来直接用了未定义的 timeout，NameError 被下面的 except 吞掉，
            # 导致表情包描述永远返回空字符串（smart 选表情退化）。补上定义。
            timeout = self.timeout or 60
            async with self.http.post(
                f"{provider['base_url']}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                dataj = await resp.json(content_type=None)
                self.record_usage(dataj.get("usage"), "sticker")
            if resp.status != 200:
                return ""
            out = ((dataj.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
            out = re.sub(r"\s+", " ", out)
            return out[:60]
        except Exception:
            return ""

    async def save_sticker_from_url(self, url: str, source: str = "qq", context: str = ""):
        if not str(url or "").startswith(("http://", "https://")):
            return None, ""
        if not await self.is_public_url(url):
            return None, ""
        try:
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return None, ""
                blob = await resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
        except Exception:
            return None, ""
        if not blob or len(blob) > 5 * 1024 * 1024:
            return None, ""
        ext = ".png"
        for e in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            if e in url.lower() or e.strip(".") in ctype:
                ext = e
                break
        name = secrets.token_hex(8) + ext
        try:
            (STICKER_DIR / name).write_bytes(blob)
        except Exception:
            return None, ""
        self.store.add_sticker(name)
        desc = (context or "").strip()
        if not desc:
            desc = await self.describe_sticker(blob)
        if desc:
            self.store.set_sticker_description(name, desc[:300])
        return name, desc

    async def smart_pick_sticker(self, rows: list[dict], user_text: str, reply: str) -> str | None:
        descs = []
        for r in rows:
            d = (r.get("description") or "").strip()
            if d and d not in descs:
                descs.append(d)
        if not descs:
            return None
        provider = self.current_provider()
        if not provider.get("api_key"):
            return None
        prompt = (
            "根据下面这段对话，从候选表情说明里选一个最贴切的，只输出说明词本身（2-6字）。"
            "没有完全匹配时，选一个情绪最接近的；实在找不到合适的才输出：无。\n候选：" + "、".join(descs) +
            f"\n对方说：{user_text[:200]}\n你回复：{reply[:200]}"
        )
        payload = {
            "model": provider.get("model") or self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 20,
        }
        try:
            async with self.http.post(
                f"{provider['base_url']}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
                self.record_usage(data.get("usage"), "sticker")
                text = ((data.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
        except Exception as e:
            log.warning("智能选表情失败: %s", e)
            return None
        ans = text.strip().strip('"').strip("'").strip()
        if not ans or ans == "无":
            return None
        for r in rows:
            d = (r.get("description") or "").strip()
            if d and (d == ans or ans in d or d in ans):
                return r["filename"]
        return None

    async def auto_save_sticker_images(self, urls: list, reply: str):
        """AI 说“存了”时真正落库，失败返回 None。"""
        if not urls or not reply:
            return None
        if not any(k in reply for k in ("存了", "收了", "存起来", "收藏了", "存进", "加入表情")):
            return None
        for u in urls[:2]:
            try:
                name, desc = await self.save_sticker_from_url(u, "qq", "")
                if name:
                    log.info("AI 自动收录表情: %s %s", name, (desc or "")[:30])
                    return name
            except Exception as e:
                log.warning("AI 收录表情失败: %s", e)
        return None

    async def maybe_send_sticker(self, ws, mtype: str, ev: dict, user_text: str = "", reply: str = "", has_image: bool = False):
        base = self.SI("sticker_probability", 0)
        if base <= 0:
            return
        # 场景加权：斗图/短回复更容易发，安慰或严肃话题不发
        prob = base
        if has_image:
            prob += 20
        if any(k in (user_text or "") for k in ("哈哈", "笑死", "草", "图", "表情", "斗图")):
            prob += 10
        if any(k in (user_text or "") for k in ("难受", "难过", "哭", "安慰", "认真", "帮帮我")):
            prob -= 30
        if len(str(reply or "")) <= 8:
            prob += 10
        if prob <= 0 or random.randint(1, 100) > min(90, prob):
            return
        now = time.time()
        key = f"{ev.get('group_id') or ''}:{ev.get('user_id') or ''}"
        last = getattr(self, "_sticker_last_at", {}).get(key, 0)
        if now - last < 300:
            return
        day = time.strftime("%Y-%m-%d")
        if getattr(self, "_sticker_day", "") != day:
            self._sticker_day = day
            self._sticker_count = 0
        try:
            cap = max(0, int(self.store.get_setting("sticker_daily_limit", "12") or 12))
        except Exception:
            cap = 12
        if getattr(self, "_sticker_count", 0) >= cap:
            return
        rows = self.store.sticker_descriptions()
        if not rows:
            return
        mode = self.store.get_setting("sticker_mode", "smart")
        name = None
        if mode == "smart":
            name = await self.smart_pick_sticker(rows, user_text, reply)
            if not name:
                return
        else:
            name = random.choice([r["filename"] for r in rows])
        recent = getattr(self, "_sticker_recent", [])
        if name in recent[-10:]:
            return
        sd = max(0, min(10000, self.SI("sticker_delay_ms", 800)))
        if sd:
            await asyncio.sleep(sd / 1000.0)
        base_url = (self.store.get_setting("public_base_url", "") or "").rstrip("/")
        if not base_url:
            return
        ok = await self.send_sticker(ws, mtype, ev, name)
        if ok:
            recent.append(name)
            self._sticker_recent = recent[-20:]
            self._sticker_last_at = getattr(self, "_sticker_last_at", {})
            self._sticker_last_at[key] = now
            self._sticker_count = getattr(self, "_sticker_count", 0) + 1
            log.info("智能表情已发送: %s", name)

    async def send_sticker(self, ws, mtype: str, ev: dict, name: str) -> bool:
        base = (self.store.get_setting("public_base_url", "") or "").rstrip("/")
        if not base:
            return False
        _tgt = self.test_redirect_target()
        if _tgt and str(ev.get("user_id") or "") != _tgt:
            mtype = "private"
            ev = {**ev, "user_id": _tgt}
        params = {"message": [{"type": "image", "data": {"file": f"{base}/stickers/{name}"}}], "message_type": mtype}
        if mtype == "group":
            params["group_id"] = ev.get("group_id")
        else:
            params["user_id"] = ev.get("user_id")
        # 等 OneBot 回执再判定成功：NapCat 拉图失败（如 401）时 retcode 非 0，
        # 以前这里一发出去就打“已发送”，会把故障伪装成成功。
        res = await self.onebot_call(ws, "send_msg", params, timeout=30)   # 图要下载，10 秒会误判超时
        code = (res or {}).get("retcode") if isinstance(res, dict) else None
        if code not in (0, 1):
            reason = ""
            if isinstance(res, dict):
                reason = str(res.get("wording") or res.get("message") or res.get("msg") or "")[:160]
            log.warning("表情包发送失败: %s retcode=%s %s", name, code, reason)
            return False
        if mtype == "group":
            gid = str(ev.get("group_id"))
            now = time.time()
            self.group_last_reply[gid] = now
            self.group_reply_times.setdefault(gid, deque()).append(now)
        log.info("表情包已发送: %s", name)
        return True

    @staticmethod
    def match_capture_keyword(text: str, keywords) -> str | None:
        """在用户消息里找收录表情包的命令词。

        规则：**先比出现位置（越靠前越优先），位置相同再取更长的**。
        不能只按长度：如果含义本身也包含某个关键词，按长度可能误选中含义里的词，
        导致命令词和含义都截错。命令词正常情况下出现在消息最前面（@ 之后）。
        """
        t = str(text or "").strip()
        hits = [(t.find(str(w)), -len(str(w)), str(w)) for w in (keywords or []) if str(w) and str(w) in t]
        if not hits:
            return None
        return min(hits)[2]



class StickerStoreMixin:
    def stickers(self) -> list[str]:
        with self._conn() as c:
            return [r["filename"] for r in c.execute("SELECT filename FROM stickers ORDER BY id")]

    def sticker_descriptions(self) -> list[dict]:
        with self._conn() as c:
            return [
                dict(r)
                for r in c.execute("SELECT filename, COALESCE(description,'') AS description FROM stickers ORDER BY id")
            ]

    def add_sticker(self, filename: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO stickers(filename, created_at) VALUES(?,datetime('now','localtime'))", (filename,))

    def set_sticker_description(self, filename: str, description: str):
        with self._conn() as c:
            c.execute("UPDATE stickers SET description=? WHERE filename=?", (str(description or ""), filename))

    def remove_sticker(self, filename: str):
        with self._conn() as c:
            c.execute("DELETE FROM stickers WHERE filename=?", (filename,))


add(id="sticker.send", name="表情包发送", entry="fishpond.features.sticker.service:maybe_send_sticker",
    routes=["/api/stickers", "/api/stickers/*"], tables=["stickers"], settings=["sticker_*"], ui="聊天/表情包",
    files="fishpond/features/sticker/service.py", status="active")
add(id="sticker.pack", name="表情包导入", entry="fishpond.features.sticker.service:_install_sticker_pack",
    routes=["/api/stickers/install_pack"], tables=["stickers"], settings=["sticker_pack_url"], ui="聊天/表情包",
    files="fishpond/features/sticker/service.py", status="active")
