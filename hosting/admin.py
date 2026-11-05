#!/usr/bin/env python3
"""托管主控：租户列表/创建/启停/续期/二维码 + /t/<token>/ 反向代理"""
import json, os, subprocess, sys, time, asyncio, secrets
from pathlib import Path
import aiohttp
from aiohttp import web

ROOT = Path(os.environ.get("FISHPOND_HOST_ROOT", "/opt/fishpond"))
TENANTS = ROOT / "tenants"
MASTER = (ROOT / "master.token").read_text().strip() if (ROOT / "master.token").exists() else ""
USER = os.environ.get("HOST_ADMIN_USER", "owner")
PASS = os.environ.get("HOST_ADMIN_PASS", "")
DOMAIN = os.environ.get("FISHPOND_HOST_DOMAIN", "xrzs.cloud")
PREFIX = os.environ.get("FISHPOND_ADMIN_PREFIX", "").rstrip("/")
FBASE = PREFIX or ""
PY = sys.executable

def metas():
    out = []
    if TENANTS.exists():
        for p in sorted(TENANTS.glob("*/meta.json")):
            try: out.append(json.loads(p.read_text()))
            except Exception: pass
    return out

def by_token(token):
    return next((m for m in metas() if m.get("token") == token), None)

def run(args):
    try:
        r = subprocess.run(["sudo", "-n"] + args, capture_output=True, text=True, timeout=30)
        return r.returncode, (r.stdout or r.stderr)[:400]
    except Exception as e:
        return 1, str(e)

async def tenant_status(m):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(f"http://127.0.0.1:{m['admin_port']}/api/status",
                             headers={"X-Master-Token": MASTER}) as r:
                d = await r.json(content_type=None)
                qq = (d.get("qq") or {})
                return {"online": bool(qq.get("online")), "nick": qq.get("nick") or "",
                        "need_login": bool(d.get("need_login")), "bridge": bool(d.get("bridge_connected"))}
    except Exception:
        return {"online": False, "nick": "", "need_login": True, "bridge": False}

AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "")

def auth(request):
    if AGENT_TOKEN and request.headers.get("X-Agent-Token", "") == AGENT_TOKEN:
        return True
    a = request.headers.get("Authorization", "")
    expect = "Basic " + __import__("base64").b64encode(f"{USER}:{PASS}".encode()).decode()
    return a == expect

@web.middleware
async def basic_auth(request, handler):
    if (request.path.startswith(FBASE + "/host") or (FBASE and request.path in (FBASE, FBASE + "/"))) and not auth(request):
        return web.Response(status=401, headers={"WWW-Authenticate": 'Basic realm="host"'},
                            text="需要登录")
    return await handler(request)

async def index(request):
    return web.Response(text=HTML.replace("__PREFIX__", FBASE), content_type="text/html", charset="utf-8")

