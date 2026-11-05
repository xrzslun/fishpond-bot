"""账号与模型供应商模块。"""
import asyncio
import hashlib
import json
import re
import secrets
import time

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.core.config import VIEWER_FEATURE
from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")

PROVIDER_PRESETS = {'deepseek': {'base_url': 'https://api.deepseek.com', 'model': 'deepseek-chat'}, 'openai': {'base_url': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini'}, 'moonshot': {'base_url': 'https://api.moonshot.cn/v1', 'model': 'moonshot-v1-8k'}, 'zhipu': {'base_url': 'https://open.bigmodel.cn/api/paas/v4', 'model': 'glm-4-flash'}, 'siliconflow': {'base_url': 'https://api.siliconflow.cn/v1', 'model': 'deepseek-ai/DeepSeek-V3'}, 'openrouter': {'base_url': 'https://openrouter.ai/api/v1', 'model': 'openrouter/auto'}, 'groq': {'base_url': 'https://api.groq.com/openai/v1', 'model': 'llama-3.3-70b-versatile'}, 'custom': {'base_url': '', 'model': ''}}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"



class AccountsMixin:
    def current_provider(self) -> dict:
        name = self.store.get_setting("active_provider", "")
        if name:
            row = self.store.get_provider(name)
            if row and row.get("api_key"):
                return row
        key = (self.store.get_setting("deepseek_api_key", "") or self.api_key or "").strip()
        return {"name": "deepseek(默认)", "base_url": self.api_base, "api_key": key, "model": self.model}

    def current_account(self, request):
        sid = request.cookies.get("qb_sid")
        sess = self.auth_sessions.get(sid) if sid else None
        if not sess or sess.get("exp", 0) <= time.time():
            return None
        return sess

    def auth_ok(self, request) -> bool:
        return self.current_account(request) is not None

    def mask_key(self, key: str) -> str:
        if not key:
            return ""
        if len(key) > 12:
            return key[:5] + "****" + key[-4:]
        return "已配置"

    @staticmethod
    def provider_check_path(base_url: str) -> str:
        # openrouter 的 /models 是公开接口，用 /key 才能校验 Key
        return "/key" if "openrouter.ai" in base_url else "/models"

    async def api_accounts_get(self, request):
        self.require_super(request)
        acc = self.require_role(request, "admin")
        rows = self.store.accounts_all()
        if acc.get("role") != "super":
            rows = [r for r in rows if r.get("role") == "user" and str(r.get("created_by")) == str(acc.get("id"))]
        for r in rows:
            r.pop("pass_hash", None)
        return aiohttp_web.json_response({"code": 0, "accounts": rows, "my_role": acc.get("role"),
                                          "viewer_enabled": VIEWER_FEATURE and self.store.get_setting("enable_viewer_role", "0") == "1"})

    async def api_accounts_create(self, request):
        self.require_super(request)
        acc = self.require_role(request, "admin")
        data = await request.json()
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        role = str(data.get("role") or "user")
        if acc.get("role") == "admin" and role != "user":
            return aiohttp_web.json_response({"code": -1, "message": "管理员只能创建用户"})
        if role == "viewer" and (not VIEWER_FEATURE or acc.get("role") != "super" or self.store.get_setting("enable_viewer_role", "0") != "1"):
            return aiohttp_web.json_response({"code": -1, "message": "角色不合法"})
        if role not in ("super", "admin", "user", "viewer"):
            return aiohttp_web.json_response({"code": -1, "message": "角色不合法"})
        if not username or len(username) < 2 or len(password) < 6:
            return aiohttp_web.json_response({"code": -1, "message": "用户名至少2位，密码至少6位"})
        qg = data.get("quota_groups")
        qu = data.get("quota_users")
        qg = None if qg in (None, "", "0") else max(0, int(qg))
        qu = None if qu in (None, "", "0") else max(0, int(qu))
        if acc.get("role") == "admin":
            qg = qg if qg is not None else None
        new_id = self.store.create_account(username, password, role, acc.get("id"), qg, qu)
        if new_id is None:
            return aiohttp_web.json_response({"code": -1, "message": "用户名已存在"})
        return aiohttp_web.json_response({"code": 0, "id": new_id})

    async def api_accounts_update(self, request):
        self.require_super(request)
        acc = self.require_role(request, "admin")
        data = await request.json()
        aid = data.get("id")
        target = self.store.account_by_id(aid) if aid else None
        if not target:
            return aiohttp_web.json_response({"code": -1, "message": "账号不存在"})
        if acc.get("role") == "admin":
            if target.get("role") != "user" or str(target.get("created_by")) != str(acc.get("id")):
                return aiohttp_web.json_response({"code": -1, "message": "只能修改自己创建的用户"})
        fields = {}
        if "quota_groups" in data:
            v = data.get("quota_groups")
            fields["quota_groups"] = None if v in (None, "", "0") else max(0, int(v))
        if "quota_users" in data:
            v = data.get("quota_users")
            fields["quota_users"] = None if v in (None, "", "0") else max(0, int(v))
        if data.get("password"):
            if len(str(data["password"])) < 6:
                return aiohttp_web.json_response({"code": -1, "message": "密码至少6位"})
            fields["pass_hash"] = hash_password(str(data["password"]))
        if "disabled" in data:
            fields["disabled"] = 1 if data.get("disabled") else 0
        if ("role" in data and acc.get("role") == "super"
                and data.get("role") in ("super", "admin", "user", "viewer")
                and (data.get("role") != "viewer" or VIEWER_FEATURE)):
            fields["role"] = data["role"]
        self.store.update_account(aid, **fields)
        return aiohttp_web.json_response({"code": 0})

    async def api_accounts_delete(self, request):
        self.require_super(request)
        acc = self.require_role(request, "admin")
        data = await request.json()
        aid = data.get("id")
        target = self.store.account_by_id(aid) if aid else None
        if not target:
            return aiohttp_web.json_response({"code": -1, "message": "账号不存在"})
        if str(target.get("id")) == str(acc.get("id")):
            return aiohttp_web.json_response({"code": -1, "message": "不能删除自己"})
        if acc.get("role") == "admin" and (target.get("role") != "user" or str(target.get("created_by")) != str(acc.get("id"))):
            return aiohttp_web.json_response({"code": -1, "message": "只能删除自己创建的用户"})
        self.store.delete_account(aid)
        return aiohttp_web.json_response({"code": 0})

    async def api_provider_balances(self, request):
        self.require_super(request)
        force = request.query.get("force") == "1"
        now = time.time()
        cache = getattr(self, "_balance_cache", {})
        out = {}
        for p in self.store.providers():
            name = p["name"]
            hit = cache.get(name)
            if hit and not force and now - hit[1] < 60:
                out[name] = hit[0]
                continue
            text = await self.fetch_balance_text(p)
            cache[name] = (text, now)
            out[name] = text
        self._balance_cache = cache
        return aiohttp_web.json_response({"code": 0, "balances": out})

    async def api_provider_models(self, request):
        self.require_super(request)
        data = await request.json()
        base = str(data.get("base_url") or "").strip().rstrip("/")
        key = str(data.get("api_key") or "").strip()
        name = str(data.get("name") or "").strip()
        if name and (not base or not key):
            row = self.store.get_provider(name) or {}
            base = base or str(row.get("base_url") or "").rstrip("/")
            key = key or str(row.get("api_key") or "")
        if not base or not key:
            return aiohttp_web.json_response({"code": -1, "message": "缺少地址或 Key"})
        try:
            async with self.http.get(base + "/models", headers={"Authorization": f"Bearer {key}"},
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return aiohttp_web.json_response({"code": -1, "message": f"获取失败 HTTP {resp.status}"})
                d = await resp.json(content_type=None)
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": f"获取失败：{e}"})
        items = []
        if isinstance(d, dict):
            arr = d.get("data") or d.get("models") or []
            for it in arr:
                if isinstance(it, dict):
                    mid = it.get("id") or it.get("name") or it.get("model")
                else:
                    mid = it
                if mid:
                    items.append(str(mid))
        elif isinstance(d, list):
            items = [str(x.get("id") if isinstance(x, dict) else x) for x in d]
        items = sorted(set([x for x in items if x]))
        return aiohttp_web.json_response({"code": 0, "models": items})

    async def api_providers_get(self, request):
        self.require_super(request)
        active = self.store.get_setting("active_provider", "")
        items = []
        for p in self.store.providers():
            items.append({
                "name": p["name"],
                "base_url": p["base_url"],
                "model": p["model"],
                "masked": self.mask_key(p["api_key"]),
                "active": p["name"] == active,
            })
        return aiohttp_web.json_response({
            "code": 0,
            "active": active,
            "providers": items,
            "presets": [{"name": k, "base_url": v["base_url"], "model": v["model"]} for k, v in PROVIDER_PRESETS.items()],
        })

    async def api_providers_save(self, request):
        self.require_super(request)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        base_url = str(data.get("base_url") or "").strip().rstrip("/")
        model = str(data.get("model") or "").strip()
        key = str(data.get("api_key") or "").strip()
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            return aiohttp_web.json_response({"code": -1, "message": "名称只能包含字母数字-_"})
        if not base_url.startswith("http"):
            return aiohttp_web.json_response({"code": -1, "message": "base_url 需以 http(s):// 开头"})
        if not model:
            return aiohttp_web.json_response({"code": -1, "message": "请填写模型名"})
        if not key:
            existing = self.store.get_provider(name)
            if existing:
                key = existing["api_key"]
        if len(key) < 10:
            return aiohttp_web.json_response({"code": -1, "message": "请填写 API Key（至少 10 位）"})
        self.store.save_provider(name, base_url, key, model)
        if not self.store.get_setting("active_provider", ""):
            self.store.set_setting("active_provider", name)
        return aiohttp_web.json_response({"code": 0})

    async def api_providers_delete(self, request):
        self.require_super(request)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        self.store.delete_provider(name)
        if self.store.get_setting("active_provider", "") == name:
            self.store.set_setting("active_provider", "")
        return aiohttp_web.json_response({"code": 0})

    async def api_providers_activate(self, request):
        self.require_super(request)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        if not self.store.get_provider(name):
            return aiohttp_web.json_response({"code": -1, "message": "供应商不存在"})
        self.store.set_setting("active_provider", name)
        return aiohttp_web.json_response({"code": 0})

    async def api_providers_test(self, request):
        self.require_super(request)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        row = self.store.get_provider(name)
        if not row:
            return aiohttp_web.json_response({"code": -1, "message": "供应商不存在"})
        try:
            async with self.http.get(
                f"{row['base_url']}{self.provider_check_path(row['base_url'])}",
                headers={"Authorization": f"Bearer {row['api_key']}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    return aiohttp_web.json_response({"code": 0, "message": "Key 有效"})
                return aiohttp_web.json_response({"code": -1, "message": f"Key 无效（HTTP {resp.status}）"})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": f"网络错误: {e}"})

    async def api_providers_autodetect(self, request):
        self.require_super(request)
        data = await request.json()
        key = str(data.get("key") or "").strip()
        if len(key) < 10:
            return aiohttp_web.json_response({"code": -1, "message": "先粘贴 API Key"})
        matches = []
        for name, preset in PROVIDER_PRESETS.items():
            if name == "custom" or not preset["base_url"]:
                continue
            try:
                async with self.http.get(
                    f"{preset['base_url']}{self.provider_check_path(preset['base_url'])}",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status == 200:
                        matches.append({"name": name, "base_url": preset["base_url"], "model": preset["model"]})
            except Exception:
                continue
        return aiohttp_web.json_response({
            "code": 0 if matches else -1,
            "matches": matches,
            "message": "匹配到: " + ", ".join(m["name"] for m in matches) if matches else "没有匹配到已知服务商，可手动填写 base_url",
        })

    async def api_apikey_get(self, request):
        self.require_super(request)
        key = self.effective_api_key()
        return aiohttp_web.json_response({
            "code": 0,
            "configured": bool(key),
            "masked": self.mask_key(key),
            "source": "db" if self.store.get_setting("deepseek_api_key", "") else ("env" if self.api_key else ""),
        })

    async def api_apikey_save(self, request):
        self.require_super(request)
        data = await request.json()
        key = str(data.get("key") or "").strip()
        if len(key) < 20 or not key.startswith("sk-"):
            return aiohttp_web.json_response({"code": -1, "message": "Key 格式不对（应以 sk- 开头）"})
        self.store.set_setting("deepseek_api_key", key)
        return aiohttp_web.json_response({"code": 0})

    async def api_apikey_test(self, request):
        self.require_super(request)
        key = self.effective_api_key()
        if not key:
            return aiohttp_web.json_response({"code": -1, "message": "还没有配置 Key"})
        try:
            async with self.http.get(
                f"{self.api_base}/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    return aiohttp_web.json_response({"code": 0, "message": "Key 有效"})
                return aiohttp_web.json_response({"code": -1, "message": f"Key 无效（HTTP {resp.status}）"})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": f"网络错误: {e}"})

    async def api_end_get(self, request):
        self.require_auth(request)
        return aiohttp_web.json_response({
            "code": 0,
            "enabled": self.store.get_setting("end_phrase_enabled", "1") == "1",
            "reply": self.store.get_setting("end_phrase_reply", "好的，那我退下了"),
            "phrases": self.store.end_phrases(),
        })

    async def api_end_config(self, request):
        self.require_auth(request)
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("end_phrase_enabled", "1" if data.get("enabled") else "0")
        if "reply" in data:
            self.store.set_setting("end_phrase_reply", str(data.get("reply") or "").strip()[:100])
        return aiohttp_web.json_response({"code": 0})

    async def api_end_add(self, request):
        self.require_auth(request)
        data = await request.json()
        phrase = str(data.get("phrase") or "").strip()
        if not phrase or len(phrase) > 30:
            return aiohttp_web.json_response({"code": -1, "message": "触发词不能为空且不超过 30 字"})
        self.store.add_end_phrase(phrase)
        return aiohttp_web.json_response({"code": 0})

    async def api_end_remove(self, request):
        self.require_auth(request)
        data = await request.json()
        self.store.remove_end_phrase(str(data.get("phrase") or "").strip())
        return aiohttp_web.json_response({"code": 0})


add(id="accounts.providers", name="账号与模型供应商", entry="fishpond.features.accounts.service:AccountsMixin",
    routes=["/api/accounts/*", "/api/providers/*", "/api/apikey/*", "/api/end-phrase/*"], tables=["providers"],
    settings=["provider_*"], ui="账号/模型", files="fishpond/features/accounts/service.py", status="active")
