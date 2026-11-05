"""发布前安全审计：扫描发布目录中的密钥、数据库、配置、可疑令牌。"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = ROOT / "deploy" / "files"
PATTERNS = [
    ("疑似 API Key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("疑似 48 位令牌", re.compile(r"\b[0-9a-f]{48}\b")),
    ("疑似密码赋值", re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*[\"'][^\"']{6,}[\"']")),
    ("私钥块", re.compile(r"BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY")),
]
BAD_NAMES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", "config.yaml"}


def main():
    issues = []
    if not FILES.is_dir():
        print("发布目录不存在，先运行 make_release.py")
        return 1
    for f in FILES.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix in BAD_NAMES or f.name.endswith((".db", ".db-wal", ".db-shm")):
            issues.append(f"不该打包的文件: {f.relative_to(FILES)}")
            continue
        if f.suffix not in (".py", ".js", ".html", ".css", ".sh", ".md", ".json", ".yaml", ".yml"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for name, pat in PATTERNS:
            for m in pat.finditer(text):
                issues.append(f"{name}: {f.relative_to(FILES)} → {m.group(0)[:40]}")
    for i in issues[:40]:
        print("✗", i)
    print(f"\n安全审计：{len(issues)} 个问题")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
