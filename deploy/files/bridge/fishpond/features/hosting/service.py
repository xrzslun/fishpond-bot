"""托管节点模块：远程租户、部署、二维码。"""
import asyncio
import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from datetime import datetime

import aiohttp
import aiohttp.web as aiohttp_web

from fishpond.registry import add

log = __import__("logging").getLogger("qqbridge")


class HostingMixin:
    def hosting_metas(self) -> list[dict]:
        out = []
        d = self.HOSTING_ROOT / "tenants"
        if d.exists():
            for f in sorted(d.glob("*/meta.json")):
                try:
                    out.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return out

    def hosting_nodes(self) -> dict:
        """节点配置：hk 本机；sh 走隧道到上海主控。"""
        nodes = {"hk": {"label": "本地部署（本机）", "local": True}}
        try:
            cfg = json.loads((self.HOSTING_ROOT / "nodes.json").read_text(encoding="utf-8"))
            for k, v in cfg.items():
                if k == "hk":
                    continue
                nodes[k] = {"label": v.get("label") or k, "local": False,
                            "base": v.get("base", "").rstrip("/"),
                            "prefix": v.get("prefix", ""),
                            "auth": "Basic " + __import__("base64").b64encode(
                                f"{v.get('user','owner')}:{v.get('pass','')}".encode()).decode()}
        except Exception:
            pass
        return nodes

    def hosting_master_token(self) -> str:
        try:
            return (self.HOSTING_ROOT / "master.token").read_text().strip()
        except Exception:
            return ""

    def hosting_cli(self, args: list[str]) -> tuple[int, str]:
        import subprocess as sp
        cmd = ["sudo", "-n", str(self.HOSTING_ROOT / "venv/bin/python3"),
               str(self.HOSTING_ROOT / "hosting/tenant.py")] + args
        try:
            r = sp.run(cmd, capture_output=True, text=True, timeout=180)
            return r.returncode, (r.stdout or r.stderr or "").strip()[:600]
        except Exception as e:
            return 1, str(e)

    async def hosting_live(self, m: dict) -> dict:
        try:
            async with self.http.get(
                    f"http://127.0.0.1:{m['admin_port']}/api/status",
                    headers={"X-Master-Token": self.hosting_master_token()},
                    timeout=aiohttp.ClientTimeout(total=3)) as r:
                d = await r.json(content_type=None)
                qq = d.get("qq") or {}
                return {"online": bool(qq.get("online")), "nick": qq.get("nick") or "",
                        "uin": str(qq.get("uin") or ""), "need_login": bool(d.get("need_login"))}
        except Exception:
            return {"online": False, "nick": "", "uin": "", "need_login": True}

    async def api_hosting_list(self, request):
        self.require_super(request)
        node = str(request.query.get("node") or "hk")
        nodes = self.hosting_nodes()
        if node in nodes and not nodes[node]["local"]:
            n = nodes[node]
            try:
                async with self.http.get(n["base"] + n["prefix"] + "/host/api/list",
                                         headers={"Authorization": n["auth"]},
                                         timeout=aiohttp.ClientTimeout(total=5)) as r:
                    d = await r.json(content_type=None)
                    return aiohttp_web.json_response({"code": 0, "items": d.get("items") or [], "node": node})
            except Exception as e:
                return aiohttp_web.json_response({"code": -1, "message": f"节点不可用: {e}"})
        items = []
        for m in self.hosting_metas():
            live = await self.hosting_live(m)
            try:
                left = max(0, (datetime.strptime(m["expires_at"], "%Y-%m-%d %H:%M") - datetime.now()).days)
            except Exception:
                left = 0
            items.append({**{k: m.get(k) for k in ("id", "qq", "plan", "price", "expires_at", "admin_pass", "account")},
                          "token": m.get("token"), "live": live,
                          "bound_qq": live.get("uin") or m.get("qq") or "", "days_left": left,
                          "link": f"https://xrzs.cloud/t/{m.get('token')}/"})
        return aiohttp_web.json_response({"code": 0, "items": items})

    async def api_hosting_nodes(self, request):
        self.require_super(request)
        nodes = self.hosting_nodes()
        return aiohttp_web.json_response({"code": 0, "items": [
            {"key": k, "label": v.get("label"), "local": bool(v.get("local"))} for k, v in nodes.items()]})

    async def api_hosting_add_node(self, request):
        self.require_super(request)
        d = await request.json()
        key = str(d.get("key") or "").strip().lower()[:16]
        base = str(d.get("base") or "").strip().rstrip("/")
        if not key or not base.startswith("http"):
            return aiohttp_web.json_response({"code": -1, "message": "服务器地址必填，需 http(s)://"})
        cfg = {}
        try:
            cfg = json.loads((self.HOSTING_ROOT / "nodes.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        cfg[key] = {"label": str(d.get("label") or key), "base": base,
                    "prefix": str(d.get("prefix") or "").strip(), "user": "owner",
                    "pass": str(d.get("pass") or "").strip(),
                    "token": str(d.get("token") or "").strip()}
        (self.HOSTING_ROOT / "nodes.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return aiohttp_web.json_response({"code": 0})

    async def api_hosting_passwd(self, request):
        self.require_super(request)
        d = await request.json()
        tid = str(d.get("id") or ""); pw = str(d.get("password") or "")
        node = str(d.get("node") or "hk")
        n = self.hosting_nodes().get(node) or {}
        if n and not n.get("local"):
            try:
                async with self.http.post(n["base"] + n["prefix"] + "/host/api/passwd",
                                          json={"id": tid, "password": pw},
                                          headers={"Authorization": n.get("auth", "")},
                                          timeout=aiohttp.ClientTimeout(total=30)) as r:
                    return aiohttp_web.json_response(await r.json(content_type=None))
            except Exception as e:
                return aiohttp_web.json_response({"code": -1, "message": str(e)[:120]})
        code, out = await asyncio.get_running_loop().run_in_executor(
            None, self.hosting_cli, ["passwd", tid, pw])
        return aiohttp_web.json_response({"code": 0 if code == 0 else -1, "message": out})

    async def _hosting_forward(self, request, path: str):
        d = await request.json()
        node = str(d.get("node") or "hk")
        n = self.hosting_nodes().get(node) or {}
        if n and not n.get("local"):
            try:
                async with self.http.post(n["base"] + n["prefix"] + "/host" + path, json=d,
                                          headers={"Authorization": n["auth"]},
                                          timeout=aiohttp.ClientTimeout(total=180)) as r:
                    return aiohttp_web.json_response(await r.json(content_type=None))
            except Exception as e:
                return aiohttp_web.json_response({"code": -1, "message": f"节点不可用: {e}"})
        return None

    async def api_hosting_create(self, request):
        self.require_super(request)
        fw = await self._hosting_forward(request, "/api/create")
        if fw is not None:
            return fw
        d = await request.json()
        tid = str(d.get("id") or "").strip()
        qq = str(d.get("qq") or "").strip()
        days = str(int(d.get("days") or 30))
        account = str(d.get("account") or "admin").strip()
        password = str(d.get("password") or "")
        code, out = await asyncio.get_running_loop().run_in_executor(
            None, self.hosting_cli, ["create", tid, qq, days, account, password])
        return aiohttp_web.json_response({"code": 0 if code == 0 else -1, "message": out})

    async def api_hosting_action(self, request):
        self.require_super(request)
        fw = await self._hosting_forward(request, "/api/action")
        if fw is not None:
            return fw
        d = await request.json()
        tid, act = str(d.get("id") or ""), str(d.get("action") or "")
        args = {"start": ["start", tid], "stop": ["stop", tid],
                "renew": ["renew", tid, str(int(d.get("days") or 30))],
                "delete": ["delete", tid, "--purge"]}.get(act)
        if not args:
            return aiohttp_web.json_response({"code": -1, "message": "未知操作"})
        code, out = await asyncio.get_running_loop().run_in_executor(None, self.hosting_cli, args)
        return aiohttp_web.json_response({"code": 0 if code == 0 else -1, "message": out})

    def _remote_ssh(self, ip, user, password, port, env, script, timeout=600):
        import subprocess as sp, shlex
        envs = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
        cmd = ["sshpass", "-p", password, "ssh", "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=15",
               "-p", str(port), f"{user}@{ip}", f"{envs} bash -s"]
        r = sp.run(cmd, input=script, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + "\n" + (r.stderr or "")

    def _deploy_remote_sync(self, ip: str, user: str, password: str, port: str, label: str) -> str:
        import subprocess as sp, secrets, socket
        ROOT = self.HOSTING_ROOT
        hk = (os.environ.get("FISHPOND_HK_HOST") or "")
        if not hk:
            try:
                hk = (ROOT / "hk_host").read_text().strip()
            except Exception:
                hk = ""
        if not hk:
            raise RuntimeError("本机缺少 hk_host 配置")
        script = (ROOT / "hosting" / "deploy_remote.sh").read_text(encoding="utf-8")
        code, out = self._remote_ssh(ip, user, password, port, {"MODE": "prep"}, script, 420)
        if code != 0:
            raise RuntimeError("远程准备失败: " + out[-300:])
        pub = ""
        for line in out.splitlines():
            if line.startswith("PUBKEY:"):
                pub = line[7:].strip()
        if not pub:
            raise RuntimeError("未取到远程公钥")
        ak = Path.home() / ".ssh" / "authorized_keys"
        ak.parent.mkdir(mode=0o700, exist_ok=True)
        existing = ak.read_text(encoding="utf-8") if ak.exists() else ""
        if pub not in existing:
            with ak.open("a", encoding="utf-8") as f:
                f.write(pub + "\n")
            ak.chmod(0o600)
        pport = 19100
        while pport < 19300:
            with socket.socket() as sk:
                try:
                    sk.bind(("127.0.0.1", pport)); break
                except OSError:
                    pport += 1
        files = [ROOT / "app/bot.py", ROOT / "hosting/admin.py", ROOT / "hosting/tenant.py"]
        scp = ["sshpass", "-p", password, "scp", "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", "-P", str(port)] + [str(f) for f in files] + [f"{user}@{ip}:/tmp/"]
        rs = sp.run(scp, capture_output=True, text=True, timeout=300)
        if rs.returncode != 0:
            raise RuntimeError("文件上传失败: " + (rs.stderr or "")[-200:])
        hpass = secrets.token_hex(8)
        code2, out2 = self._remote_ssh(ip, user, password, port,
                                       {"MODE": "finish", "TUNNEL_PORT": pport, "HK_HOST": hk,
                                        "HK_USER": "ubuntu", "HOST_PASS": hpass}, script, 600)
        if code2 != 0:
            raise RuntimeError("远程部署失败: " + out2[-300:])
        cfg = {}
        try:
            cfg = json.loads((ROOT / "nodes.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        key = "r" + ip.replace(".", "")
        cfg[key] = {"label": label or ip, "base": f"http://127.0.0.1:{pport}", "prefix": "",
                    "user": "owner", "pass": hpass}
        (ROOT / "nodes.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"部署完成：{label or ip}，隧道端口 {pport}，节点 {key}"

    async def api_hosting_deploy_server(self, request):
        self.require_super(request)
        d = await request.json()
        ip = str(d.get("ip") or "").strip(); user = str(d.get("user") or "root").strip()
        password = str(d.get("password") or ""); port = str(d.get("port") or "22")
        label = str(d.get("label") or "").strip()
        if not ip or not password:
            return aiohttp_web.json_response({"code": -1, "message": "IP 和密码必填"})
        try:
            msg = await asyncio.get_running_loop().run_in_executor(
                None, self._deploy_remote_sync, ip, user, password, port, label)
            return aiohttp_web.json_response({"code": 0, "message": msg})
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": str(e)[:400]})

    async def api_hosting_qr(self, request):
        self.require_super(request)
        fw = await self._hosting_forward(request, "/api/qr")
        if fw is not None:
            return fw
        d = await request.json()
        m = next((x for x in self.hosting_metas() if x.get("id") == d.get("id")), None)
        if not m:
            return aiohttp_web.json_response({"code": -1, "message": "租户不存在"})
        try:
            async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True),
                                             timeout=aiohttp.ClientTimeout(total=40)) as s2:
                async with s2.post(f"http://127.0.0.1:{m['admin_port']}/api/login",
                                   json={"username": "admin", "password": m.get("admin_pass", "")}) as r:
                    await r.read()
                async with s2.post(f"http://127.0.0.1:{m['admin_port']}/api/qr", json={"force": True}) as r:
                    return aiohttp_web.json_response(await r.json(content_type=None))
        except Exception as e:
            return aiohttp_web.json_response({"code": -1, "message": str(e)[:150]})


add(id="hosting.nodes", name="托管节点", entry="fishpond.features.hosting.service:HostingMixin",
    routes=["/api/hosting/*"], tables=[], settings=["hosting_*"], ui="租户",
    files="fishpond/features/hosting/service.py", status="active")
