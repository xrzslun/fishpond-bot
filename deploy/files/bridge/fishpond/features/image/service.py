"""生图模块。"""
import asyncio
import base64
import hashlib
import json
import os
import random
import re
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
IMAGE_SF_MODELS = {'Tongyi-MAI/Z-Image-Turbo', 'Tongyi-MAI/Z-Image', 'Kwai-Kolors/Kolors', 'Qwen/Qwen-Image'}
IMAGE_ZHIPU_MODELS = {'glm-image', 'cogview-4-250304', 'cogview-4', 'cogview-3-flash'}
SELF_STYLE_DEFAULT = 'Q版chibi角色设定图，三头身，正面全身站姿，纯白背景，无场景无家具，粗描边、赛璐璐平涂上色、色彩明亮、画面干净'
SELF_DESC_DEFAULT = '深蓝到浅蓝渐层的及腰长发，两侧蓝色鱼鳍形状的耳朵，头顶白色蕾丝荷叶边女仆头饰、额前蓝色蕾丝发带和右侧蓝色蝴蝶结，头顶一撮呆毛；大眼蓝瞳、张嘴笑、脸颊腮红；深蓝色女仆装、白色荷叶边围裙、浅蓝色镶边、胸前深蓝蝴蝶结、围裙印蓝色小鲸鱼、裙摆两侧金色小蝴蝶结，身后一条鲸鱼尾巴；画面上不要出现任何文字、签名和边框'
SELF_EDIT_MODEL_DEFAULT = 'Qwen/Qwen-Image-Edit'
SELF_EDIT_PROMPT_DEFAULT = '保持参考图里这个角色的外观与画风不变，整理成干净的Q版chibi角色立绘：三头身、头大身小、正面全身站姿、纯白背景、粗描边平涂上色；保留深蓝到浅蓝渐变长发、浅灰色鱼鳍状耳朵、白色蕾丝女仆头巾、右侧浅蓝蝴蝶结、深蓝女仆装、白色围裙上的蓝色小鲸鱼、裙摆金色刺绣与金色小蝴蝶结、身后的鲸鱼尾巴；表情张嘴笑、眼睛大而有高光'
SELF_NEGATIVE_DEFAULT = '写实,照片,真人,3D渲染,厚涂,CG,坐姿,躺姿,沙发,床,室内场景,家具,地面阴影,文字,水印,AI生成,签名,边框,畸形,多余手指,多余肢体,肢体融合,恐怖'
ZHIPU_BASE_DEFAULT = 'https://open.bigmodel.cn/api/paas/v4'



SELF_HINTS = ("AI画像", "ai画像", "自画像", "你自己", "你本人", "你长什么样", "你的样子",
              "你认为的自己", "你现在的样子", "自我画像")


def is_self_image(prompt):
    """判断这次生图是不是在画「AI 自己」。只认明确的指代，避免误伤普通请求。"""
    t = str(prompt or "")
    if any(k in t for k in SELF_HINTS):
        return True
    flat = re.sub(r"\s+", "", t).lower()
    # 「画AI」「画一张AI」「画个ai」，以及「画一个AI的你」
    if re.search(r"画[一1]?[张个幅只]?(ai|a\.i\.)", flat):
        return True
    # 「画你」「画一个你」这类；排除「画你们」「画你的房间」「画你说的那个场景」
    return bool(re.search(r"画[一1]?[张个幅只]?\s*你(?![们的])(?![说讲刚昨上发])", t))


def self_image_extra(prompt):
    """去掉指代后剩下的具体要求，例如「画你自己在你的鱼缸里游泳」→「在你的鱼缸里游泳」。"""
    t = str(prompt or "")
    for k in SELF_HINTS:
        t = t.replace(k, " ")
    t = re.sub(r"(?i)\bai\b|ＡＩ|AI", " ", t)
    t = re.sub(r"^(帮我画|给我画|画|生成|来)[一1]?[张个幅只]?\s*", "", t.strip())
    t = re.sub(r"^(你|的)\s*", "", t.strip())
    t = re.sub(r"\s+", " ", t).strip(" ，,。.；;的")
    return t


