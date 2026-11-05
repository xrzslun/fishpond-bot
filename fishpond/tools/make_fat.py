"""生成单文件发行版：bot.py 内嵌 fishpond/ 与 web/ 的 zip，启动时自解压。
兼容旧版 updater（只覆盖 bot.py），也兼容新版目录包。"""
import base64
import io
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "deploy" / "files" / "bridge"
OUT = ROOT / "deploy" / "files" / "bot_fat.py"


def main():
    src = (BRIDGE / "bot.py").read_text(encoding="utf-8")
    ver = re.search(r'APP_VERSION = "([^"]+)"', src).group(1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("fishpond", "web"):
            base = BRIDGE / name
            for f in base.rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts:
                    zf.write(f, f.relative_to(BRIDGE).as_posix())
    blob = base64.b64encode(buf.getvalue()).decode()
    bootstrap = f'''# ---- 内置模块包（单文件发行版，启动时自解压） ----
_FP_PKG_VER = "{ver}"
_FP_PKG_B64 = (
{_wrap(blob)}
)


def _fp_extract():
    import base64 as _b64
    import io as _io
    import pathlib as _pl
    import zipfile as _zf
    root = _pl.Path(__file__).resolve().parent
    mark = root / ".pkg_version"
    try:
        if mark.is_file() and mark.read_text(encoding="utf-8").strip() == _FP_PKG_VER:
            return
    except Exception:
        pass
    try:
        _zf.ZipFile(_io.BytesIO(_b64.b64decode(_FP_PKG_B64))).extractall(root)
        mark.write_text(_FP_PKG_VER, encoding="utf-8")
    except Exception as _e:
        print("内置模块包解压失败:", _e)


_fp_extract()

'''
    anchor = "import sys as _sys0"
    idx = src.index(anchor)
    fat = src[:idx] + bootstrap + src[idx:]
    OUT.write_text(fat, encoding="utf-8")
    print(f"单文件发行版: {OUT}  {OUT.stat().st_size} 字节 | 版本 {ver}")


def _wrap(s, width=120):
    return "\n".join(f'    "{s[i:i+width]}"' for i in range(0, len(s), width))


if __name__ == "__main__":
    main()
