#!/usr/bin/env python3
"""托管租户管理 CLI：创建/启停/续期/删除/列表（每租户 = 1 个 NapCat 容器 + 1 个 bot 进程）"""
import json, os, secrets, subprocess, sys, time, shutil
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("FISHPOND_HOST_ROOT", "/opt/fishpond"))
TENANTS = ROOT / "tenants"
APP = ROOT / "app"
VENV = ROOT / "venv"
IMAGE = os.environ.get("NAPCAT_IMAGE", "mlikiowa/napcat-docker:latest")
HOST_DOMAIN = os.environ.get("FISHPOND_HOST_DOMAIN", "xrzs.cloud")
SUDO = [] if os.geteuid() == 0 else ["sudo", "-n"]

def sh(cmd, check=True):
    r = subprocess.run(SUDO + cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"命令失败: {' '.join(cmd)}\n{r.stderr[:400]}")
    return r

def meta_path(tid): return TENANTS / tid / "meta.json"

def load(tid):
    p = meta_path(tid)
    if not p.exists(): raise SystemExit(f"租户不存在: {tid}")
    return json.loads(p.read_text())

def save(tid, m):
    meta_path(tid).write_text(json.dumps(m, ensure_ascii=False, indent=2))

def next_ports():
    used = set()
    if TENANTS.exists():
        for p in TENANTS.glob("*/meta.json"):
            try:
                m = json.loads(p.read_text())
                used.update([m.get("ws_port"), m.get("web_port"), m.get("admin_port")])
            except Exception: pass
    base = 13100
    while True:
        if not ({base, base + 3000, base + 5000} & used): return base, base + 3000, base + 5000
        base += 1

CONFIG_TPL = """deepseek:
  base_url: https://api.deepseek.com
  model: deepseek-chat
  api_key: ''
  persona: '你是「大肥鱼」，QQ 里闲聊的朋友，嘴硬心软、偶尔损人，像手机打字，一两句为主。'
onebot:
  ws_url: ws://127.0.0.1:{ws}
  access_token: ''
napcat:
  webui_url: http://127.0.0.1:{web}
  webui_token: {ntoken}
  qr_cooldown_seconds: 60
webui:
  path: '/t/{token}'
admin:
  host: 127.0.0.1
  db_path: data.db
  default_admin:
    username: '{account}'
    password: '{apass}'
trigger:
  group_at_only: true
  keywords: []
update_url: 'https://xrzs.cloud/updates/latest.json'
"""