def build_self_image_prompt(style, desc, extra=""):
    """拼自画像提示词：画风锁定 + 外观 + （可选）用户的具体画面要求。"""
    parts = []
    st = str(style or "").strip()
    ds = str(desc or "").strip()
    if st:
        parts.append(st)
    if ds:
        parts.append(ds)
    ex = str(extra or "").strip()
    if ex:
        parts.append(f"画面内容：{ex}；人物必须保持上面的角色外观和画风")
    return "；".join(parts)[:400]



class ImageMixin:
    async def prepare_images(self, urls: list[str]) -> list[str]:
        out = []
        if not self.vision_enabled:
            return out
        for u in urls[: self.max_images]:
            if not await self.is_public_url(u):
                log.warning("拒绝下载内网/非法图片地址: %s", str(u)[:80])
                continue
            try:
                async with self.http.get(u, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.read()
            except Exception as e:
                log.warning("图片下载失败: %s", e)
                continue
            if not data or len(data) > self.max_bytes:
                continue
            out.append(self.encode_image(data))
        return out

    def encode_image(self, data: bytes) -> str:
        try:
            import io

            from PIL import Image

            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((self.max_side, self.max_side))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            data = buf.getvalue()
            mime = "image/jpeg"
        except Exception:
            mime = "image/png"
        return f"data:{mime};base64," + base64.b64encode(data).decode()

    def image_scope_ok(self, mtype, gid, uid, is_super):
        scope = self.store.get_setting("image_scope", "all") or "all"
        if scope == "all":
            return True
        if scope == "super":
            return bool(is_super)
        users = self.store.users()
        groups = self.store.groups()
        if mtype == "group" and groups and str(gid) in groups:
            return True
        return str(uid) in users

    async def enhance_image_prompt(self, prompt, uid=None, is_super=False):
        p = str(prompt or "")
        # 画「AI 自己」：走固定模板，不经过 LLM 改写，避免被“自述场景”带偏成生活照。
        # 这条分支独立于「提示词优化」开关（关掉该开关也要保持固定形象）。
        # 普通生图不进入这个分支，保持原有行为。
        if is_self_image(p):
            style = (self.store.get_setting("image_self_style", SELF_STYLE_DEFAULT) or "").strip()
            desc = (self.store.get_setting("image_self_desc", SELF_DESC_DEFAULT) or "").strip()
            out = build_self_image_prompt(style, desc, self_image_extra(p))
            log.info("自画像提示词: %s", out)
            return out
        # 以下是普通生图：优化开关关掉就原样返回，行为与 3.5.5 一致
        if self.store.get_setting("image_enhance", "1") != "1":
            return p
        ctx = []
        user_ref = any(k in p for k in ("我自己", "画我", "我的样子", "本人", "画一个我", "老大"))
        if user_ref and uid:
            try:
                rows = self.store.mem_by_owner(str(uid), None, 12, all_levels=True)
                noise = ("关键词", "触发词", "提示词", "后台", "部署", "API", "token", "观察者", "FishPond")
                mem = [r["content"] for r in rows if not any(w in (r["content"] or "") for w in noise)][:8]
                if mem:
                    ctx.append("【关于用户的资料】" + "；".join(mem)[:600])
            except Exception:
                pass
        try:
            slang = self.store.slang_find(p)[:3]
            if slang:
                ctx.append("【网络用语】" + "；".join(f"{r['term']}={r.get('meaning','')}" for r in slang)[:300])
        except Exception:
            pass
        system = ("你是文生图提示词工程师。把用户请求改写成一条中文画面描述，包含主体、数量、动作、"
                  "空间关系、环境、镜头、光线、风格；保留原意，不要解释、不要引号，最多 150 字。只输出提示词。")
        if ctx:
            system += "\n参考资料（必须遵守，尤其是外观/身份）：\n" + "\n".join(ctx)
        try:
            out = await self.llm_complete(system, p[:300], max_tokens=260, temperature=0.6)
            out = re.sub(r"\s+", " ", str(out or "")).strip().strip('"“”')
            out = out[:150].rstrip("，,。.、 ")
            out = re.sub(r"^(画面描述|提示词|描述)[：:]\s*", "", out)
            return out or prompt
        except Exception:
            return prompt

    async def _image_call(self, base, key, payload, timeout=180):
        """调硅基流动出图接口并把结果读成 bytes。"""
        async with self.http.post(base + "/images/generations", json=payload,
                                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                  timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            raw = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"生图接口 HTTP {resp.status}: {raw[:160]}")
            data = json.loads(raw)
        items = data.get("images") or data.get("data") or []
        if not items:
            raise RuntimeError("生图接口没有返回图片")
        item = items[0] if isinstance(items[0], dict) else {"url": items[0]}
        if item.get("b64_json"):
            import base64 as _b64
            return _b64.b64decode(item["b64_json"])
        url = item.get("url") or ""
        if not url:
            raise RuntimeError("生图接口没有返回图片地址")
        async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=90)) as r2:
            if r2.status != 200:
                raise RuntimeError(f"下载图片失败 HTTP {r2.status}")
            img = await r2.read()
        if not img:
            raise RuntimeError("下载图片为空")
        return img

    async def generate_image(self, prompt, enhance=True, uid=None, is_super=False):
        provider = (self.store.get_setting("image_provider", "siliconflow") or "siliconflow").strip().lower()
        # 硅基流动（也用于 AI画像的图生图）
        sf_base = (self.store.get_setting("image_base_url", "https://api.siliconflow.cn/v1") or "").rstrip("/")
        sf_key = (self.store.get_setting("image_api_key", "") or "").strip()
        # 智谱
        zp_base = (self.store.get_setting("image_zhipu_base", ZHIPU_BASE_DEFAULT) or ZHIPU_BASE_DEFAULT).rstrip("/")
        zp_key = (self.store.get_setting("image_api_key_zhipu", "") or "").strip()
        model = (self.store.get_setting("image_model", "Tongyi-MAI/Z-Image-Turbo") or "").strip()
        size = (self.store.get_setting("image_size", "1024x1024") or "1024x1024").strip()
        # 供应商切换后可能残留另一家的模型名/尺寸，这里兜底纠正，避免直接报"模型不存在"
        if provider == "zhipu":
            if model not in IMAGE_ZHIPU_MODELS:
                log.warning("模型 %s 不属于智谱，自动改用 glm-image", model)
                model, size = "glm-image", "1280x1280"
        elif model not in IMAGE_SF_MODELS:
            log.warning("模型 %s 不属于硅基流动，自动改用 Qwen/Qwen-Image", model)
            model, size = "Qwen/Qwen-Image", "1024x1024"
        self_pic = is_self_image(prompt)
        raw_prompt = str(prompt or "")
        # 自画像优先「参考图 → 图生图」，形象最稳；没配参考图或调用失败时退回文字模板。
        ref = (self.store.get_setting("image_self_ref", "") or "").strip()
        if self_pic and ref:
            try:
                edit_model = (self.store.get_setting("image_self_edit_model", SELF_EDIT_MODEL_DEFAULT)
                              or SELF_EDIT_MODEL_DEFAULT).strip()
                edit_prompt = (self.store.get_setting("image_self_edit_prompt", SELF_EDIT_PROMPT_DEFAULT) or "").strip()
                extra = self_image_extra(raw_prompt)
                if extra:
                    edit_prompt += f"；画面内容：{extra}；人物必须保持参考图里的外观和画风"
                image_input = ref
                if not ref.startswith("http"):
                    p = Path(ref)
                    if not p.is_file():
                        raise RuntimeError(f"参考图不存在: {ref}")
                    b = p.read_bytes()
                    mime = "image/png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
                    import base64 as _b64
                    image_input = f"data:{mime};base64," + _b64.b64encode(b).decode()
                img = await self._image_call(sf_base, sf_key, {
                    "model": edit_model,
                    "prompt": edit_prompt[:800],
                    "image": image_input,
                    "image_size": size,
                    "batch_size": 1,
                }, timeout=240)
                log.info("自画像图生图成功: %s", edit_model)
                return img
            except Exception as e:
                log.warning("自画像图生图失败，回退文字模板: %s", e)
        if enhance:
            prompt = await self.enhance_image_prompt(prompt, uid=uid, is_super=is_super)
        # 智谱：字段是 size/quality，没有步数和负面提示词
        if provider == "zhipu":
            if not zp_key:
                raise RuntimeError("还没有配置智谱 API Key")
            payload = {
                "model": model,
                "prompt": str(prompt)[:1000],
                "size": size,
                "quality": "hd" if model == "glm-image" else "standard",
                "watermark_enabled": False,
            }
            log.info("智谱生图: model=%s size=%s", model, size)
            return await self._image_call(zp_base, zp_key, payload, timeout=240)
        if not sf_key:
            raise RuntimeError("还没有配置硅基流动 API Key")
        low = model.lower()
        default_steps = 8 if ("turbo" in low or "schnell" in low) else 25
        try:
            steps = max(1, min(50, int(self.store.get_setting("image_steps", str(default_steps)) or default_steps)))
        except Exception:
            steps = default_steps
        # Kolors/Qwen 这类模型步数太低会出畸形、肢体融合
        if "turbo" not in low and "schnell" not in low and steps < 20:
            steps = 20
        payload = {"model": model, "prompt": str(prompt)[:800], "image_size": size,
                   "batch_size": 1, "num_inference_steps": steps}
        neg_key = "image_self_negative" if self_pic else "image_negative"
        neg_default = SELF_NEGATIVE_DEFAULT if self_pic else "低质量,模糊,畸形,多余肢体,肢体融合,文字,水印"
        neg = (self.store.get_setting(neg_key, neg_default) or "").strip()
        if neg and "turbo" not in low and "schnell" not in low and "flux" not in low:
            payload["negative_prompt"] = neg
        return await self._image_call(sf_base, sf_key, payload)

    async def send_image_bytes(self, ws, mtype, ev, data):
        import base64 as _b64
        b64 = _b64.b64encode(data).decode()
        seg = {"type": "image", "data": {"file": "base64://" + b64}}
        if mtype == "group":
            action, params = "send_group_msg", {"group_id": ev.get("group_id"), "message": [seg]}
        else:
            action, params = "send_private_msg", {"user_id": ev.get("user_id"), "message": [seg]}
        res = await self.onebot_call(ws, action, params, timeout=30)
        return bool(res) and (res.get("status") in ("ok", "async") or res.get("retcode") == 0)

    def image_help_text(self, is_super=False):
        """生图用法说明，给用户看，不耗额度。"""
        try:
            limit = max(1, int(self.store.get_setting("image_daily_limit", "5") or 5))
        except Exception:
            limit = 5
        unlimited = self.store.get_setting("image_super_unlimited", "1") == "1"
        quota = "你这边不限张数" if (is_super and unlimited) else f"每天 {limit} 张"
        return (
            "画图这样用：\n"
            "· 群里 @我 说「画图 一只猫在键盘上睡觉」，私聊直接说「画图 …」也行\n"
            "· 越具体越准：主体 + 动作 + 场景 + 风格，比如「画图 一只橘猫趴在窗台晒太阳，水彩风」\n"
            "· 想画我的固定形象，就说「画AI」或「画一张AI」\n"
            f"· 额度：{quota}，只算成功的图，失败不扣\n"
            "· 画失败我会说原因；想再看这段说明，说「画图帮助」"
        )

    async def handle_image(self, ws, ev, mtype, uid, prompt, is_super):
        if self.store.get_setting("image_enabled", "0") != "1":
            await self.send(ws, mtype, ev, "生图功能还没开，让老大去后台打开。", record_convo=False)
            return
        gid = str(ev.get("group_id") or "") if mtype == "group" else ""
        if not self.image_scope_ok(mtype, gid, uid, is_super):
            await self.send(ws, mtype, ev, "你这边没有生图权限。", record_convo=False)
            return
        try:
            limit = max(1, int(self.store.get_setting("image_daily_limit", "5") or 5))
        except Exception:
            limit = 5
        super_unlimited = self.store.get_setting("image_super_unlimited", "1") == "1"
        if not (is_super and super_unlimited) and self.store.image_count_today(uid) >= limit:
            await self.send(ws, mtype, ev, f"你今天已经画了 {limit} 张，明天再来吧。想看用法说「画图帮助」。", record_convo=False)
            return
        if len(prompt.strip()) < 1:
            await self.send(ws, mtype, ev, "想画什么？说具体点，比如「画图 一只猫在键盘上睡觉」。", record_convo=False)
            return
        await self.send(ws, mtype, ev, random.choice(["在画了，等一下…", "好，开画，稍等～", "收到，正在生成…"]), record_convo=False)
        rid = self.store.image_log(uid, gid, prompt)
        try:
            img = await self.generate_image(prompt, uid=uid, is_super=is_super)
            ok = await self.send_image_bytes(ws, mtype, ev, img)
            self.store.image_finish(rid, bool(ok))
            if not ok:
                await self.send(ws, mtype, ev, "图生成出来了，但发送失败，稍后再试。", record_convo=False)
        except Exception as e:
            self.store.image_finish(rid, False)
            log.warning("生图失败: %s", e)
            await self.send(ws, mtype, ev, f"画失败了：{str(e)[:100]}", record_convo=False)

    @staticmethod
    def image_command_prompt(user_text: str) -> str:
        """识别「画图 xxx」类指令，返回真正要画的描述；不是画图指令则返回空串。"""
        t = str(user_text or "").strip()
        if not t:
            return ""
        m = re.match(r"^(?:画图|画一张|画一幅|画个|画一只|画一个|画张|画幅|画一下|画下|帮我画|给我画|"
                     r"生成图片|生成一张|来张图|来一张|"
                     r"画(?!风|面|质|师|家|笔|布|法)(?:一只|一个|一张|一幅|个|张|幅|只|下)?)"
                     r"\s*[：:，,]?\s*(.+)$", t)
        if not m:
            return ""
        prompt = re.sub(r"^(一只|一个|一张|一幅|个|张|幅|只)\s*", "", m.group(1).strip())
        return prompt

    @staticmethod
    def image_help_requested(user_text: str) -> bool:
        """是否在问「画图怎么用 / 生图帮助」。"""
        th = re.sub(r"\s+", "", str(user_text or "")).lower()
        if not th:
            return False
        return bool(re.search(r"(画图|生图|画ai|ai画像|自画像)(帮助|说明|怎么用|怎么画|怎么弄|用法|help)", th)
                    or re.search(r"(怎么|如何)(画图|生图|画ai|ai画像)", th)
                    or th in ("help", "画图help"))

    async def api_image_get(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("image_enabled", "0") == "1",
            "base_url": self.store.get_setting("image_base_url", "https://api.siliconflow.cn/v1") or "",
            "masked": self.mask_key(self.store.get_setting("image_api_key", "") or ""),
            "provider": (self.store.get_setting("image_provider", "siliconflow") or "siliconflow"),
            "zhipu_base": self.store.get_setting("image_zhipu_base", ZHIPU_BASE_DEFAULT) or "",
            "zhipu_masked": self.mask_key(self.store.get_setting("image_api_key_zhipu", "") or ""),
            "model": self.store.get_setting("image_model", "Tongyi-MAI/Z-Image-Turbo") or "",
            "size": self.store.get_setting("image_size", "1024x1024") or "1024x1024",
            "steps": int(self.store.get_setting("image_steps", "8") or 8),
            "negative": self.store.get_setting("image_negative", "低质量,模糊,畸形,多余肢体,肢体融合,文字,水印") or "",
            "enhance": self.store.get_setting("image_enhance", "1") == "1",
            "self_desc": self.store.get_setting("image_self_desc", SELF_DESC_DEFAULT) or "",
            "self_style": self.store.get_setting("image_self_style", SELF_STYLE_DEFAULT) or "",
            "self_negative": self.store.get_setting("image_self_negative", SELF_NEGATIVE_DEFAULT) or "",
            "self_ref": self.store.get_setting("image_self_ref", "") or "",
            "self_edit_model": self.store.get_setting("image_self_edit_model", SELF_EDIT_MODEL_DEFAULT) or "",
            "self_edit_prompt": self.store.get_setting("image_self_edit_prompt", SELF_EDIT_PROMPT_DEFAULT) or "",
            "daily_limit": int(self.store.get_setting("image_daily_limit", "5") or 5),
            "scope": self.store.get_setting("image_scope", "all") or "all",
            "super_unlimited": self.store.get_setting("image_super_unlimited", "1") == "1",
        })

    async def api_image_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("image_enabled", "1" if data.get("enabled") else "0")
        for k, key in (("base_url", "image_base_url"), ("model", "image_model"), ("size", "image_size")):
            if k in data:
                self.store.set_setting(key, str(data.get(k) or "").strip()[:200])
        if "api_key" in data:
            k = str(data.get("api_key") or "").strip()
            if k:
                self.store.set_setting("image_api_key", k[:200])
        if "provider" in data:
            pv = str(data.get("provider") or "").strip().lower()
            self.store.set_setting("image_provider", "zhipu" if pv == "zhipu" else "siliconflow")
        if "zhipu_base" in data:
            self.store.set_setting("image_zhipu_base", str(data.get("zhipu_base") or "").strip()[:200])
        if "zhipu_key" in data:
            zk = str(data.get("zhipu_key") or "").strip()
            if zk:
                self.store.set_setting("image_api_key_zhipu", zk[:200])
        if "steps" in data:
            try:
                self.store.set_setting("image_steps", str(max(1, min(50, int(data.get("steps"))))))
            except Exception:
                pass
        if "negative" in data:
            self.store.set_setting("image_negative", str(data.get("negative") or "")[:300])
        if "enhance" in data:
            self.store.set_setting("image_enhance", "1" if data.get("enhance") else "0")
        if "self_desc" in data:
            self.store.set_setting("image_self_desc", str(data.get("self_desc") or "").strip()[:400])
        if "self_style" in data:
            self.store.set_setting("image_self_style", str(data.get("self_style") or "").strip()[:400])
        if "self_negative" in data:
            self.store.set_setting("image_self_negative", str(data.get("self_negative") or "").strip()[:300])
        if "self_ref" in data:
            self.store.set_setting("image_self_ref", str(data.get("self_ref") or "").strip()[:500])
        if "self_edit_model" in data:
            self.store.set_setting("image_self_edit_model", str(data.get("self_edit_model") or "").strip()[:200])
        if "self_edit_prompt" in data:
            self.store.set_setting("image_self_edit_prompt", str(data.get("self_edit_prompt") or "").strip()[:800])
        if "daily_limit" in data:
            try:
                self.store.set_setting("image_daily_limit", str(max(1, min(1000, int(data.get("daily_limit"))))))
            except Exception:
                pass
        if "super_unlimited" in data:
            self.store.set_setting("image_super_unlimited", "1" if data.get("super_unlimited") else "0")
        if "scope" in data:
            self.store.set_setting("image_scope", "super" if data.get("scope") == "super" else ("whitelist" if data.get("scope") == "whitelist" else "all"))
        return aiohttp_web.json_response({"code": 0})

    async def api_image_test(self, request):
        self.require_super(request)
        data = await request.json()
        prompt = str(data.get("prompt") or "一只猫在键盘上睡觉").strip()
        try:
            img = await self.generate_image(prompt, uid=str(self.self_id or ""), is_super=True)
            mime = "image/png" if img[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
            import base64 as _b64
            data_url = f"data:{mime};base64," + _b64.b64encode(img).decode()
            return aiohttp_web.json_response({"code": 0, "bytes": len(img), "data_url": data_url,
                                              "message": f"生成成功，{len(img)//1024} KB"})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": str(e)[:200]})


add(id="image.core", name="生图",
    entry="fishpond.features.image.service:prepare_images",
    routes=["/api/image/*"] if "image" == "voice" else [], tables=[],
    settings=["image_*"], ui="机器人/生图",
    files="fishpond/features/image/service.py", status="active")
