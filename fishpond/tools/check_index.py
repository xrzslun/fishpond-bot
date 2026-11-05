"""注册完整性检查：入口/路由/表/模块/INDEX/前端/发布包。

退出码 0 = 通过，1 = 有 error。
"""
import ast
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ERRORS = []
WARNS = []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNS.append(msg)


def load_registry_entries():
    entries = []
    # 静态清单
    reg = ROOT / "fishpond" / "registry.py"
    tree = ast.parse(reg.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_STATIC" for t in node.targets):
            try:
                rows = ast.literal_eval(node.value)
            except Exception:
                continue
            keys = ("id", "name", "entry", "routes", "tables", "settings", "ui", "files")
            for r in rows:
                entries.append(dict(zip(keys, r)))
    # 模块注册
    for f in sorted((ROOT / "fishpond").rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(getattr(n, "func", None), "id", "") == "add":
                kw = {}
                for k in n.keywords:
                    try:
                        kw[k.arg] = ast.literal_eval(k.value)
                    except Exception:
                        kw[k.arg] = ""
                if kw.get("id"):
                    kw.setdefault("files", str(f.relative_to(ROOT)))
                    kw.setdefault("status", "active")
                    entries.append(kw)
    return entries


def check_entry(e):
    entry = str(e.get("entry") or "")
    m = re.match(r"^([\w.]+):(\w+)$", entry)
    if not m:
        return  # 描述型入口，跳过
    mod, name = m.groups()
    path = ROOT / (mod.replace(".", "/") + ".py")
    if not path.is_file():
        err(f"{e['id']}: 入口文件不存在 {path.relative_to(ROOT)}")
        return
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception as ex:
        err(f"{e['id']}: 入口文件解析失败 {ex}")
        return
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    if name not in names:
        err(f"{e['id']}: 入口 {name} 不存在于 {path.relative_to(ROOT)}")


def registered_routes():
    out = set()
    files = [ROOT / "bridge" / "bot_admin.py"] + list((ROOT / "fishpond").rglob("*.py"))
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in re.finditer(r'add_(?:get|post|route)\((?:[^)]*?)"([^"]+)"', text):
            if m.group(1).startswith("/"):
                out.add(m.group(1))
    return out


def check_routes(entries, routes):
    def ok(p):
        if p in routes:
            return True
        if p.endswith("*"):
            pre = p[:-1]
            return any(r.startswith(pre) for r in routes)
        return any(r == p or r.endswith(p) for r in routes)
    for e in entries:
        for p in (e.get("routes") or []):
            if not str(p).startswith("/"):
                continue
            if not ok(p):
                err(f"{e['id']}: 路由 {p} 未在后台注册")


def check_reverse_routes(entries, routes):
    declared = []
    for e in entries:
        for p in (e.get("routes") or []):
            p = str(p)
            if p.startswith("/"):
                declared.append(p[:-1] if p.endswith("*") else p)
    allow = ("/", "/web/", "/stickers/", "/g/", "/updates/", "/host/", "/t/",
             "/api/login", "/api/logout", "/api/me", "/api/status", "/api/logs",
             "/api/tokens", "/api/health", "/api/errors", "/api/diag/", "/api/rollback",
             "/api/selfcheck/run", "/api/featurecheck/run")
    for r in sorted(routes):
        if any(r == a or r.startswith(a) for a in allow):
            continue
        if not any(r.startswith(d) or d.startswith(r) for d in declared):
            warn(f"路由 {r} 未登记到任何功能")


def check_settings(entries):
    files = list((ROOT / "fishpond").rglob("*.py")) + [ROOT / "bridge" / "bot_admin.py"]
    text = ""
    for f in files:
        try:
            text += f.read_text(encoding="utf-8")
        except Exception:
            pass
    for e in entries:
        for key in (e.get("settings") or []):
            k = str(key).split("*")[0].strip()
            if not k:
                continue
            if k not in text:
                warn(f"{e['id']}: 配置键 {key} 未被读取")


def check_frontend_api(entries, routes):
    js = ROOT / "fishpond" / "web" / "js" / "app.js"
    if not js.is_file():
        return
    text = js.read_text(encoding="utf-8")
    paths = set(re.findall(r"fetch\(B\s*\+\s*['\"]([^'\"]+)['\"]", text))
    declared = []
    for e in entries:
        for p in (e.get("routes") or []):
            p = str(p)
            if p.startswith("/"):
                declared.append(p[:-1] if p.endswith("*") else p)
    for p in sorted(paths):
        if not p.startswith("/api/"):
            continue
        if not any(p.startswith(d) or d.startswith(p) for d in declared):
            warn(f"前端请求 {p} 未登记到任何功能")


def check_tables(entries):
    files = [ROOT / "bridge" / "bot_admin.py"] + list((ROOT / "fishpond").rglob("*.py"))
    sql = ""
    for f in files:
        try:
            sql += f.read_text(encoding="utf-8")
        except Exception:
            pass
    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql))
    for e in entries:
        for t in (e.get("tables") or []):
            name = str(t).split(".")[0].strip()
            if name and name not in tables and name not in ("settings", "sessions"):
                warn(f"{e['id']}: 数据表 {name} 未在建表语句中找到")


