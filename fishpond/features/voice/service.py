"""语音模块。"""
import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
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
ZHIPU_BASE_DEFAULT = 'https://open.bigmodel.cn/api/paas/v4'
SELF_STYLE_DEFAULT = 'Q版chibi角色设定图，三头身，正面全身站姿，纯白背景，无场景无家具，粗描边、赛璐璐平涂上色、色彩明亮、画面干净'
SELF_DESC_DEFAULT = '深蓝到浅蓝渐层的及腰长发，两侧蓝色鱼鳍形状的耳朵，头顶白色蕾丝荷叶边女仆头饰、额前蓝色蕾丝发带和右侧蓝色蝴蝶结，头顶一撮呆毛；大眼蓝瞳、张嘴笑、脸颊腮红；深蓝色女仆装、白色荷叶边围裙、浅蓝色镶边、胸前深蓝蝴蝶结、围裙印蓝色小鲸鱼、裙摆两侧金色小蝴蝶结，身后一条鲸鱼尾巴；画面上不要出现任何文字、签名和边框'



def _leading_beep_seconds(pcm: bytes, sr: int = 24000) -> float:
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


def audio_mime(data: bytes) -> str:
    """按文件头判断音频类型（智谱返回 wav，Edge 返回 mp3）。"""
    b = bytes(data or b"")
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "audio/wav"
    if b[:3] == b"ID3" or b[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if b[:4] == b"OggS":
        return "audio/ogg"
    return "audio/mpeg"



class VoiceMixin:
    def voice_context(self, memory_text: str = "", slang_text: str = "") -> str:
        """给语音模型的人设/记忆/黑话上下文，让它说话带记忆和黑话的味道。"""
        parts = []
        try:
            persona = self.persona_text() or ""
            if persona:
                parts.append(persona[:1200])
        except Exception:
            pass
        if slang_text:
            parts.append(str(slang_text)[:600])
        if memory_text:
            parts.append(str(memory_text)[:800])
        return "\n".join(parts)

    def voice_wanted(self, had_voice: bool, user_id: str, user_text: str) -> bool:
        """是否需要语音回复：always=全部；voice_in=对方发语音；super=超管文字也回；含“发语音”也回。"""
        if not self.tts_on():
            return False
        mode = self.store.get_setting("voice_tts_mode", "voice_in")
        if mode == "always":
            return True
        if mode == "voice_in" and had_voice:
            return True
        # 独立的“超管文字也回语音”开关，可与上面两种模式叠加
        if (self.store.get_setting("voice_super_text", "0") == "1"
                and self.is_super_admin(user_id)):
            return True
        return bool(re.search(r"(发|来|说).{0,4}语音", user_text))

    def tts_on(self) -> bool:
        return self.store.get_setting("voice_tts_enabled", "0") == "1"

    def asr_on(self) -> bool:
        return self.store.get_setting("voice_asr_enabled", "0") == "1"

    @staticmethod
    def build_glm4voice_payload(text: str, style: str, context: str = "") -> dict:
        """glm-4-voice 走 chat/completions。

        system 里放：人设/记忆/黑话上下文 + “照这句话说”的指令 + 情绪要求。
        否则它会把待朗读内容当成对话输入，自己重新组织语言，记忆和黑话的味道就丢了。
        """
        parts = []
        if context:
            parts.append("【你的设定与记忆】\n" + context.strip()[:2000])
        parts.append("请把用户给你的这句话用上面的口吻自然说出来：保留意思，可以微调语气词，"
                     "但不要回答它、不要加新内容、不要解释。")
        parts.append("【语气要求】" + (style or "用自然、有情绪起伏的语气说话，语速稍快一点。每句话都完整说完，不要突然停下。"))
        return {
            "model": "glm-4-voice",
            "messages": [
                {"role": "system", "content": "\n".join(parts)},
                {"role": "user", "content": [{"type": "text", "text": str(text)[:800]}]},
            ],
            "stream": False,
        }

    async def synthesize_glm4voice(self, text: str, context: str = "") -> bytes:
        """智谱 GLM-4-Voice：端到端语音，能按指令控制情绪/语调/语速。"""
        key = (self.store.get_setting("voice_zvoice_key", "")
               or self.store.get_setting("voice_zhipu_key", "")
               or self.store.get_setting("image_api_key_zhipu", "") or "").strip()
        if not key:
            raise RuntimeError("智谱 Voice 未配置 API Key")
        base = (self.store.get_setting("image_zhipu_base", ZHIPU_BASE_DEFAULT) or ZHIPU_BASE_DEFAULT).rstrip("/")
        style = (self.store.get_setting("voice_zvoice_style", "用自然、有情绪起伏的语气说话，语速稍快一点。每句话都完整说完，不要突然停下。") or "").strip()
        payload = self.build_glm4voice_payload(text, style, context)
        async with self.http.post(base + "/chat/completions", json=payload,
                                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                  timeout=aiohttp.ClientTimeout(total=90)) as resp:
            raw = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"智谱 Voice HTTP {resp.status}: {raw[:160]}")
            data = json.loads(raw)
        try:
            audio_b64 = data["choices"][0]["message"]["audio"]["data"]
        except Exception:
            raise RuntimeError(f"智谱 Voice 没有返回音频: {str(data)[:160]}")
        pcm = base64.b64decode(audio_b64)
        # 实测返回的是 24kHz 单声道 16bit PCM（按 44.1k 包会因为“加速”听上去变快、音调变高）
        rate = int(self.store.get_setting("voice_zvoice_rate", "24000") or 24000)
        import io as _io
        import wave as _wave
        buf = _io.BytesIO()
        with _wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
        log.info("智谱 Voice 合成: %d 字节 PCM", len(pcm))
        return buf.getvalue()

    async def prepare_voice(self, data: bytes) -> bytes:
        """发语音前统一处理：去开头提示音、保留自然尾音、加淡入淡出，再转 mp3。

        和上一版的差别：
        - 不再把尾部静音裁光（那会让语音“突然结束”），只在末尾补 0.12s 静音
        - 开头/结尾各加淡入淡出，避免硬切产生的“咔哒”和不自然感
        - 码率 64k，比 48k 更接近自然音色
        """
        if not data:
            return data
        engine = (self.store.get_setting("voice_engine", "tts") or "tts").strip().lower()
        if engine == "breeze":
            # Breeze 没有开头提示音：不裁剪、不淡入淡出，只在结尾补 0.5 秒静音，
            # 避免最后一个字听感上“被掐断”；补静音需要重编码一次，但不做任何裁剪。
            try:
                enc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-v", "error", "-i", "pipe:0",
                    "-af", "adelay=120|120,apad=pad_dur=1.2,areverse,afade=t=in:st=0:d=0.4,areverse",
                    "-ar", "24000", "-ac", "1", "-b:a", "96k", "-f", "mp3", "pipe:1",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                out, err = await asyncio.wait_for(enc.communicate(data), timeout=30)
                if enc.returncode == 0 and out:
                    log.info("Breeze 语音补尾音 1.2s + 淡出 0.4s（%d → %d 字节）", len(data), len(out))
                    return out
                log.warning("Breeze 补尾音失败，使用原音频: %s", (err or b"")[:120])
            except Exception as e:
                log.warning("Breeze 补尾音异常，使用原音频: %s", e)
            return data
        try:
            dec = await asyncio.create_subprocess_exec(
                "ffmpeg", "-v", "error", "-i", "pipe:0", "-ar", "24000", "-ac", "1",
                "-f", "s16le", "pipe:1",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            pcm, err = await asyncio.wait_for(dec.communicate(data), timeout=30)
            if dec.returncode != 0 or not pcm:
                log.warning("语音解码失败，改用纯 Python 裁剪: %s", (err or b"")[:120])
                return self.trim_wav_pure(data)
            cut = self.leading_beep_seconds(pcm, 24000)
            if cut:
                skip = int(24000 * cut) * 2
                pcm = pcm[skip:]
                log.info("去掉开头提示音 %.2fs", cut)
            pcm = self.polish_pcm(pcm, 24000)
            enc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-v", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ar", "24000", "-ac", "1", "-b:a", "96k", "-f", "mp3", "pipe:1",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            out, err2 = await asyncio.wait_for(enc.communicate(pcm), timeout=30)
            if enc.returncode == 0 and out:
                log.info("语音转码: %d -> %d 字节", len(data), len(out))
                return out
            log.warning("语音转码失败，使用原音频: %s", (err2 or b"")[:120])
        except Exception as e:
            log.warning("语音处理异常，改用纯 Python 裁剪: %s", e)
            return self.trim_wav_pure(data)
        return data

    async def tts_speak(self, ws, mtype: str, ev: dict, text: str, context: str = "") -> bool:
        try:
            data = await self.synthesize(text, context)
            if not data:
                return False
            data = await self.prepare_voice(data)
            self.remember_outgoing(text)
            params = {"message": [{"type": "record", "data": {"file": "base64://" + base64.b64encode(data).decode()}}],
                      "message_type": mtype}
            if mtype == "group":
                params["group_id"] = ev.get("group_id")
            else:
                params["user_id"] = ev.get("user_id")
            await ws.send_str(json.dumps({"action": "send_msg", "params": params, "echo": f"v{time.time()}"}))
            log.info("语音已发送 (%d bytes)", len(data))
            return True
        except Exception as e:
            log.warning("语音发送失败: %s", e)
            return False

    async def api_voice_get(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({
            "code": 0,
            "tts_enabled": self.store.get_setting("voice_tts_enabled", "0") == "1",
            "tts_mode": self.store.get_setting("voice_tts_mode", "voice_in"),
            "super_text": self.store.get_setting("voice_super_text", "0") == "1",
            "engine": self.store.get_setting("voice_engine", "tts"),
            "voice_name": self.store.get_setting("voice_zhipu_voice", "tongtong"),
            "voice_speed": self.store.get_setting("voice_zhipu_speed", "1.0"),
            "breeze_key_masked": self.mask_key(self.store.get_setting("voice_breeze_key", "")),
            "breeze_voice": self.store.get_setting("voice_breeze_voice", ""),
            "breeze_model": self.store.get_setting("voice_breeze_model", "breeze-tts-2"),
            "zvoice_key_masked": self.mask_key(self.store.get_setting("voice_zvoice_key", "")
                                               or self.store.get_setting("voice_zhipu_key", "")
                                               or self.store.get_setting("image_api_key_zhipu", "")),
            "zvoice_style": self.store.get_setting("voice_zvoice_style", "用自然、有情绪起伏的语气说话，语速稍快一点。每句话都完整说完，不要突然停下。每句话都完整说完，不要突然停下。"),
            "asr_enabled": self.store.get_setting("voice_asr_enabled", "0") == "1",
            "asr_engine": self.store.get_setting("voice_asr_engine", "local"),
            "asr_local_model": self.store.get_setting("voice_asr_local_model", "base"),
            "asr_base": self.store.get_setting("voice_asr_base", ""),
            "asr_model": self.store.get_setting("voice_asr_model", "whisper-large-v3-turbo"),
            "asr_key_masked": self.mask_key(self.store.get_setting("voice_asr_key", "")),
            "ffmpeg_ok": bool(getattr(self, "_ffmpeg_ok", True)),
        })

    async def api_voice_audio(self, request):
        """把刚合成的试听音频按正确 Content-Type 返回，避免大 base64 在手机端解析失败。"""
        self.require_auth(request)
        token = str(request.query.get("t") or "")
        item = (getattr(self, "_tts_preview", None) or {}).get(token)
        if not item:
            raise aiohttp_web.HTTPNotFound(text="试听音频已过期，请重新生成")
        return aiohttp_web.Response(body=item["data"], content_type=item["mime"],
                                    headers={"Cache-Control": "no-store"})

    async def api_voice_diag(self, request):
        """语音诊断：同时给出“原始合成音频”和“后处理音频”，用于判断滴声来自哪里。"""
        self.require_super(request)
        text = "诊断语音一二三四五，如果你听到开头有滴声，请对比两段。"
        try:
            raw = await self.synthesize(text)
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": f"合成失败: {e}"})
        if not raw:
            return aiohttp_web.json_response({"code": -1, "message": "合成失败"})
        proc = await self.prepare_voice(raw)
        cache = getattr(self, "_tts_preview", None) or {}
        now = time.time()
        cache = {k: v for k, v in cache.items() if now - v["ts"] < 600}
        tok_raw = secrets.token_hex(8)
        tok_proc = secrets.token_hex(8)
        cache[tok_raw] = {"data": raw, "mime": audio_mime(raw), "ts": now}
        cache[tok_proc] = {"data": proc, "mime": audio_mime(proc), "ts": now}
        self._tts_preview = cache
        prefix = self.webui_prefix().rstrip("/")
        return aiohttp_web.json_response({
            "code": 0,
            "version": self.current_version(),
            "ffmpeg_ok": bool(getattr(self, "_ffmpeg_ok", True)),
            "engine": self.store.get_setting("voice_engine", "tts"),
            "raw_bytes": len(raw), "proc_bytes": len(proc),
            "raw_url": f"{prefix}/api/voice/audio?t={tok_raw}",
            "proc_url": f"{prefix}/api/voice/audio?t={tok_proc}",
        })

    async def api_voice_keytest(self, request):
        """不保存、直接用输入的 Key 打一次最小请求，提前发现 401/过期。"""
        self.require_super(request)
        data = await request.json()
        key = str(data.get("key") or "").strip()
        engine = str(data.get("engine") or "tts").strip().lower()
        if not key:
            if engine == "breeze":
                key = (self.store.get_setting("voice_breeze_key", "") or "").strip()
            else:
                key = (self.store.get_setting("voice_zvoice_key", "")
                       or self.store.get_setting("voice_zhipu_key", "")
                       or self.store.get_setting("image_api_key_zhipu", "")).strip()
        if not key:
            return aiohttp_web.json_response({"code": -1, "message": "没有可测试的 Key，请先填写"})
        base = (self.store.get_setting("image_zhipu_base", ZHIPU_BASE_DEFAULT) or ZHIPU_BASE_DEFAULT).rstrip("/")
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            if engine == "breeze":
                base = (self.store.get_setting("voice_breeze_base", "https://api.breeze.blue") or "https://api.breeze.blue").rstrip("/")
                vid = str(data.get("voice_id") or self.store.get_setting("voice_breeze_voice", "")).strip()
                if not vid:
                    return aiohttp_web.json_response({"code": -1, "message": "请先填写 Breeze Voice ID"})
                model = str(data.get("model") or self.store.get_setting("voice_breeze_model", "breeze-tts-2"))
                payload = {"text": "你好，这是语音测试。", "model_id": model, "language_code": "zh",
                           "voice_settings": {"speed": 1.0}}
                url = f"{base}/v1/text-to-speech/{vid}?output_format=mp3_24000_64&delivery=sync"
                headers = {"xi-api-key": key, "Content-Type": "application/json"}
            elif engine == "voice":
                payload = self.build_glm4voice_payload("你好", "用自然语气说话")
                url = base + "/chat/completions"
            else:
                payload = {"model": "glm-tts", "input": "你好", "voice": "tongtong", "response_format": "wav"}
                url = base + "/audio/speech"
            async with self.http.post(url, json=payload, headers=headers,
                                      timeout=aiohttp.ClientTimeout(total=30)) as resp:
                body = await resp.read()
            if resp.status == 200 and body:
                return aiohttp_web.json_response({"code": 0, "message": f"Key 可用（{len(body)} 字节音频）"})
            text = body[:160].decode("utf-8", "ignore")
            return aiohttp_web.json_response({"code": -1, "message": f"HTTP {resp.status}: {text}"})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": f"请求失败: {e}"})

    async def api_voice_preview(self, request):
        self.require_super(request)   # 试听会产生 TTS 费用，只允许超管
        data = await request.json()
        text = str(data.get("text") or "你好呀，我是大肥鱼，你听听这个声音怎么样？")[:120]
        t0 = time.time()
        try:
            audio = await self.synthesize(text)
            if not audio:
                return aiohttp_web.json_response({"code": -1, "message": "合成失败"})
            # 试听要跟正式发送完全一致：先去开头提示音，再播放
            audio = await self.prepare_voice(audio)
            mime = audio_mime(audio)
            cost = time.time() - t0
            token = secrets.token_hex(8)
            cache = getattr(self, "_tts_preview", None) or {}
            now = time.time()
            cache = {k: v for k, v in cache.items() if now - v["ts"] < 600}
            cache[token] = {"data": audio, "mime": mime, "ts": now}
            if len(cache) > 6:
                for k in sorted(cache, key=lambda x: cache[x]["ts"])[:-6]:
                    cache.pop(k, None)
            self._tts_preview = cache
            log.info("试听完成 用时=%.1fs 大小=%d", cost, len(audio))
            prefix = self.webui_prefix().rstrip("/")
            return aiohttp_web.json_response({"code": 0, "mime": mime, "bytes": len(audio),
                                              "seconds": round(cost, 1),
                                              "url": f"{prefix}/api/voice/audio?t={token}"})
        except Exception as e:
            log.warning("试听合成失败: %s", e)
            return aiohttp_web.json_response({"code": -1, "message": f"合成失败: {e}"})

    async def api_voice_config(self, request):
        self.require_super(request)   # 写配置统一要求超管
        data = await request.json()
        if "tts_enabled" in data:
            self.store.set_setting("voice_tts_enabled", "1" if data.get("tts_enabled") else "0")
        if "asr_enabled" in data:
            self.store.set_setting("voice_asr_enabled", "1" if data.get("asr_enabled") else "0")
        if "super_text" in data:
            self.store.set_setting("voice_super_text", "1" if data.get("super_text") else "0")
        if data.get("tts_mode") in ("voice_in", "always"):
            self.store.set_setting("voice_tts_mode", data["tts_mode"])
        # 兼容旧页面的字段名：zhipu_key / voice_key 都当成语音专用 Key
        for kk in ("zvoice_key", "zhipu_key", "voice_key"):
            if kk in data:
                zk = str(data.get(kk) or "").strip()
                if zk:
                    self.store.set_setting("voice_zvoice_key", zk[:200])
                    log.info("语音 Key 已保存（字段 %s，长度 %d）", kk, len(zk))
        if "breeze_key" in data:
            bk = str(data.get("breeze_key") or "").strip()
            if bk:
                self.store.set_setting("voice_breeze_key", bk[:200])
        if "breeze_voice" in data:
            bv = str(data.get("breeze_voice") or "").strip()
            self.store.set_setting("voice_breeze_voice", bv[:120])
        if "breeze_model" in data:
            bm = str(data.get("breeze_model") or "breeze-tts-2").strip()
            self.store.set_setting("voice_breeze_model", bm[:60])
        if data.get("engine") in ("tts", "voice", "breeze"):
            self.store.set_setting("voice_engine", data["engine"])
        if "voice_name" in data:
            vn = str(data.get("voice_name") or "tongtong").strip()
            if vn:
                self.store.set_setting("voice_zhipu_voice", vn[:40])
        if "voice_speed" in data:
            try:
                sp = max(0.8, min(1.3, float(data.get("voice_speed"))))
                self.store.set_setting("voice_zhipu_speed", f"{sp:.2f}")
            except Exception:
                pass
        if "zvoice_style" in data:
            self.store.set_setting("voice_zvoice_style",
                                   str(data.get("zvoice_style") or "").strip()[:300]
                                   or "用自然、有情绪起伏的语气说话，语速稍快一点。每句话都完整说完，不要突然停下。每句话都完整说完，不要突然停下。")
        if data.get("asr_engine") in ("local", "api"):
            self.store.set_setting("voice_asr_engine", data["asr_engine"])
        if "asr_local_model" in data:
            m = str(data.get("asr_local_model") or "base").strip()
            if m:
                self.store.set_setting("voice_asr_local_model", m)
        if "asr_base" in data:
            self.store.set_setting("voice_asr_base", str(data.get("asr_base") or "").strip().rstrip("/"))
        if "asr_model" in data:
            self.store.set_setting("voice_asr_model", str(data.get("asr_model") or "").strip())
        if "asr_key" in data:
            k = str(data.get("asr_key") or "").strip()
            if k:
                self.store.set_setting("voice_asr_key", k)
        masked = self.mask_key(self.store.get_setting("voice_zvoice_key", "")
                               or self.store.get_setting("voice_zhipu_key", ""))
        return aiohttp_web.json_response({"code": 0,
                                          "engine": self.store.get_setting("voice_engine", "tts"),
                                          "voice_key_masked": masked})


    def _load_whisper(self, size: str):
        from faster_whisper import WhisperModel

        return WhisperModel(size, device="cpu", compute_type="int8")

    async def transcribe_local(self, data: bytes) -> str | None:
        import numpy as np

        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            self.store.set_setting("voice_asr_enabled", "0")
            log.warning("未安装 faster-whisper，已自动禁用语音识别")
            return None
        size = self.store.get_setting("voice_asr_local_model", "base") or "base"
        loop = asyncio.get_running_loop()
        try:
            if getattr(self, "_whisper", None) is None or getattr(self, "_whisper_size", None) != size:
                self._whisper = await loop.run_in_executor(None, self._load_whisper, size)
                self._whisper_size = size
        except Exception as e:
            self.store.set_setting("voice_asr_enabled", "0")
            log.warning("本地语音模型不可用（%s），已自动禁用语音识别", e)
            return None
        try:
            raw = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["ffmpeg", "-v", "quiet", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
                    input=data, capture_output=True,
                ).stdout,
            )
            if not raw:
                return None
            audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0

            def _run():
                segs, _ = self._whisper.transcribe(
                    audio, language="zh", beam_size=1,
                    initial_prompt="以下是普通话内容，请用简体中文转写。",
                )
                return "".join(seg.text for seg in segs).strip()

            text = await loop.run_in_executor(None, _run)
            return text or None
        except Exception as e:
            log.warning("本地语音识别失败: %s", e)
            return None

    async def transcribe(self, url: str) -> str | None:
        try:
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    return None
                data = await r.read()
        except Exception as e:
            log.warning("语音下载失败: %s", e)
            return None
        if not data:
            return None
        if self.store.get_setting("voice_asr_engine", "local") == "local":
            return await self.transcribe_local(data)
        base = (self.store.get_setting("voice_asr_base", "") or "").rstrip("/")
        key = self.store.get_setting("voice_asr_key", "")
        if not key and "bigmodel.cn" in base:
            # 智谱 ASR 与生图/语音合成共用一个 Key，省一次填写
            key = (self.store.get_setting("voice_zhipu_key", "")
                   or self.store.get_setting("image_api_key_zhipu", "") or "").strip()
        model = self.store.get_setting("voice_asr_model", "whisper-1")
        if not base or not key:
            return None
        mp3 = data
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", "pipe:0", "-f", "mp3", "pipe:1",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate(data)
            if out:
                mp3 = out
        except Exception as e:
            log.warning("语音转码失败: %s", e)
        try:
            form = aiohttp.FormData()
            form.add_field("model", model)
            form.add_field("file", mp3, filename="audio.mp3", content_type="audio/mpeg")
            async with self.http.post(
                f"{base}/audio/transcriptions",
                data=form,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    log.warning("语音识别失败 HTTP %s", resp.status)
                    return None
                d = await resp.json(content_type=None)
                text = (d.get("text") or "").strip()
                return text or None
        except Exception as e:
            log.warning("语音识别异常: %s", e)
            return None

    async def synthesize_breeze(self, text: str) -> bytes:
        """Breeze Blue TTS：POST /v1/text-to-speech/{voice_id}，xi-api-key 鉴权。"""
        key = (self.store.get_setting("voice_breeze_key", "") or "").strip()
        vid = (self.store.get_setting("voice_breeze_voice", "") or "").strip()
        if not key:
            raise RuntimeError("Breeze 未配置 API Key（后台语音页填写）")
        if not vid:
            raise RuntimeError("Breeze 未配置 Voice ID（在 Breeze 控制台复制 voc_ 开头的 ID）")
        base = (self.store.get_setting("voice_breeze_base", "https://api.breeze.blue") or "https://api.breeze.blue").rstrip("/")
        model = (self.store.get_setting("voice_breeze_model", "breeze-tts-2") or "breeze-tts-2").strip()
        try:
            speed = float(self.store.get_setting("voice_zhipu_speed", "1.0") or 1.0)
        except Exception:
            speed = 1.0
        speed = max(0.5, min(2.0, speed))
        t = str(text)
        if len(t) > 900:
            cut = max(t.rfind(ch, 0, 900) for ch in "。！？!?\n")
            t = t[:cut + 1] if cut > 300 else t[:900]
        if t and t[-1] not in "。！？!?.…":
            t += "。"   # 补句号，避免模型把最后一个字读得仓促
        body = {"text": t, "model_id": model, "language_code": "zh",
                "voice_settings": {"speed": speed}}
        style = (self.store.get_setting("voice_zvoice_style", "") or "").strip()
        if style:
            body["instructions"] = style[:300]
        url = f"{base}/v1/text-to-speech/{vid}?output_format=mp3_24000_64&delivery=sync"
        async with self.http.post(url, json=body, headers={"xi-api-key": key},
                                  timeout=aiohttp.ClientTimeout(total=90)) as resp:
            data = await resp.read()
        if resp.status != 200 or not data:
            raise RuntimeError(f"Breeze TTS HTTP {resp.status}: {data[:120]!r}")
        return data

    async def synthesize(self, text: str, context: str = "") -> bytes:
        """语音合成入口。

        - tts（默认）：智谱 GLM-TTS，逐字朗读、内容准确
        - voice：智谱 glm-4-voice 端到端，情绪更自然，但可能改措辞
        """
        engine = (self.store.get_setting("voice_engine", "tts") or "tts").strip().lower()

        async def primary():
            if engine == "voice":
                return await self.synthesize_glm4voice(text, context)
            if engine == "breeze":
                return await self.synthesize_breeze(text)
            voice = (self.store.get_setting("voice_zhipu_voice", "tongtong") or "tongtong").strip()
            return await self.synthesize_zhipu(text, voice)

        try:
            return await primary()
        except Exception as e:
            log.warning("主语音引擎失败，自动切换备用: %s", e)
        try:
            return await self.synthesize_edge(text)
        except Exception as e:
            log.warning("备用 edge-tts 失败: %s", e)
        if engine != "tts":
            try:
                return await self.synthesize_zhipu(text, (self.store.get_setting("voice_zhipu_voice", "tongtong") or "tongtong").strip())
            except Exception as e:
                log.warning("智谱备用也失败: %s", e)
        raise RuntimeError("语音合成失败：主引擎和备用都不可用")

    async def synthesize_edge(self, text: str) -> bytes:
        """免费备用：edge-tts，主引擎 429/504 时兜底。"""
        import edge_tts
        voice = (self.store.get_setting("voice_tts_voice", "zh-CN-XiaoxiaoNeural")
                 or "zh-CN-XiaoxiaoNeural").strip()
        out = bytearray()
        com = edge_tts.Communicate(str(text)[:300], voice)
        async for chunk in com.stream():
            if chunk.get("type") == "audio":
                out.extend(chunk.get("data") or b"")
        if not out:
            raise RuntimeError("edge-tts 没有返回音频")
        log.info("edge-tts 兜底合成 %d 字节", len(out))
        return bytes(out)

    async def synthesize_zhipu(self, text: str, voice: str = "") -> bytes:
        # 与语音页保存的 Key 保持一致：语音专用 → 旧语音字段 → 生图 Key
        key = (self.store.get_setting("voice_zvoice_key", "")
               or self.store.get_setting("voice_zhipu_key", "")
               or self.store.get_setting("image_api_key_zhipu", "") or "").strip()
        if not key:
            raise RuntimeError("智谱 TTS 未配置 API Key（请在语音页填「智谱 Key」，或复用生图 Key）")
        base = (self.store.get_setting("image_zhipu_base", ZHIPU_BASE_DEFAULT) or ZHIPU_BASE_DEFAULT).rstrip("/")
        model = (self.store.get_setting("voice_zhipu_model", "glm-tts") or "glm-tts").strip()
        voice_id = (voice or self.store.get_setting("voice_zhipu_voice", "tongtong") or "tongtong").strip()
        try:
            speed = float(self.store.get_setting("voice_zhipu_speed", "1.0") or 1.0)
        except Exception:
            speed = 1.0
        speed = max(0.8, min(1.3, speed))
        payload = {"model": model, "input": str(text)[:300], "voice": voice_id,
                   "speed": speed, "volume": 1.0, "response_format": "wav"}
        async with self.http.post(base + "/audio/speech", json=payload,
                                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                  timeout=aiohttp.ClientTimeout(total=60)) as resp:
            raw = await resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if resp.status != 200:
                raise RuntimeError(f"智谱 TTS HTTP {resp.status}: {raw[:120]}")
        if ctype.startswith("audio"):
            return raw
        # 少数情况返回 JSON（流式 base64）
        try:
            d = json.loads(raw)
            content = d["choices"][0]["delta"]["content"]
            import base64 as _b64
            return _b64.b64decode(content)
        except Exception:
            raise RuntimeError(f"智谱 TTS 返回异常: {raw[:120]}")

    @staticmethod
    def trim_wav_pure(data: bytes) -> bytes:
        """没有 ffmpeg 时的兜底：直接解析 WAV，裁掉开头提示音并补静音（输出仍是 wav）。"""
        import wave, io, struct
        try:
            with wave.open(io.BytesIO(data), "rb") as w:
                ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
                raw = w.readframes(n)
        except Exception:
            return data
        if sw != 2 or ch != 1:
            return data
        cut = _leading_beep_seconds(raw, sr)
        if not cut:
            return data
        pcm = raw[int(sr * cut) * 2:]
        tail = b"\x00\x00" * int(sr * 0.3)
        out = io.BytesIO()
        with wave.open(out, "wb") as wo:
            wo.setnchannels(1)
            wo.setsampwidth(2)
            wo.setframerate(sr)
            wo.writeframes(pcm + tail)
        return out.getvalue()

    @staticmethod
    def polish_pcm(pcm: bytes, sr: int = 24000) -> bytes:
        """淡入、保留自然尾音、末尾补静音，避免“最后一个字只说了一半”。

        关键点：
        - 最后一个有声样本之后**多留 0.3 秒**（保留字的自然衰减），而不是切在字中间
        - 淡出只作用于补出来的静音段，不削掉真实语音
        - 末尾补 0.5 秒静音：更像真人说完停顿一下，也保证 mp3 编码器把最后几帧刷出来
        """
        try:
            import numpy as np
        except Exception:
            return pcm
        if not pcm:
            return pcm
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        thr = 200.0
        loud = np.where(np.abs(x) > thr)[0]
        if loud.size:
            end = int(loud[-1]) + int(sr * 0.30)
            if end < len(x):
                x = x[:end]
        fade_in = int(sr * 0.01)
        if len(x) > fade_in + 1:
            x[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
        tail = np.zeros(int(sr * 0.50), dtype=np.float32)
        x = np.concatenate([x, tail])
        fade_out = int(sr * 0.03)
        if len(x) > fade_out:
            x[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
        return np.clip(x, -32768, 32767).astype(np.int16).tobytes()


add(id="voice.core", name="语音",
    entry="fishpond.features.voice.service:voice_context",
    routes=["/api/voice/*"] if "voice" == "voice" else [], tables=[],
    settings=["voice_*"], ui="机器人/语音",
    files="fishpond/features/voice/service.py", status="active")