def create(tid="", qq="", days=30, plan="basic", price=0, account="admin", password=""):
    qq = str(qq or "").strip()
    tid = "".join(c for c in str(tid or "") if c.isalnum() or c in "-_")[:24]
    if not tid:
        tid = "t-" + secrets.token_hex(3)
    d = TENANTS / tid
    if d.exists(): raise SystemExit(f"租户已存在: {tid}")
    ws, web, admin = next_ports()
    ntoken = secrets.token_hex(16)
    account = str(account or "admin").strip()[:32] or "admin"
    apass = str(password or "").strip() or secrets.token_urlsafe(9)
    token = secrets.token_urlsafe(18)
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("napcat/qq", "napcat/config", "napcat/plugins"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text(CONFIG_TPL.format(ws=ws, web=web, ntoken=ntoken,
                                                    apass=apass, token=token, account=account))
    m = {"id": tid, "qq": str(qq), "token": token, "plan": plan, "price": price,
         "account": account,
         "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "days": int(days),
         "expires_at": (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M"),
         "ws_port": ws, "web_port": web, "admin_port": admin, "admin_pass": apass,
         "napcat_token": ntoken, "status": "created"}
    save(tid, m)
    sh(["chown", "-R", "fishpond:fishpond", str(d)])
    sh(["docker", "run", "-d", "--name", f"napcat-{tid}", "--restart", "unless-stopped",
        "-e", "TZ=Asia/Shanghai", "-e", "MODE=ws", "-e", f"WEBUI_TOKEN={ntoken}",
        *(["-e", f"ACCOUNT={qq}"] if qq else []),
        "-p", f"127.0.0.1:{ws}:3001", "-p", f"127.0.0.1:{web}:6099",
        "--memory=900m", "--memory-swap=1200m", "--cpus=1",
        "-v", f"{d}/napcat/qq:/app/.config/QQ", "-v", f"{d}/napcat/config:/app/napcat/config",
        "-v", f"{d}/napcat/plugins:/app/napcat/plugins", IMAGE], check=False)
    unit = f"""[Unit]
Description=FishPond tenant {tid}
After=network-online.target docker.service
[Service]
User=fishpond
WorkingDirectory={d}
Environment=FISHPOND_HOME={d}
Environment=FISHPOND_ADMIN_PORT={admin}
Environment=FISHPOND_MASTER_TOKEN={master_token()}
ExecStart={VENV}/bin/python3 {APP}/bot.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
"""
    Path(f"/etc/systemd/system/fishpond-tenant-{tid}.service").write_text(unit)
    sh(["systemctl", "daemon-reload"])
    sh(["systemctl", "enable", "fishpond-tenant-" + tid])
    sh(["systemctl", "start", "fishpond-tenant-" + tid], check=False)
    m["status"] = "running"; save(tid, m)
    print(f"✓ 已创建 {tid}")
    print(f"  链接: https://{HOST_DOMAIN}/t/{m['token']}/")
    print(f"  账号: {account}")
    print(f"  管理密码: {apass}")
    print(f"  端口: ws={ws} web={web} admin={admin}")

def master_token():
    p = ROOT / "master.token"
    if not p.exists():
        p.write_text(secrets.token_hex(24))
    return p.read_text().strip()

def cmd_start(tid):
    m = load(tid); sh(["docker", "start", f"napcat-{tid}"], check=False)
    sh(["systemctl", "start", f"fishpond-tenant-{tid}"], check=False)
    m["status"] = "running"; save(tid, m); print("✓ 已启动", tid)

def cmd_stop(tid):
    m = load(tid)
    sh(["systemctl", "stop", f"fishpond-tenant-{tid}"], check=False)
    sh(["docker", "stop", f"napcat-{tid}"], check=False)
    m["status"] = "stopped"; save(tid, m); print("✓ 已停止", tid)

def cmd_passwd(tid, newpass=""):
    m = load(tid)
    newpass = str(newpass or "").strip() or secrets.token_urlsafe(9)
    d = TENANTS / tid
    cfg = d / "config.yaml"
    txt = cfg.read_text(encoding="utf-8")
    import re as _re
    txt = _re.sub(r"password: '[^']*'", f"password: '{newpass}'", txt)
    cfg.write_text(txt, encoding="utf-8")
    # 同步数据库里的管理员哈希（通过 bot 主控令牌接口）
    body = json.dumps({"password": newpass, "username": m.get("account", "admin")})
    try:
        subprocess.run(["curl", "-s", "-X", "POST", f"http://127.0.0.1:{m['admin_port']}/api/master/set_admin_password",
                        "-H", "Content-Type: application/json",
                        "-H", "X-Master-Token: " + master_token(), "-d", body],
                       capture_output=True, timeout=15)
    except Exception:
        pass
    m["admin_pass"] = newpass
    save(tid, m)
    print("✓ 新密码:", newpass)

def cmd_renew(tid, days):
    m = load(tid)
    base = datetime.strptime(m["expires_at"], "%Y-%m-%d %H:%M")
    base = max(base, datetime.now()) + timedelta(days=int(days))
    m["expires_at"] = base.strftime("%Y-%m-%d %H:%M"); m["days"] = m.get("days", 0) + int(days)
    save(tid, m); print("✓ 已续期到", m["expires_at"])

def cmd_delete(tid, purge=False):
    m = load(tid)
    sh(["systemctl", "disable", "--now", f"fishpond-tenant-{tid}"], check=False)
    sh(["docker", "rm", "-f", f"napcat-{tid}"], check=False)
    for p in (Path(f"/etc/systemd/system/fishpond-tenant-{tid}.service"),):
        p.unlink(missing_ok=True)
    sh(["systemctl", "daemon-reload"], check=False)
    if purge:
        shutil.rmtree(TENANTS / tid, ignore_errors=True)
    else:
        m["status"] = "deleted"; save(tid, m)
    print("✓ 已删除", tid, "(数据已清除)" if purge else "(数据保留)")

def cmd_list():
    if not TENANTS.exists(): return
    for p in sorted(TENANTS.glob("*/meta.json")):
        m = json.loads(p.read_text())
        print(f"{m['id']:<10} QQ={m['qq']:<12} {m['status']:<8} 到期={m['expires_at']} 链接=https://{HOST_DOMAIN}/t/{m['token']}/")

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    c = sys.argv[1]
    if c == "create":
        tid = sys.argv[2] if len(sys.argv) > 2 else ""
        qq = sys.argv[3] if len(sys.argv) > 3 else ""
        days = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        account = sys.argv[5] if len(sys.argv) > 5 else "admin"
        password = sys.argv[6] if len(sys.argv) > 6 else ""
        create(tid, qq, days, account=account, password=password)
    elif c == "passwd":
        cmd_passwd(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    elif c == "list": cmd_list()
    elif c == "start": cmd_start(sys.argv[2])
    elif c == "stop": cmd_stop(sys.argv[2])
    elif c == "renew": cmd_renew(sys.argv[2], int(sys.argv[3]))
    elif c == "delete": cmd_delete(sys.argv[2], purge="--purge" in sys.argv)
    elif c == "master": print(master_token())
    else: print(__doc__)

if __name__ == "__main__":
    main()
