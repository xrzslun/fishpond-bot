#!/usr/bin/env python3
"""更新路径回归测试：防止再次把更新写到 admin.py 自身。

覆盖：
1. 静态：更新目标与重启入口必须使用 BASE/bot.py；
2. 动态：目录包解压后写入 bot.py / fishpond / web，且不动无关文件。
"""
import importlib.util
import io
import os
import pathlib
import tarfile
import tempfile
import unittest

CANDIDATES = [
    os.environ.get("BOT_PY") or "",
    "/opt/qqbot/bridge/bot.py",
    str(pathlib.Path(__file__).resolve().parent.parent / "bridge" / "bot_admin.py"),
]


def load_bot():
    for cand in CANDIDATES:
        p = pathlib.Path(cand) if cand else None
        if p and p.is_file():
            spec = importlib.util.spec_from_file_location("bot_for_update_test", str(p))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, p.parent
    raise unittest.SkipTest("找不到 bot.py")


class TestUpdateEntrypoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot, cls.base = load_bot()

    def test_admin_uses_base_bot(self):
        adm = (self.base / "fishpond" / "platforms" / "admin.py").read_text(encoding="utf-8")
        self.assertIn('target = BASE / "bot.py"', adm,
                      "更新目标必须是 BASE/bot.py，不能用 Path(__file__)")
        self.assertNotIn("target = Path(__file__).resolve()", adm)

    def test_restart_uses_base_bot(self):
        rt = (self.base / "fishpond" / "features" / "runtime" / "service.py").read_text(encoding="utf-8")
        self.assertIn('os.execv(sys.executable, [sys.executable, str(BASE / "bot.py")])', rt,
                      "重启必须使用 BASE/bot.py，不能用 Path(__file__)")

    def test_package_apply_writes_expected_files(self):
        work = pathlib.Path(tempfile.mkdtemp(prefix="updtest_"))
        try:
            pkg = io.BytesIO()
            with tarfile.open(fileobj=pkg, mode="w:gz") as tf:
                def add(name, data):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))
                add("bot.py", b'APP_VERSION = "9.9.9"\n')
                add("fishpond/registry.py", b"# registry\n")
                add("web/index.html", b"<html>ok</html>\n")
            target = work / "target"
            (target / "fishpond").mkdir(parents=True)
            (target / "fishpond" / "old.py").write_text("old\n", encoding="utf-8")
            (target / "bot.py").write_text('APP_VERSION = "0.0.1"\n', encoding="utf-8")
            ver = self.bot.Bridge.apply_update_package(None, pkg.getvalue(), target, work / "bak")
            self.assertEqual(ver, "9.9.9")
            self.assertIn('9.9.9', (target / "bot.py").read_text(encoding="utf-8"))
            self.assertTrue((target / "fishpond" / "registry.py").is_file())
            self.assertTrue((target / "web" / "index.html").is_file())
            self.assertFalse((target / "fishpond" / "old.py").exists())
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
