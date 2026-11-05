"""发布前 HTTP 冒烟：临时实例 + 假登录，逐个 GET 后台接口，抓 5xx。

用法：python smoke_http.py <包目录>
只在发布前跑，不进入用户包。
"""
import asyncio
import pathlib
import shutil
import sys
import tempfile
import time

SKIP_PREFIX = ("/g/", "/web/", "/stickers/", "/api/hosting", "/api/update",
               "/api/qr", "/api/napcat", "/api/voice/preview", "/api/voice/audio",
               "/api/selfcheck/run", "/api/featurecheck/run", "/api/image/test",
               "/api/apikey/test", "/api/providers/test", "/api/providers/autodetect")


def find_bridge(pkg: pathlib.Path) -> pathlib.Path:
    for cand in (pkg, pkg / "files", pkg / "bridge", pkg / "files" / "bridge"):
        if (cand / "bot.py").is_file() and (cand / "fishpond").is_dir():
            return cand
    for p in pkg.rglob("bot.py"):
        if (p.parent / "fishpond").is_dir():
            return p.parent
    raise SystemExit("包内找不到 bot.py + fishpond")


async def run(pkg_dir: str) -> int:
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    pkg = pathlib.Path(pkg_dir).resolve()
    src = find_bridge(pkg)
    work = pathlib.Path(tempfile.mkdtemp(prefix="smoke_fp_"))
    shutil.copytree(src, work, dirs_exist_ok=True)
    (work / "config.yaml").write_text("{}\n", encoding="utf-8")

    sys.path.insert(0, str(work))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("smoke_bot", work / "bot.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bridge = mod.Bridge(mod.load_config())
    finally:
        sys.path.pop(0)

    app = web.Application()
    app.middlewares.append(bridge.role_middleware())
    bridge.register_admin_routes(app)
    sid = "smoke-sid"
    bridge.auth_sessions[sid] = {"exp": time.time() + 3600, "id": 1, "username": "smoke", "role": "super"}

    paths = []
    for route in app.router.routes():
        if not getattr(route, "method", "") == "GET":
            continue
        p = route.resource.canonical
        if "{" in p or not p.startswith("/"):
            continue
        if any(p.startswith(x) for x in SKIP_PREFIX):
            continue
        paths.append(p)

    errors = []
    t0 = time.time()
    server = TestServer(app)
    client = TestClient(server, cookie_jar=None)
    await client.start_server()
    try:
        results = await asyncio.gather(
            *[client.get(p, cookies={"qb_sid": sid}) for p in paths],
            return_exceptions=True,
        )
        for p, r in zip(paths, results):
            if isinstance(r, Exception):
                errors.append(f"{p} 请求异常: {r}")
                continue
            if r.status >= 500:
                body = (await r.text())[:120].replace("\n", " ")
                errors.append(f"{p} -> {r.status} {body}")
            elif r.status == 401:
                errors.append(f"{p} -> 401（鉴权未生效）")
    finally:
        await client.close()

    cost = time.time() - t0
    shutil.rmtree(work, ignore_errors=True)
    print(f"冒烟接口 {len(paths)} 个，耗时 {cost:.1f}s，失败 {len(errors)} 个")
    for e in errors:
        print("✗", e)
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("用法: smoke_http.py <包目录>")
    sys.exit(asyncio.run(run(sys.argv[1])))
