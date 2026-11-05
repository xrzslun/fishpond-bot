#!/usr/bin/env python3
"""FishPond 关键纯函数单测。

用法：
    # 服务器上（venv 里有 aiohttp/pyyaml）
    /opt/qqbot/bridge/venv/bin/python3 -m unittest discover -s /opt/qqbot/tests -v
    # 或本地（需先装 aiohttp pyyaml）
    python3 -m unittest discover -s tests -v

被测模块按顺序查找：$BOT_PY → /opt/qqbot/bridge/bot.py → ../bridge/bot_admin.py
"""
import importlib.util
import os
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
CANDIDATES = [
    os.environ.get("BOT_PY") or "",
    "/opt/qqbot/bridge/bot.py",
    str(HERE.parent / "bridge" / "bot_admin.py"),
    str(HERE.parent / "deploy" / "files" / "bridge" / "bot.py"),
]


def load_bot():
    for cand in CANDIDATES:
        p = pathlib.Path(cand) if cand else None
        if p and p.is_file():
            spec = importlib.util.spec_from_file_location("bot_under_test", str(p))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, p
    raise unittest.SkipTest("找不到被测模块（设置 BOT_PY 环境变量）")


BOT, BOT_PATH = load_bot()


class TestSelfImage(unittest.TestCase):
    def test_should_trigger(self):
        for text in ("你自己", "画一张你自己", "你认为的自己", "画你", "画一个你",
                     "自画像", "你长什么样", "你的样子", "画一张AI", "画AI", "AI画像", "画个ai"):
            with self.subTest(text=text):
                self.assertTrue(BOT.is_self_image(text))

    def test_should_not_trigger(self):
        for text in ("一只猫在键盘上睡觉", "猫在海边奔跑", "画你们群的吉祥物", "画你的房间",
                     "画你说的那个场景", "赛博朋克城市", "画一幅油画", "一个女孩在弹吉他", ""):
            with self.subTest(text=text):
                self.assertFalse(BOT.is_self_image(text))

    def test_extra_stripped(self):
        self.assertEqual(BOT.self_image_extra("画一张你自己"), "")
        self.assertEqual(BOT.self_image_extra("画AI"), "")
        self.assertIn("吃面", BOT.self_image_extra("画AI在吃面"))


class TestSelfPrompt(unittest.TestCase):
    def test_build_contains_style_and_desc(self):
        q = BOT.build_self_image_prompt(BOT.SELF_STYLE_DEFAULT, BOT.SELF_DESC_DEFAULT)
        self.assertIn("Q版", q)
        self.assertIn("鲸鱼", q)
        self.assertLessEqual(len(q), 400)

    def test_extra_appended(self):
        q = BOT.build_self_image_prompt("风格A", "外观B", "在鱼缸里游泳")
        self.assertIn("风格A", q)
        self.assertIn("外观B", q)
        self.assertIn("在鱼缸里游泳", q)

    def test_truncated(self):
        q = BOT.build_self_image_prompt("x" * 900, "y" * 900)
        self.assertLessEqual(len(q), 400)


