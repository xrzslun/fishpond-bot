"""扫描 registry，生成 INDEX.md（功能索引表）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import ast  # noqa: E402
from fishpond.registry import FEATURES  # noqa: E402

# 扫描 features/*/service.py 里的 add(...)，无需导入依赖
_dynamic = []
for _f in sorted(ROOT.glob("fishpond/**/*.py")):
    if "tools" in _f.parts or _f.name in ("__init__.py", "registry.py"):
        continue
    try:
        _tree = ast.parse(_f.read_text(encoding="utf-8"))
    except Exception:
        continue
    for _n in ast.walk(_tree):
        if isinstance(_n, ast.Call) and getattr(getattr(_n, "func", None), "id", "") == "add":
            kw = {}
            for k in _n.keywords:
                try:
                    kw[k.arg] = ast.literal_eval(k.value)
                except Exception:
                    kw[k.arg] = ""
            kw.setdefault("files", str(_f.relative_to(ROOT)))
            kw.setdefault("status", "active")
            _dynamic.append(kw)

_dyn_ids = {d.get("id") for d in _dynamic}
FEATURES = [f for f in FEATURES if f.get("id") not in _dyn_ids] + _dynamic


def main():
    rows = sorted(FEATURES, key=lambda x: (x.get("status") != "active", x.get("id", "")))
    out = ["# 功能索引（自动生成，勿手改）", "",
           f"共 {len(rows)} 项。修改功能请同步 registry。", "",
           "| 功能 ID | 名称 | 入口 | 接口 | 数据表 | 配置键 | 页面 | 文件 |",
           "|---|---|---|---|---|---|---|---|"]
    for f in rows:
        fmt = lambda v: "<br>".join(map(str, v)) if isinstance(v, (list, tuple)) and v else (str(v) if v else "—")
        out.append("| {id} | {name} | `{entry}` | {routes} | {tables} | {settings} | {ui} | `{files}` |".format(
            id=f.get("id", ""), name=f.get("name", ""), entry=f.get("entry", ""),
            routes=fmt(f.get("routes")), tables=fmt(f.get("tables")),
            settings=fmt(f.get("settings")), ui=fmt(f.get("ui")), files=f.get("files", "")))
    out += ["", "> 状态 `legacy` 表示仍在单文件里，迁移后会变为 `active` 并由模块注册。", ""]
    (ROOT / "INDEX.md").write_text("\n".join(out), encoding="utf-8")
    print(f"已生成 INDEX.md，共 {len(rows)} 项")


if __name__ == "__main__":
    main()