async def api_list(request):
    out = []
    for m in metas():
        st = await tenant_status(m)
        out.append({**m, "live": st,
                    "link": f"https://{DOMAIN}/t/{m['token']}/",
                    "days_left": max(0, int((__import__("datetime").datetime.strptime(m["expires_at"], "%Y-%m-%d %H:%M") - __import__("datetime").datetime.now()).total_seconds() // 86400))})
    return web.json_response({"code": 0, "items": out})

async def api_create(request):
    d = await request.json()
    tid = str(d.get("id") or "").strip()
    qq = str(d.get("qq") or "").strip()
    days = str(int(d.get("days") or 30))
    account = str(d.get("account") or "admin").strip()
    password = str(d.get("password") or "")
    code, out = run([PY, str(ROOT / "hosting/tenant.py"), "create", tid, qq, days, account, password])
    return web.json_response({"code": 0 if code == 0 else -1, "message": out})

async def api_action(request):
    d = await request.json()
    tid = str(d.get("id") or ""); act = str(d.get("action") or "")
    days = str(d.get("days") or 30)
    args = {"start": ["start", tid], "stop": ["stop", tid], "renew": ["renew", tid, days],
            "delete": ["delete", tid, "--purge"]}.get(act)
    if not args: return web.json_response({"code": -1, "message": "未知操作"})
    code, out = run([PY, str(ROOT / "hosting/tenant.py")] + args)
    return web.json_response({"code": 0 if code == 0 else -1, "message": out})

async def api_passwd(request):
    d = await request.json()
    tid = str(d.get("id") or ""); pw = str(d.get("password") or "")
    code, out = run([PY, str(ROOT / "hosting/tenant.py"), "passwd", tid, pw])
    return web.json_response({"code": 0 if code == 0 else -1, "message": out})

async def api_qr(request):
    d = await request.json(); m = next((x for x in metas() if x["id"] == d.get("id")), None)
    if not m: return web.json_response({"code": -1, "message": "租户不存在"})
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True),
                                         timeout=aiohttp.ClientTimeout(total=40)) as s:
            async with s.post(f"http://127.0.0.1:{m['admin_port']}/api/login",
                              json={"username": "admin", "password": m.get("admin_pass", "")}) as r:
                await r.read()
            async with s.post(f"http://127.0.0.1:{m['admin_port']}/api/qr", json={"force": True}) as r:
                return web.json_response(await r.json(content_type=None))
    except Exception as e:
        return web.json_response({"code": -1, "message": str(e)[:120]})

SH_ADMIN = os.environ.get("FISHPOND_SH_ADMIN", "http://127.0.0.1:8092")

async def proxy(request):
    token = request.match_info["token"]; m = by_token(token)
    if not m:
        # 本机没有这个租户 → 交给上海节点（多节点托管）
        tail = request.match_info.get("tail", "")
        url = f"{SH_ADMIN}/shost/t/{token}/{tail}"
        if request.query_string: url += "?" + request.query_string
        body = await request.read()
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as s:
                async with s.request(request.method, url, data=body or None, headers=headers) as r:
                    data = await r.read()
                    ct = r.headers.get("Content-Type", "application/octet-stream")
                    return web.Response(status=r.status, body=data, headers={"Content-Type": ct})
        except Exception as e:
            return web.Response(status=502, text=f"上海节点不可用: {e}")
    tail = request.match_info.get("tail", "")
    path_qs = request.path_qs
    if FBASE and path_qs.startswith(FBASE):
        path_qs = path_qs[len(FBASE):] or "/"
    url = f"http://127.0.0.1:{m['admin_port']}{path_qs}"
    if request.query_string: url += "?" + request.query_string
    body = await request.read()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as s:
            async with s.request(request.method, url, data=body or None, headers=headers) as r:
                resp = web.StreamResponse(status=r.status, headers={
                    k: v for k, v in r.headers.items() if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")})
                resp.content_type = r.headers.get("Content-Type", "application/octet-stream")
                await resp.prepare(request)
                async for chunk in r.content.iter_chunked(65536):
                    await resp.write(chunk)
                await resp.write_eof()
                return resp
    except Exception as e:
        return web.Response(status=502, text=f"租户服务不可用: {e}")

HTML = """<!doctype html><html><head><meta charset=utf-8><title>FishPond 托管</title>
<style>body{background:#0b0d11;color:#e6e6e6;font:14px system-ui;margin:24px}
table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #22262f;padding:8px;text-align:left}
input,button{background:#12151b;color:#e6e6e6;border:1px solid #2a2f3a;border-radius:6px;padding:6px}
button{cursor:pointer}.ok{color:#4ade80}.bad{color:#f87171}.hint{color:#9aa4b8;font-size:12px}</style></head>
<body><h2>FishPond 托管控制台</h2>
<div class=hint>创建租户后把链接和初始密码发给用户；二维码在用户掉线时用来重新登录。</div>
<div style="margin:12px 0;display:flex;gap:8px;flex-wrap:wrap">
<input id=id placeholder=租户ID style=width:120px><input id=qq placeholder=QQ号 style=width:160px>
<input id=days placeholder=天数 value=30 style=width:80px><button onclick=create()>创建租户</button>
<span id=msg class=hint></span></div>
<table><thead><tr><th>租户</th><th>QQ</th><th>状态</th><th>到期</th><th>链接</th><th>操作</th></tr></thead><tbody id=rows></tbody></table>
<script>
async function api(u,o){const r=await fetch('__PREFIX__/host'+u,o||{});return r.json()}
async function load(){const d=await api('/api/list');document.getElementById('rows').innerHTML=(d.items||[]).map(function(m){
 const st=m.live.online?'<span class=ok>在线</span>':(m.live.need_login?'<span class=bad>需扫码</span>':'<span class=bad>离线</span>');
 return `<tr><td>${m.id}</td><td>${m.qq}</td><td>${st}<div class=hint>${m.live.nick||''}</div></td>
 <td>${m.expires_at}<div class=hint>剩 ${m.days_left} 天</div></td>
 <td><a style=color:#7dd3fc href="${m.link}" target=_blank>打开</a><div class=hint>密码 ${m.admin_pass}</div></td>
 <td><button onclick="act('${m.id}','start')">启动</button>
 <button onclick="act('${m.id}','stop')">停止</button>
 <button onclick="renew('${m.id}')">续期</button>
 <button onclick="qr('${m.id}')">二维码</button>
 <button onclick="act('${m.id}','delete')">删除</button></td></tr>`}).join('')}
async function create(){const r=await api('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({id:id.value,qq:qq.value,days:days.value})});msg.textContent=r.message;load()}
async function act(id,a){if(a==='delete'&&!confirm('删除租户 '+id+' ？'))return;
 const r=await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,action:a})});msg.textContent=r.message;load()}
async function renew(id){const d=prompt('续期天数','30');if(!d)return;
 await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,action:'renew',days:d})});load()}
async function qr(id){const r=await api('/api/qr',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
 if(r.code!==0){alert(r.message||'失败');return}
 if(r.qrcode){const w=window.open('');w.document.write('<img src="'+r.qrcode+'" style="width:320px"><p>'+((r.qrcodeurl)||'')+'</p>')}
 else alert(r.qrcodeurl||'没有二维码')}
load();setInterval(load,15000);
</script></body></html>"""

app = web.Application(middlewares=[basic_auth])
app.router.add_get(FBASE + "/host/", index); app.router.add_get(FBASE + "/host", index)
app.router.add_get(FBASE + "/host/api/list", api_list)
app.router.add_post(FBASE + "/host/api/create", api_create)
app.router.add_post(FBASE + "/host/api/action", api_action)
app.router.add_post(FBASE + "/host/api/qr", api_qr)
app.router.add_post(FBASE + "/host/api/passwd", api_passwd)
app.router.add_route("*", FBASE + "/t/{token}/{tail:.*}", proxy)
app.router.add_route("*", FBASE + "/t/{token}", proxy)
if FBASE:
    app.router.add_get(FBASE + "/", index)

if __name__ == "__main__":
    port = int(os.environ.get("HOST_ADMIN_PORT", "8090"))
    web.run_app(app, host=os.environ.get("HOST_BIND", "127.0.0.1"), port=port, print=None)
