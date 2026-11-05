"""打目录更新包：bot.py + fishpond/ + web/ → dist/bot-package.tar.gz"""
import hashlib
import pathlib
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "deploy" / "files" / "bridge"
OUT_DIR = ROOT / "deploy" / "files"
OUT = OUT_DIR / "bot-package.tar.gz"


def main():
    for name in ("bot.py", "fishpond", "web"):
        assert (SRC / name).exists(), f"缺少 {name}，先运行 make_release.py"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(OUT, "w:gz") as tf:
        for name in ("bot.py", "fishpond", "web"):
            tf.add(SRC / name, arcname=name)
    data = OUT.read_bytes()
    print(f"包: {OUT}  {len(data)} 字节")
    print(f"sha256: {hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
