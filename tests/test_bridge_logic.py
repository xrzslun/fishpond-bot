#!/usr/bin/env python3
"""FishPond 业务逻辑测试：用临时 SQLite + 打桩，不联网、不碰生产库。

覆盖：生图权限/配额/供应商分流、配置局部保存、提醒队列、管理员与白名单、帮助文案。
运行（服务器）：
    BOT_PY=/opt/qqbot/bridge/bot.py /opt/qqbot/bridge/venv/bin/python3 -m unittest discover -s /opt/qqbot/tests -v
"""
import asyncio
import importlib.util
import os
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
CANDIDATES = [
    os.environ.get("BOT_PY") or "",
    "/opt/qqbot/bridge/bot.py",
    str(HERE.parent / "bridge" / "bot_admin.py"),
]


def load_bot():
    for cand in CANDIDATES:
        p = pathlib.Path(cand) if cand else None
        if p and p.is_file():
            spec = importlib.util.spec_from_file_location("bot_under_test2", str(p))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise unittest.SkipTest("找不到被测模块")


BOT = load_bot()
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class FakeReq:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


def make_bridge(store):
    b = BOT.Bridge.__new__(BOT.Bridge)
    b.store = store
    b.onebot = {}
    b.connected = False
    b.offline_since = None
    b._disconnects = 0
    b.sent = []
    b._delivered = False
    b.self_id = "999"

    async def fake_send(ws, mtype, ev, text, **kw):
        b.sent.append(text)

    async def fake_gen(prompt, enhance=True, uid=None, is_super=False):
        b.last_gen_prompt = prompt
        return PNG

    async def fake_send_img(ws, mtype, ev, data):
        b._delivered = True
        return True

    b.send = fake_send
    b.generate_image = fake_gen
    b.send_image_bytes = fake_send_img
    b.require_super = lambda req: {"role": "super"}
    return b


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = BOT.Store(pathlib.Path(self.tmp.name) / "test.db")
        self.b = make_bridge(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def run_async(self, coro):
        return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class TestImageScope(Base):
    def test_all(self):
        self.store.set_setting("image_scope", "all")
        self.assertTrue(self.b.image_scope_ok("group", "1", "2", False))

    def test_super_only(self):
        self.store.set_setting("image_scope", "super")
        self.assertFalse(self.b.image_scope_ok("group", "1", "2", False))
        self.assertTrue(self.b.image_scope_ok("group", "1", "2", True))

    def test_whitelist(self):
        self.store.set_setting("image_scope", "whitelist")
        self.assertFalse(self.b.image_scope_ok("group", "1", "2", False))
        self.store.add_wl("group", "1", None)
        self.assertTrue(self.b.image_scope_ok("group", "1", "2", False))
        self.assertFalse(self.b.image_scope_ok("group", "9", "2", False))


class TestHandleImage(Base):
    def _ev(self):
        return {"group_id": "1", "user_id": "123"}

    def test_disabled(self):
        self.store.set_setting("image_enabled", "0")
        self.run_async(self.b.handle_image(None, self._ev(), "group", "123", "猫", False))
        self.assertIn("生图功能还没开", "".join(self.b.sent))

    def test_scope_denied(self):
        self.store.set_setting("image_enabled", "1")
        self.store.set_setting("image_scope", "super")
        self.run_async(self.b.handle_image(None, self._ev(), "group", "123", "猫", False))
        self.assertIn("没有生图权限", "".join(self.b.sent))

    def test_quota_exceeded(self):
        self.store.set_setting("image_enabled", "1")
        self.store.set_setting("image_scope", "all")
        self.store.set_setting("image_daily_limit", "1")
        rid = self.store.image_log("123", "1", "猫")
        self.store.image_finish(rid, True)
        self.run_async(self.b.handle_image(None, self._ev(), "group", "123", "狗", False))
        self.assertIn("已经画了", "".join(self.b.sent))
        self.assertFalse(self.b._delivered)

    def test_super_unlimited(self):
        self.store.set_setting("image_enabled", "1")
        self.store.set_setting("image_scope", "all")
        self.store.set_setting("image_daily_limit", "1")
        self.store.set_setting("image_super_unlimited", "1")
        rid = self.store.image_log("123", "1", "猫")
        self.store.image_finish(rid, True)
        self.run_async(self.b.handle_image(None, self._ev(), "group", "123", "狗", True))
        self.assertTrue(self.b._delivered)

    def test_super_limited_when_switch_off(self):
        self.store.set_setting("image_enabled", "1")
        self.store.set_setting("image_scope", "all")
        self.store.set_setting("image_daily_limit", "1")
        self.store.set_setting("image_super_unlimited", "0")
        rid = self.store.image_log("123", "1", "猫")
        self.store.image_finish(rid, True)
        self.run_async(self.b.handle_image(None, self._ev(), "group", "123", "狗", True))
        self.assertFalse(self.b._delivered)

    def test_success_logged(self):
        self.store.set_setting("image_enabled", "1")
        self.store.set_setting("image_scope", "all")
        self.store.set_setting("image_daily_limit", "5")
        self.run_async(self.b.handle_image(None, self._ev(), "group", "123", "猫", False))
        self.assertTrue(self.b._delivered)
        self.assertEqual(self.store.image_count_today("123"), 1)


class TestImageProviderPayload(Base):
    def _capture(self, prompt, **settings):
        for k, v in settings.items():
            self.store.set_setting(k, v)
        # Base 里把 generate_image 打了桩，这里换回真实实现
        self.b.generate_image = BOT.Bridge.generate_image.__get__(self.b)
        captured = {}

        async def fake_call(base, key, payload, timeout=180):
            captured.update({"base": base, "key": key, "payload": payload})
            return PNG

        self.b._image_call = fake_call
        self.run_async(self.b.generate_image(prompt, enhance=False))
        return captured

    def test_siliconflow(self):
        c = self._capture("一只猫", image_provider="siliconflow", image_model="Qwen/Qwen-Image",
                          image_size="1024x1024", image_api_key="sk-test")
        p = c["payload"]
        self.assertEqual(c["base"], "https://api.siliconflow.cn/v1")
        self.assertEqual(p["image_size"], "1024x1024")
        self.assertIn("num_inference_steps", p)
        self.assertNotIn("quality", p)

    def test_zhipu(self):
        c = self._capture("一只猫", image_provider="zhipu", image_model="glm-image",
                          image_size="1280x1280", image_api_key_zhipu="zp-test")
        p = c["payload"]
        self.assertIn("open.bigmodel.cn", c["base"])
        self.assertEqual(p["model"], "glm-image")
        self.assertEqual(p["size"], "1280x1280")
        self.assertEqual(p["quality"], "hd")
        self.assertFalse(p["watermark_enabled"])
        self.assertNotIn("num_inference_steps", p)
        self.assertNotIn("negative_prompt", p)

    def test_zhipu_model_mismatch_falls_back(self):
        c = self._capture("一只猫", image_provider="zhipu", image_model="Qwen/Qwen-Image",
                          image_size="1024x1024", image_api_key_zhipu="zp-test")
        self.assertEqual(c["payload"]["model"], "glm-image")
        self.assertEqual(c["payload"]["size"], "1280x1280")

    def test_siliconflow_model_mismatch_falls_back(self):
        c = self._capture("一只猫", image_provider="siliconflow", image_model="glm-image",
                          image_size="1280x1280", image_api_key="sk-test")
        self.assertEqual(c["payload"]["model"], "Qwen/Qwen-Image")


class TestConfigPartialSave(Base):
    def test_image_partial(self):
        b = self.b
        self.run_async(b.api_image_config(FakeReq({"model": "Qwen/Qwen-Image", "negative": "低质量"})))
        self.run_async(b.api_image_config(FakeReq({"daily_limit": "7"})))
        self.assertEqual(self.store.get_setting("image_model"), "Qwen/Qwen-Image")
        self.assertEqual(self.store.get_setting("image_negative"), "低质量")
        self.assertEqual(self.store.get_setting("image_daily_limit"), "7")

    def test_voice_partial_save_keeps_key(self):
        b = self.b
        self.run_async(b.api_voice_config(FakeReq({"zvoice_key": "abc123", "zvoice_style": "语气轻快"})))
        self.assertEqual(self.store.get_setting("voice_zvoice_key"), "abc123")
        self.assertEqual(self.store.get_setting("voice_zvoice_style"), "语气轻快")
        # 只改风格不应清空 Key
        self.run_async(b.api_voice_config(FakeReq({"zvoice_style": "温柔一点"})))
        self.assertEqual(self.store.get_setting("voice_zvoice_key"), "abc123")
        self.assertEqual(self.store.get_setting("voice_zvoice_style"), "温柔一点")

    def test_image_provider_switch(self):
        b = self.b
        self.run_async(b.api_image_config(FakeReq({"provider": "zhipu", "model": "glm-image"})))
        self.assertEqual(self.store.get_setting("image_provider"), "zhipu")


class TestReminders(Base):
    def test_due_and_done(self):
        import time as _t
        now = int(_t.time())
        self.store.reminder_add("123", "", "过去的提醒", now - 60, "刚才")
        self.store.reminder_add("123", "", "未来的提醒", now + 3600, "一小时后")
        due = self.store.reminder_due(now)
        self.assertEqual(len(due), 1)
        self.assertIn("过去的提醒", due[0]["text"] or due[0].get("content", ""))
        self.store.reminder_done(due[0]["id"])
        self.assertEqual(len(self.store.reminder_due(now)), 0)


class TestReminderParse(Base):
    def test_empty_task_not_saved(self):
        class M:
            pass
        msg = BOT.ProactiveMessenger.__new__(BOT.ProactiveMessenger)
        msg.b = self.b
        msg.store = self.store
        self.run_async(BOT.ProactiveMessenger.handle(msg, None, {"user_id": "123"}, "private", "123", "提醒我"))
        with self.store._conn() as c:
            n = c.execute("select count(*) from reminders").fetchone()[0]
        self.assertEqual(n, 0)

    def test_task_without_time_saved(self):
        msg = BOT.ProactiveMessenger.__new__(BOT.ProactiveMessenger)
        msg.b = self.b
        msg.store = self.store
        self.run_async(BOT.ProactiveMessenger.handle(msg, None, {"user_id": "123"}, "private", "123", "提醒我 买牛奶"))
        rows = self.store.reminder_pending("123")
        self.assertEqual(len(rows), 1)


class TestAdminsAndWhitelist(Base):
    def test_super_and_allowed(self):
        # 超管 QQ 列表来自 settings.super_admin_qqs（不是网页管理员表）
        self.store.set_setting("super_admin_qqs", "2844642318,123456789")
        self.assertTrue(self.b.is_super_admin("2844642318"))
        self.assertIn("2844642318", self.b.super_admin_qqs())
        self.assertTrue(self.b.allowed("group", "1", "123"))
        self.store.add_wl("group", "1", None)
        self.assertTrue(self.b.allowed("group", "1", "123"))
        self.assertFalse(self.b.allowed("group", "2", "123"))

    def test_blacklist(self):
        self.store.add_black("666", "坏人")
        self.assertTrue(self.store.is_black("666"))
        self.store.remove_black("666")
        self.assertFalse(self.store.is_black("666"))



class TestPrepareVoice(Base):
    def test_transcode_mp3_and_trim(self):
        import shutil, wave, io, struct, math
        if not shutil.which("ffmpeg"):
            self.skipTest("无 ffmpeg")
        buf = io.BytesIO()
        w = wave.open(buf, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        # 0.5 秒静音 + 1 秒 440Hz，共 1.5 秒
        frames = b"\x00\x00" * 12000
        tone = struct.pack("<" + "h" * 24000, *[int(8000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(24000)])
        w.writeframes(frames + tone); w.close()
        raw = buf.getvalue()
        out = self.run_async(BOT.Bridge.prepare_voice(self.b, raw))
        self.assertTrue(out[:3] == b"ID3", "应转成 mp3")
        self.assertLess(len(out), len(raw), "体积应变小")

    def test_empty_passthrough(self):
        self.assertEqual(self.run_async(BOT.Bridge.prepare_voice(self.b, b"")), b"")


class TestLeadingBeep(Base):
    def test_detect_synthetic_beeps(self):
        try:
            import numpy as np
        except Exception:
            self.skipTest("无 numpy")
        sr = 24000
        def tone(dur, freq=560):
            t = np.arange(int(sr * dur)) / sr
            return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        def silence(dur):
            return np.zeros(int(sr * dur), dtype=np.float32)
        # 两组 560Hz 提示音 + 停顿 + 一段"人声"（用噪声模拟：宽带、非单一音高）
        rng = np.random.default_rng(7)
        speech = (0.25 * rng.standard_normal(int(sr * 1.2))).astype(np.float32)
        x = np.concatenate([tone(0.4), silence(0.2), tone(0.4), silence(0.2), speech])
        pcm = (x * 32767).astype(np.int16).tobytes()
        cut = BOT.Bridge.leading_beep_seconds(pcm, sr)
        self.assertGreaterEqual(cut, 0.7)   # 应裁掉两组提示音
        self.assertLessEqual(cut, 1.25)     # 不应吃进人声

    def test_no_beep_no_cut(self):
        try:
            import numpy as np
        except Exception:
            self.skipTest("无 numpy")
        sr = 24000
        x = (0.3 * np.sin(2 * np.pi * 800 * np.arange(sr) / sr)).astype(np.float32)
        self.assertEqual(BOT.Bridge.leading_beep_seconds((x * 32767).astype(np.int16).tobytes(), sr), 0.0)


class TestGlm4VoicePayload(Base):
    def test_payload_shape(self):
        p = BOT.Bridge.build_glm4voice_payload("你好", "语气轻快")
        self.assertEqual(p["model"], "glm-4-voice")
        self.assertFalse(p["stream"])
        # system 必须是字符串，user 必须是 text 段数组（智谱要求）
        self.assertIsInstance(p["messages"][0]["content"], str)
        self.assertIsInstance(p["messages"][1]["content"], list)
        self.assertEqual(p["messages"][1]["content"][0]["type"], "text")
        self.assertEqual(p["messages"][1]["content"][0]["text"], "你好")

    def test_context_injected(self):
        p = BOT.Bridge.build_glm4voice_payload("你好", "语气轻快", "我是一只叫大肥鱼的猫")
        sys_msg = p["messages"][0]["content"]
        self.assertIn("大肥鱼", sys_msg)
        self.assertIn("不要回答它", sys_msg)
        self.assertIn("语气轻快", sys_msg)




class TestPolishPcm(Base):
    def test_tail_and_fades(self):
        try:
            import numpy as np
        except Exception:
            self.skipTest("无 numpy")
        sr = 24000
        x = (0.3 * np.sin(2 * np.pi * 300 * np.arange(sr) / sr)).astype(np.float32)
        pcm = (x * 32767).astype(np.int16).tobytes()
        out = BOT.Bridge.polish_pcm(pcm, sr)
        y = np.frombuffer(out, dtype=np.int16).astype(np.float32)
        # 末尾补了静音（比原长）
        self.assertGreater(len(y), len(x))
        # 末尾有约 0.5 秒静音
        self.assertLess(float(np.abs(y[-int(sr*0.45):]).max()), 50)
        self.assertGreater(len(y), len(x) + int(sr * 0.45))
        # 开头淡入：第一个样本应接近 0
        self.assertLess(abs(float(y[0])), 2000)


class TestSuperTextToggle(Base):
    def test_toggle(self):
        self.run_async(self.b.api_voice_config(FakeReq({"super_text": True})))
        self.assertEqual(self.store.get_setting("voice_super_text"), "1")
        self.run_async(self.b.api_voice_config(FakeReq({"super_text": False})))
        self.assertEqual(self.store.get_setting("voice_super_text"), "0")


class TestVoiceWanted(Base):
    def test_modes(self):
        b = self.b
        self.store.set_setting("voice_tts_enabled", "1")
        self.store.set_setting("voice_super_text", "0")   # 预设可能带 1，测试里先归零
        self.store.set_setting("super_admin_qqs", "10001")
        # voice_in：只有对方发语音才回
        self.store.set_setting("voice_tts_mode", "voice_in")
        self.assertFalse(b.voice_wanted(False, "10001", "你好"))
        self.assertTrue(b.voice_wanted(True, "20002", "你好"))
        # always：全部回
        self.store.set_setting("voice_tts_mode", "always")
        self.assertTrue(b.voice_wanted(False, "20002", "你好"))
        # super：只有超管文字才回
        self.store.set_setting("voice_super_text", "1")
        self.store.set_setting("voice_tts_mode", "voice_in")
        self.assertTrue(b.voice_wanted(False, "10001", "你好"))   # 超管文字也回
        self.assertFalse(b.voice_wanted(False, "20002", "你好"))  # 普通用户文字不回
        self.assertTrue(b.voice_wanted(True, "20002", "你好"))    # 普通用户发语音仍回
        self.store.set_setting("voice_super_text", "0")
        self.assertFalse(b.voice_wanted(False, "10001", "你好"))  # 关掉后超管文字不回
        # 明确要求“发语音”也回
        self.assertTrue(b.voice_wanted(False, "20002", "发条语音听听"))
        # TTS 关闭时一律不回
        self.store.set_setting("voice_tts_enabled", "0")
        self.assertFalse(b.voice_wanted(True, "10001", "发语音"))


class TestHandleSingArgs(Base):
    def test_args_order(self):
        """回归：handle_sing 的 (ws, mtype, ev, user_id, song) 参数顺序不能错，否则 ev 变成字符串。"""
        b = self.b
        sent = {}
        async def fake_llm(*a, **k): return "啦啦啦，今天也要开心呀"
        async def fake_send(ws, mtype, ev, text, at_qq=None):
            sent["mtype"], sent["ev"], sent["text"] = mtype, ev, text
        b.llm_complete = fake_llm
        b.send = fake_send
        b.tts_on = lambda: False
        b.reply_count = 0
        ok = self.run_async(b.handle_sing(object(), "private", {"user_id": "123"}, "123", ""))
        self.assertTrue(ok)
        self.assertEqual(sent.get("mtype"), "private")
        self.assertIsInstance(sent.get("ev"), dict)
        self.assertIn("🎵", sent.get("text", ""))


class TestSelfEcho(Base):
    def test_detect_echo(self):
        b = self.b
        b.remember_outgoing("今天终于把功能都做完了，还挺顺利的。")
        self.assertTrue(b.looks_like_self_echo("今天终于把功能都做完了还挺顺利的"))
        self.assertFalse(b.looks_like_self_echo("给我唱首歌听一下"))


class TestDefaultSuperAdmin(Base):
    def test_first_account_becomes_super(self):
        """新部署：第一个账号必须是超级管理员，否则后台超管功能不可用。"""
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "t.db"
            st = BOT.Store(path)
            st.add_admin("first", "pw")          # 模拟旧逻辑：role 默认 admin
            st2 = BOT.Store(path)                # 重新初始化触发保底
            self.assertEqual(st2.account_by_name("first")["role"], "super")

    def test_ensure_default_admin_is_super(self):
        b = self.b
        b.ensure_default_admin({"default_admin": {"username": "fresh", "password": "pw"}})
        self.assertEqual(self.store.account_by_name("fresh")["role"], "super")

    def test_create_account_super(self):
        with tempfile.TemporaryDirectory() as d:
            st = BOT.Store(pathlib.Path(d) / "t.db")
            st.create_account("admin2", "pw", "super")
            self.assertEqual(st.account_by_name("admin2")["role"], "super")


class TestCaptureKeyword(Base):
    def test_position_first_then_length(self):
        kws = ["添加表情包", "收录", "存表情", "保存表情包"]
        # 命令词在最前：即使含义里也有别的词，也选最靠前的
        self.assertEqual(BOT.Bridge.match_capture_keyword("保存表情包 思考", kws), "保存表情包")
        self.assertEqual(BOT.Bridge.match_capture_keyword("存表情 生气", kws), "存表情")
        # 含义很长、且包含另一个关键词，仍以位置为准
        self.assertEqual(
            BOT.Bridge.match_capture_keyword("收录 这是一个很长的思考过程不要动", ["收录", "思考"]), "收录")
        # 同一位置取更长的
        self.assertEqual(BOT.Bridge.match_capture_keyword("存表情", ["存表", "存表情"]), "存表情")
        self.assertIsNone(BOT.Bridge.match_capture_keyword("今天天气不错", kws))


class TestGameMode(Base):
    def _prep(self):
        b = self.b
        sent = []
        async def fake_llm(messages, **kw):
            return "赤月挂在天上。\n┆ 状态 · 第1天 06:10 ┆\n生命 100｜感染 0\nA 起身｜B 躲着｜C 找水"
        async def fake_send(ws, mtype, ev, text, **kw):
            sent.append(text)
        b.llm_messages = fake_llm
        b.send = fake_send
        return b, sent

    def test_player_without_script_is_told_to_contact_admin(self):
        b, sent = self._prep()
        self.store.set_setting("super_admin_qqs", "99999")
        self.store.player_set("123", script_id=None, active=1)
        ok = self.run_async(b.handle_game(object(), "private", {"user_id": "123"}, "123", "在吗"))
        self.assertTrue(ok)
        self.assertIn("99999", sent[0])

    def test_unassigned_qq_not_intercepted(self):
        b, sent = self._prep()
        ok = self.run_async(b.handle_game(object(), "private", {"user_id": "555"}, "555", "在吗"))
        self.assertFalse(ok)
        self.assertEqual(sent, [])

    def test_turn_saves_messages_and_run(self):
        b, sent = self._prep()
        sid = self.store.script_add("赤月2039", "x" * 80, "末世")
        self.store.player_set("777", script_id=sid, active=1)
        ok = self.run_async(b.handle_game(object(), "private", {"user_id": "777"}, "777", "开始"))
        self.assertTrue(ok)
        runs = self.store.run_list("777")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_no"], 1)
        msgs = self.store.msg_list(runs[0]["id"], 10)
        self.assertEqual(len(msgs), 2)          # 用户 + AI
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("赤月", sent[0])

    def test_restart_creates_second_run(self):
        b, sent = self._prep()
        sid = self.store.script_add("赤月2039", "x" * 80, "末世")
        self.store.player_set("888", script_id=sid, active=1)
        self.run_async(b.handle_game(object(), "private", {"user_id": "888"}, "888", "开始"))
        rid = self.store.run_create("888", sid)
        self.assertEqual(self.store.run_get(rid)["run_no"], 2)
        self.assertEqual(len(self.store.run_list("888")), 2)

    def test_group_not_intercepted(self):
        b, sent = self._prep()
        sid = self.store.script_add("赤月2039", "x" * 80, "末世")
        self.store.player_set("666", script_id=sid, active=1)
        self.assertFalse(self.run_async(b.handle_game(object(), "group", {"group_id": "1"}, "666", "开始")))

    def test_watermark_invisible(self):
        out = BOT.Bridge.watermark_prompt("abcdef", "token123")
        self.assertGreater(len(out), len("abcdef"))
        self.assertEqual(out.replace("\u200b", "").replace("\u200c", ""), "abcdef")


class TestGameContexts(Base):
    def test_group_context_switch(self):
        st = self.store
        st.ctx_set("10001", "100", 2)
        self.assertEqual(st.ctx_get("10001", "100")["active"], 1)
        # 后接入的群生效，前一个自动失效（决策 2A）
        st.ctx_set("10001", "200", 2)
        self.assertEqual(st.ctx_get("10001", "100")["active"], 0)
        self.assertEqual(st.ctx_get("10001", "200")["active"], 1)
        self.assertEqual(st.ctx_active("10001")["group_id"], "200")
        st.ctx_deactivate("10001", "200")
        self.assertEqual(st.ctx_get("10001", "200")["active"], 0)
        self.assertFalse(st.ctx_active("10001"))


class TestGameDelete(Base):
    def test_purge_and_keep(self):
        st = self.store
        for qq in ("20001", "20002"):
            st.player_set(qq, script_id=2, active=1)
            rid = st.run_create(qq, 2)
            st.msg_add(rid, "user", "hi", 1)
            st.ctx_set(qq, "555", 2)
        stat = st.player_delete("20001", purge=True)
        self.assertGreaterEqual(stat["runs"], 1)
        self.assertGreaterEqual(stat["messages"], 1)
        self.assertEqual(stat["contexts"], 1)
        self.assertFalse(st.player_get("20001"))
        self.assertEqual(st.run_list("20001"), [])
        self.assertEqual([c for c in st.ctx_list() if c["qq"] == "20001"], [])
        # purge=False：保留存档，只结束局与解绑
        stat2 = st.player_delete("20002", purge=False)
        self.assertEqual(stat2["runs"], 0)
        self.assertFalse(st.player_get("20002"))
        runs = st.run_list("20002")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "finished")
        self.assertEqual([c for c in st.ctx_list() if c["qq"] == "20002"], [])


class TestPureTrim(Base):
    def test_trim_wav_without_ffmpeg(self):
        try:
            import numpy as np
        except Exception:
            self.skipTest("无 numpy")
        import io, wave
        sr = 24000
        tone = (0.4 * np.sin(2 * np.pi * 560 * np.arange(int(sr * 0.5)) / sr)).astype(np.float32)
        rng = np.random.default_rng(5)
        speech = (0.25 * rng.standard_normal(int(sr * 1.5))).astype(np.float32)
        x = np.concatenate([tone, np.zeros(int(sr * 0.2), dtype=np.float32), speech])
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        out = BOT.Bridge.trim_wav_pure(buf.getvalue())
        with wave.open(io.BytesIO(out), "rb") as w2:
            self.assertLess(w2.getnframes(), int(sr * 2.2))   # 裁掉了开头
            self.assertGreater(w2.getnframes(), int(sr * 1.2))  # 人声还在


class TestHelpText(unittest.TestCase):
    def test_text(self):
        class S:
            def get_setting(self, k, d=""):
                return {"image_daily_limit": "5", "image_super_unlimited": "1"}.get(k, d)

        b = BOT.Bridge.__new__(BOT.Bridge)
        b.store = S()
        txt = BOT.Bridge.image_help_text(b, False)
        self.assertIn("画图", txt)
        self.assertIn("画AI", txt)
        self.assertIn("5 张", txt)
        self.assertIn("不限", BOT.Bridge.image_help_text(b, True))


class TestImageCleanup(Base):
    def test_stale_pending(self):
        rid = self.store.image_log("123", "1", "卡住的图")
        # 把创建时间改到 1 小时前，模拟异常退出遗留
        with self.store._conn() as c:
            c.execute("UPDATE image_jobs SET created_at=datetime('now','localtime','-60 minutes') WHERE id=?", (rid,))
        self.assertEqual(self.store.image_count_today("123"), 0)
        self.assertGreaterEqual(self.store.image_cleanup_stale(10), 1)
        with self.store._conn() as c:
            row = c.execute("select status from image_jobs where id=?", (rid,)).fetchone()
        self.assertEqual(row["status"], "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