def check_modules(entries):
    for d in ("features", "platforms"):
        for f in sorted((ROOT / "fishpond" / d).rglob("*.py")):
            if f.name in ("__init__.py",) or "tools" in f.parts:
                continue
            rel = str(f.relative_to(ROOT))
            if not any(str(e.get("files", "")).endswith(rel) or rel in str(e.get("files", "")) for e in entries):
                warn(f"{rel}: 没有登记任何功能")


def check_index_sync():
    idx = ROOT / "INDEX.md"
    if not idx.is_file():
        err("INDEX.md 不存在")
        return
    before = idx.read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "fishpond" / "tools" / "make_index.py")],
                   capture_output=True)
    after = idx.read_text(encoding="utf-8")
    idx.write_text(before, encoding="utf-8")
    if before != after:
        err("INDEX.md 与 registry 不一致，请运行 fishpond/tools/make_index.py")


def check_frontend():
    html = ROOT / "fishpond" / "web" / "index.html"
    js = ROOT / "fishpond" / "web" / "js" / "app.js"
    if not html.is_file() or not js.is_file():
        err("前端文件缺失（index.html 或 app.js）")
        return
    h = html.read_text(encoding="utf-8")
    j = js.read_text(encoding="utf-8")
    defs = set(re.findall(r"(?:async\s+)?function\s+(\w+)", j))
    refs = set(re.findall(r'onclick="(\w+)\(', h)) | set(re.findall(r'onchange="(\w+)\(', h))
    refs -= {"if", "else", "return"}
    for f in sorted(refs - defs):
        warn(f"onclick 引用的函数 {f} 在 app.js 中不存在")
    for f in sorted(defs):
        if f not in refs and len(re.findall(r"\b" + re.escape(f) + r"\b", j)) <= 1:
            warn(f"app.js 中函数 {f} 定义后未被使用")


def check_update_entrypoint():
    adm = (ROOT / "fishpond" / "platforms" / "admin.py").read_text(encoding="utf-8")
    if 'target = BASE / "bot.py"' not in adm:
        err("更新入口必须使用 BASE/bot.py，不能使用 Path(__file__)（会写到 admin.py 自身）")
    rt = (ROOT / "fishpond" / "features" / "runtime" / "service.py").read_text(encoding="utf-8")
    if 'os.execv(sys.executable, [sys.executable, str(BASE / "bot.py")])' not in rt:
        err("更新重启必须使用 BASE/bot.py，不能使用 Path(__file__)")


def check_package():
    base = ROOT / "deploy" / "files" / "bridge"
    for name in ("bot.py", "fishpond/registry.py", "web/index.html"):
        if not (base / name).exists():
            err(f"发布包缺少 {name}（先运行 make_release.py）")


def main():
    all_entries = load_registry_entries()
    dyn_ids = {e["id"] for e in all_entries if e.get("status") == "active"}
    entries = [e for e in all_entries if e.get("status") == "active"] + \
              [e for e in all_entries if e.get("status") != "active" and e["id"] not in dyn_ids]
    routes = registered_routes()
    for e in all_entries:
        if e.get("status") == "legacy" and e["id"] in dyn_ids:
            warn(f"{e['id']}: 已由模块注册，静态条目可删除")
    for e in entries:
        check_entry(e)
    check_routes(entries, routes)
    check_reverse_routes(entries, routes)
    check_settings(entries)
    check_frontend_api(entries, routes)
    check_tables(entries)
    check_modules(entries)
    check_index_sync()
    check_frontend()
    check_update_entrypoint()
    check_package()
    for w in WARNS:
        print("⚠", w)
    for x in ERRORS:
        print("✗", x)
    print(f"\n检查完成：{len(ERRORS)} 个错误，{len(WARNS)} 个提醒")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
