"""对比两个发布目录，输出文件与版本差异。"""
import hashlib
import pathlib
import sys


def snap(d):
    d = pathlib.Path(d)
    out = {}
    for f in d.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            out[str(f.relative_to(d))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def main():
    if len(sys.argv) < 3:
        print("用法: make_diff.py <旧目录> <新目录>")
        return 2
    old, new = snap(sys.argv[1]), snap(sys.argv[2])
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    changed = sorted(k for k in new.keys() & old.keys() if old[k] != new[k])
    print(f"新增 {len(added)} / 删除 {len(removed)} / 修改 {len(changed)}")
    for tag, rows in (("+", added), ("-", removed), ("*", changed)):
        for r in rows[:60]:
            print(f" {tag} {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