class TestImageCommand(unittest.TestCase):
    def test_parse(self):
        cases = {
            "画图 一只猫": "猫",
            "画一只猫在键盘上": "猫在键盘上",
            "帮我画一个蛋糕": "蛋糕",
            "来张图 夕阳": "夕阳",
            "生成一张 海边": "海边",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(BOT.Bridge.image_command_prompt(text), want)

    def test_not_command(self):
        for text in ("画风好奇怪", "画面太美", "我画了个圈", "", "画"):
            with self.subTest(text=text):
                self.assertEqual(BOT.Bridge.image_command_prompt(text), "")

    def test_help(self):
        for text in ("画图帮助", "生图怎么用", "怎么画图", "画AI帮助"):
            self.assertTrue(BOT.Bridge.image_help_requested(text))
        for text in ("画图", "画一只猫", "帮助"):
            self.assertFalse(BOT.Bridge.image_help_requested(text))


class TestMusicCommand(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(BOT.Bridge.music_command_keyword("播放 晴天"), "晴天")
        self.assertEqual(BOT.Bridge.music_command_keyword("来一首《七里香》"), "七里香")

    def test_empty(self):
        for text in ("播放列表", "放", "听歌", ""):
            self.assertEqual(BOT.Bridge.music_command_keyword(text), "")


class TestParseSegments(unittest.TestCase):
    def test_mixed(self):
        ev = {"message": [
            {"type": "text", "data": {"text": " 你好 "}},
            {"type": "at", "data": {"qq": "999"}},
            {"type": "image", "data": {"url": "http://a/1.png"}},
            {"type": "record", "data": {"url": "http://a/1.mp3"}},
            {"type": "reply", "data": {"id": "42"}},
        ]}
        seg = BOT.Bridge.parse_segments(ev, "999")
        self.assertEqual(seg["user_text"], "你好")
        self.assertTrue(seg["at_me"])
        self.assertEqual(seg["image_urls"], ["http://a/1.png"])
        self.assertEqual(seg["records"], ["http://a/1.mp3"])
        self.assertEqual(seg["reply_ids"], ["42"])

    def test_at_others_and_sticker(self):
        ev = {"message": [
            {"type": "at", "data": {"qq": "123"}},
            {"type": "mface", "data": {"file": "abc"}},
        ]}
        seg = BOT.Bridge.parse_segments(ev, "999")
        self.assertTrue(seg["at_others"])
        self.assertEqual(seg["at_target"], "123")
        self.assertEqual(seg["stickers"], 1)
        self.assertEqual(seg["image_urls"], [])


class TestParseQuoted(unittest.TestCase):
    def test_text_list(self):
        q = {"data": {"message": [{"type": "text", "data": {"text": "早上好"}}]}}
        text, img = BOT.Bridge.parse_quoted(q)
        self.assertEqual(text, "早上好")
        self.assertIsNone(img)

    def test_string_and_image(self):
        text, img = BOT.Bridge.parse_quoted({"data": {"message": "纯文本"}})
        self.assertEqual(text, "纯文本")
        self.assertIsNone(img)
        text, img = BOT.Bridge.parse_quoted({"data": {"message": [
            {"type": "image", "data": {"url": "http://a/x.jpg"}}]}})
        self.assertEqual(img, "http://a/x.jpg")
        self.assertEqual(text, "")

    def test_bad_input(self):
        self.assertEqual(BOT.Bridge.parse_quoted(None), ("", None))
        self.assertEqual(BOT.Bridge.parse_quoted({}), ("", None))


class TestAudioMime(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(BOT.audio_mime(b"RIFF\x00\x00\x00\x00WAVEfmt "), "audio/wav")
        self.assertEqual(BOT.audio_mime(b"ID3\x04\x00\x00"), "audio/mpeg")
        self.assertEqual(BOT.audio_mime(b"\xff\xfb\x90\x00"), "audio/mpeg")
        self.assertEqual(BOT.audio_mime(b"OggS\x00\x02"), "audio/ogg")
        self.assertEqual(BOT.audio_mime(b"garbage"), "audio/mpeg")


class TestSingRequest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(BOT.Bridge.sing_request("唱一首《晴天》"), "晴天")
        self.assertEqual(BOT.Bridge.sing_request("唱「孤勇者」给我听"), "孤勇者")
        self.assertEqual(BOT.Bridge.sing_request("唱个歌"), "")
        self.assertEqual(BOT.Bridge.sing_request("唱两句"), "")
        self.assertEqual(BOT.Bridge.sing_request("来一首 稻香"), "稻香")
        self.assertIsNone(BOT.Bridge.sing_request("今天天气不错"))
        self.assertIsNone(BOT.Bridge.sing_request(""))


class TestVersion(unittest.TestCase):
    def test_compare(self):
        vt = BOT.Bridge.version_tuple
        self.assertGreater(vt("3.5.10"), vt("3.5.9"))
        self.assertGreater(vt("3.5.1"), vt("3.5"))
        self.assertGreaterEqual(vt("3.5.0"), vt("3.5"))
        self.assertGreater(vt("4.0"), vt("3.99.99"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
