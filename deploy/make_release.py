#!/usr/bin/env python3
# 生成“对外发布版” bot.py
# 发布版：保留记忆功能；关闭观察者角色（本地保留）
#
# 只在本地生成产物，不上传、不改线上。真正发版另走 publish_pkg.sh。
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = ROOT / "bridge" / "bot_admin.py"
dst = pathlib.Path(__file__).resolve().parent / "files" / "bridge" / "bot.py"

s = src.read_text(encoding="utf-8")

# 关闭观察者角色（选项不显示、接口拒绝创建）
s = s.replace("VIEWER_FEATURE = True", "VIEWER_FEATURE = False")
# 剧本库上传/分发只在主人服务器开启，发布版关闭
s = s.replace("SCRIPT_HUB = True", "SCRIPT_HUB = False")

# ---- 发布前硬性检查 ----
errors = []

# 校验前端 JS 语法（前端已独立为 web/js/app.js）
try:
    import subprocess as _sp
    _js_file = ROOT / "fishpond" / "web" / "js" / "app.js"
    if _js_file.exists():
        _r = _sp.run(["node", "--check", str(_js_file)], capture_output=True, text=True)
        if _r.returncode != 0:
            errors.append("前端 JS 语法错误：" + (_r.stderr or "")[:300])
except FileNotFoundError:
    pass
except Exception as _e:
    errors.append("前端 JS 校验失败: %s" % _e)

# 注入作者预设（不含任何密钥），只对全新数据库生效
import json as _json
_presets_path = ROOT / "deploy" / "presets.json"
if _presets_path.exists():
    _presets = _json.loads(_presets_path.read_text(encoding="utf-8"))
    _forbidden = (
        "deepseek_api_key", "image_api_key", "image_api_key_zhipu",
        "voice_zhipu_key", "voice_zvoice_key", "voice_asr_key",
        "voice_doubao_api_key", "voice_doubao_token",
        "game_api_token", "game_dist_token", "napcat_webui_token",
    )
    _bad = [k for k in _presets if k in _forbidden or "api_key" in k or "token" in k.lower() and k not in ("balance_keywords", "roast_keywords", "sticker_capture_keywords")]
    if _bad:
        errors.append("预设里含有密钥类配置：" + ", ".join(_bad))
    s = s.replace("PRESET_SETTINGS = {}", "PRESET_SETTINGS = " + _json.dumps(_presets, ensure_ascii=False))


if "VIEWER_FEATURE = True" in s or "VIEWER_FEATURE = False" not in s:
    errors.append("观察者开关未关闭（必须是 VIEWER_FEATURE = False）")
if "SCRIPT_HUB = True" in s or "SCRIPT_HUB = False" not in s:
    errors.append("剧本库开关未关闭（发布版必须 SCRIPT_HUB = False）")
if "MEMORY_FEATURE = False" in s or "MEMORY_FEATURE = True" not in s:
    errors.append("记忆功能被误关（必须是 MEMORY_FEATURE = True）")

# 个人后台路径、统计后台地址、设备信息、密钥一律不许出现
FORBIDDEN = {
    r"xrzs\.cloud/xrzs": "个人后台路径",
    r"43\.132\.175\.12": "服务器 IP",
    r"/root/|/home/[a-z]": "本机绝对路径",
    r"sk-[A-Za-z0-9]{20,}": "疑似 API Key",
    r"[0-9a-f]{48}": "疑似 NapCat Token",
}
for pat, why in FORBIDDEN.items():
    m = re.search(pat, s)
    if m:
        errors.append(f"发现{why}：{m.group(0)[:12]}…（不要写进发布版）")

ver = ""
m = re.search(r'^APP_VERSION = "([0-9.]+)"', s, re.M)
if not m:
    errors.append("找不到 APP_VERSION")
else:
    ver = m.group(1)

try:
    compile(s, str(dst), "exec")
except SyntaxError as e:
    errors.append(f"语法错误：{e}")

if errors:
    print("!! 发布版检查未通过：")
    for e in errors:
        print("   -", e)
    sys.exit(1)

dst.write_text(s, encoding="utf-8")

# 前端静态文件：独立维护，部署到 bot.py 同级的 web/
_web_src = ROOT / "fishpond" / "web"
_web_dst = dst.parent / "web"
_pkg_src = ROOT / "fishpond"
_pkg_dst = dst.parent / "fishpond"
if _pkg_src.exists():
    import shutil as _sh
    if _pkg_dst.exists():
        _sh.rmtree(_pkg_dst)
    _sh.copytree(_pkg_src, _pkg_dst, ignore=_sh.ignore_patterns("__pycache__", "*.pyc", "web", "tools"))
    print(f"模块包: {_pkg_dst.relative_to(ROOT)}")

_web_dst.parent.mkdir(parents=True, exist_ok=True)
if _web_src.exists():
    import shutil as _sh2
    if _web_dst.exists():
        _sh2.rmtree(_web_dst)
    _sh2.copytree(_web_src, _web_dst)
    print(f"前端: {_web_dst.relative_to(ROOT)}")

# ---- 注册完整性校验（入口/路由/表/模块/INDEX/前端/包） ----
import subprocess as _sp2
_chk = _sp2.run([sys.executable, str(ROOT / "fishpond" / "tools" / "check_index.py")])
if _chk.returncode != 0:
    print("!! 注册完整性校验未通过，已中止发布")
    sys.exit(1)

_sec = _sp2.run([sys.executable, str(ROOT / "fishpond" / "tools" / "security_audit.py")])
if _sec.returncode != 0:
    print("!! 安全审计未通过，已中止发布")
    sys.exit(1)

print(f"发布版已生成: {dst}")
print(f"  版本: {ver}")
print(f"  大小: {dst.stat().st_size} 字节（{len(s)} 字符）")
print(f"  观察者: 关闭    记忆: 保留")
