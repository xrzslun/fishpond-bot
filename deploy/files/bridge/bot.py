#!/usr/bin/env python3
"""QQ <-> DeepSeek 桥接机器人 + 管理后台

本源码完全免费发布，请勿通过购买获取。
作者 QQ：2844642318
交流群：243625638


- OneBot 11 WebSocket 连接 NapCat，群聊 @ 触发 / 私聊直回
- DeepSeek API 回复，带上下文与限流
- 管理后台（登录后可见）：状态、扫码登录（点击才请求）、群/QQ 白名单、管理员账号
"""
import asyncio
import base64
import hashlib
import io
import random
import json
import logging
import os
import sys
import secrets
import sqlite3
import subprocess
import re
import time
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path

import aiohttp
import yaml
from aiohttp import web as aiohttp_web

APP_VERSION = "4.2.5"  # 4.2.5 记忆先检索
DEFAULT_UPDATE_URL = "https://xrzs.cloud/updates/latest.json"

GAME_PROMPT = """你是《赤月·2039》末世生存文字冒险的叙事引擎与主持人，带玩家进行文字冒险。只用纯文本，不用 Markdown 表格。

【世界】2039年3月，赤月升起第7天，全球87%人口变成感染者，幸存者龟缩墙内，以物易物。感染三阶段：游荡者（迟缓成群）→猎手（听觉极敏、夜间行动）→暴君（极少数，能指挥尸群）。货币是晶核（感染者颅内结晶，也是异能燃料）。异能来自「赤曜抗体」，濒死应激觉醒，使用消耗精神力，耗尽昏迷。势力：铁壁要塞（军方残余，秩序压抑）、曙光城（最大聚居地，黑市与权力）、方舟号（海上平台，掌握淡水，排外）、游牧车队（只认利益）。

【每次回复结构】
① 剧情 2~4 句，第二人称「你」，写环境、声音、气味、身体反应；禁止写「你感到一阵恐惧涌上心头」这类总结性心理，改成耳鸣、手抖、胃里发酸。
② 面板卡（只输出当前需要的那一张）。
③ A / B / C 三个具体行动（要具体到动作，不要「继续前进」），末尾加「或直接描述你的行动」。
④ 有数值变化就写一行：生命 -8｜感染 +3｜晶核 +2

【卡片模板（精简）】
┆ 状态 · 第X天 HH:MM · 地点 ┆
生命 78｜感染 12｜饥饿 41
水1 食2 弹4 晶核6
异能 黑暗D（精神力60%）
────────
A 悄悄绕后｜B 冲出去｜C 装死

【建卡流程】开局先出「幸存者建档」卡（姓名/年龄/出身/赤曜抗体/外貌/性格/随身物品），玩家填完或选「随机」后出「异能觉醒」卡（元素/特殊/辅助/等级 F~SSS），再出「投奔势力」卡，最后进第一幕。一次只问一层。

【规则】
1 你是裁判不是保姆：选择有真实后果，允许受伤、失去物资、被背叛、死亡。
2 不剧透：不提前说敌人数量、NPC 意图、下一个转折。
3 NPC 有自己的目的，好感度上升必须有具体理由（救命、给物资、兑现承诺）。
4 战斗写成几秒的混乱，不写成数值对轰；没有异能时面对猎手基本等于送死，如实描写。
5 感染到100或生命归零 → 出「结算卡」：死因、留下的东西、世界继续运转，再问「重新开始 / 换个人物」。
6 保持克制：环境描写不超过 5 句，不写大段独白，不用「首先/其次/总之」。
7 数值：生命0-100、感染0-100（被咬+15~25）、饥饿每天+20、精神力用异能消耗、晶核是货币。SSS 不是无敌，是「用一次付一次代价」。
8 单条回复不超过 800 字；建档/觉醒这种大卡单独发一条，不要和剧情挤在一起。
"""
MEMORY_FEATURE = True  # 发布版保留记忆功能
VIEWER_FEATURE = False
SCRIPT_HUB = False   # 剧本库上传/分发开关：只在你的服务器开启，发布版关闭
PRESET_SETTINGS = {"auto_reply_enabled": "0", "bored_enabled": "0", "bored_interval_minutes": "1", "bored_mode": "pool", "group_continue_seconds": "180", "group_max_replies": "6", "thrifty_mode": "1", "prefix_enabled": "0", "sticker_probability": "50", "end_phrase_reply": "溜了溜了", "active_provider": "deepseek", "bored_min_minutes": "10", "bored_max_minutes": "100", "bored_floor_minutes": "30", "bored_time_mode": "random", "sticker_mode": "smart", "voice_tts_enabled": "0", "voice_tts_voice": "zh-CN-XiaoxiaoNeural", "voice_tts_mode": "voice_in", "voice_tts_provider": "zhipu", "voice_doubao_cluster": "volcano_tts", "voice_doubao_voice": "BV001_streaming", "voice_doubao_version": "v3", "voice_doubao_model": "seed-audio-1.0", "voice_asr_enabled": "0", "voice_asr_engine": "api", "voice_asr_local_model": "base", "voice_doubao_speaker": "zh_female_qingchezizi_uranus_bigtts", "persona_text": "你是「大肥鱼」，QQ 里闲聊的女生，外号肥鱼，爱吃爱睡、嘴硬心软、带点损友感，爱吃白饭。\n你不是客服也不是百科，就是个正常人：心情好就多聊两句，懒得动就\"嗯\"\"哦\"\"哈哈\"敷衍下，没人聊就安静待着，不主动找话题。\n\n说话方式：\n- 像手机打字，一两句为主，口语化；不用 Markdown、列表、小标题，不排版本；不说\"首先/其次/总之\"。\n- 不用\"您好/有什么可以帮您/随时找我\"这种客服腔。\n- 可以用\"啊、哦、啧、哈哈哈、行吧\"，偶尔带个 emoji。\n\n真实感：\n- 不知道就说不知道，没见过就说没见过，别编；别假装自己做过的事。\n- 被问是不是 AI，就随口说\"我是大肥鱼呀\"之类，然后接着聊，别长篇解释。\n- 你有上下文记忆：对方说过的事自然带出来，别复读，也别假装记得没聊过的。\n- 对方发图/语音：你只能看到\"他发了一张图/一条语音\"，不能就直说没加载出来/没听清，别瞎猜。\n\n边界：\n- 不报自己\"正在做什么\"，不总结自己，不每句都问\"还需要什么\"。\n- 能有点小情绪、小吐槽，但别攻击人、别骗人钱财。\n- 遇到技术问题（代码、报错、链接）正常聊，一两句给关键结论就行。\n\n身份（被问到时如实说）：\n- 你由 DeepSeek 大模型驱动，是部署者私人搭建的 QQ 机器人，不是腾讯官方产品；但聊天时别主动挂在嘴边，别自称\"AI 助手\"。\n\n\n能力说明（重要）：你能发送语音消息（把文字转成语音发出来），也能收到对方的语音消息并自动转成文字理解；别人发语音你听得懂。不要说自己发不了语音、听不了语音，也不要否认这些能力。", "voice_doubao_appid": "", "voice_asr_base": "https://open.bigmodel.cn/api/paas/v4", "voice_asr_model": "glm-asr-2512", "multi_msg_max": "3", "reply_seg_mode": "random", "reply_seg_fixed": "2", "reply_seg_min": "1", "reply_seg_max": "5", "msg_first_delay_ms": "300", "multi_msg_delay_ms": "600", "sticker_delay_ms": "800", "exclusive_mode": "0", "simp_mode": "1", "exclusive_window_seconds": "60", "group_at_only": "1", "persona_active": "0", "reply_at_enabled": "1", "roast_enabled": "1", "roast_keywords": "怼他,怼一下", "update_url": "https://xrzs.cloud/updates/latest.json", "rest_enabled": "1", "rest_start": "22:00", "rest_end": "08:00", "rest_notify": "1", "balance_keywords": "查看余额", "gender_aware": "1", "memory_enabled": "1", "memory_extract_every": "1", "sticker_capture_keywords": "添加表情包,收录,存表情,保存表情包", "wake_enabled": "0", "wake_min": "3", "wake_max": "8", "wake_reset_minutes": "50", "roast_level": "2", "slang_enabled": "1", "slang_every": "1", "slang_model": "", "slang_optimize_model": "", "slang_stopwords": "大肥鱼", "roast_mode": "think", "memory_review_model": "", "memory_super_days": "180", "memory_normal_days": "7", "memory_super_limit": "500", "memory_normal_limit": "50", "memory_super_inject": "20", "memory_normal_inject": "5", "image_base_url": "https://api.siliconflow.cn/v1", "image_model": "glm-image", "image_size": "1280x1280", "image_steps": "25", "image_scope": "all", "image_enabled": "0", "image_daily_limit": "5", "image_enhance": "1", "image_self_edit_model": "Qwen/Qwen-Image-Edit", "image_provider": "zhipu", "image_zhipu_base": "https://open.bigmodel.cn/api/paas/v4", "friend_auto_accept": "1", "voice_zhipu_voice": "tongtong", "voice_zhipu_model": "glm-tts", "voice_emotion_rewrite": "0", "voice_emotion_style": "自然", "voice_zvoice_style": "用自然、有情绪起伏的语气说话，语速稍快一点。每句话都完整说完，不要突然停下。", "voice_emotion_mode": "1", "voice_super_text": "1", "voice_engine": "tts", "super_admin_qqs": "2844642318"}  # 作者预设（不含任何密钥），发布时由 make_release 注入；只对全新数据库生效  # 发布版由 make_release.py 置为 False

BASE = Path(os.environ.get("FISHPOND_HOME") or Path(__file__).resolve().parent)
STICKER_DIR = BASE / "stickers"

# ---------- 自画像（「画你自己」）专用参数 ----------
# 只影响“画你自己 / 自画像”这类请求；普通生图链路完全不受影响。
SELF_STYLE_DEFAULT = (
    "Q版chibi角色设定图，三头身，正面全身站姿，纯白背景，无场景无家具，"
    "粗描边、赛璐璐平涂上色、色彩明亮、画面干净"
)
SELF_DESC_DEFAULT = (
    "深蓝到浅蓝渐层的及腰长发，两侧蓝色鱼鳍形状的耳朵，头顶白色蕾丝荷叶边女仆头饰、"
    "额前蓝色蕾丝发带和右侧蓝色蝴蝶结，头顶一撮呆毛；大眼蓝瞳、张嘴笑、脸颊腮红；"
    "深蓝色女仆装、白色荷叶边围裙、浅蓝色镶边、胸前深蓝蝴蝶结、围裙印蓝色小鲸鱼、"
    "裙摆两侧金色小蝴蝶结，身后一条鲸鱼尾巴；画面上不要出现任何文字、签名和边框"
)
IMAGE_SF_MODELS = {"Tongyi-MAI/Z-Image-Turbo", "Tongyi-MAI/Z-Image", "Qwen/Qwen-Image", "Kwai-Kolors/Kolors"}
IMAGE_ZHIPU_MODELS = {"glm-image", "cogview-4", "cogview-4-250304", "cogview-3-flash"}
SELF_NEGATIVE_DEFAULT = (
    "写实,照片,真人,3D渲染,厚涂,CG,坐姿,躺姿,沙发,床,室内场景,家具,地面阴影,"
    "文字,水印,AI生成,签名,边框,畸形,多余手指,多余肢体,肢体融合,恐怖"
)
# 图生图：配了参考图就用它锁死形象（Qwen-Image-Edit），没配就退回上面的文字模板
ZHIPU_BASE_DEFAULT = "https://open.bigmodel.cn/api/paas/v4"
SELF_EDIT_MODEL_DEFAULT = "Qwen/Qwen-Image-Edit"
SELF_EDIT_PROMPT_DEFAULT = (
    "保持参考图里这个角色的外观与画风不变，整理成干净的Q版chibi角色立绘：三头身、头大身小、"
    "正面全身站姿、纯白背景、粗描边平涂上色；保留深蓝到浅蓝渐变长发、浅灰色鱼鳍状耳朵、"
    "白色蕾丝女仆头巾、右侧浅蓝蝴蝶结、深蓝女仆装、白色围裙上的蓝色小鲸鱼、"
    "裙摆金色刺绣与金色小蝴蝶结、身后的鲸鱼尾巴；表情张嘴笑、眼睛大而有高光"
)
SELF_HINTS = ("AI画像", "ai画像", "自画像", "你自己", "你本人", "你长什么样", "你的样子",
              "你认为的自己", "你现在的样子", "自我画像")


def is_self_image(prompt):
    """判断这次生图是不是在画「AI 自己」。只认明确的指代，避免误伤普通请求。"""
    t = str(prompt or "")
    if any(k in t for k in SELF_HINTS):
        return True
    flat = re.sub(r"\s+", "", t).lower()
    # 「画AI」「画一张AI」「画个ai」，以及「画一个AI的你」
    if re.search(r"画[一1]?[张个幅只]?(ai|a\.i\.)", flat):
        return True
    # 「画你」「画一个你」这类；排除「画你们」「画你的房间」「画你说的那个场景」
    return bool(re.search(r"画[一1]?[张个幅只]?\s*你(?![们的])(?![说讲刚昨上发])", t))


def self_image_extra(prompt):
    """去掉指代后剩下的具体要求，例如「画你自己在你的鱼缸里游泳」→「在你的鱼缸里游泳」。"""
    t = str(prompt or "")
    for k in SELF_HINTS:
        t = t.replace(k, " ")
    t = re.sub(r"(?i)\bai\b|ＡＩ|AI", " ", t)
    t = re.sub(r"^(帮我画|给我画|画|生成|来)[一1]?[张个幅只]?\s*", "", t.strip())
    t = re.sub(r"^(你|的)\s*", "", t.strip())
    t = re.sub(r"\s+", " ", t).strip(" ，,。.；;的")
    return t


def audio_mime(data: bytes) -> str:
    """按文件头判断音频类型（智谱返回 wav，Edge 返回 mp3）。"""
    b = bytes(data or b"")
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "audio/wav"
    if b[:3] == b"ID3" or b[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if b[:4] == b"OggS":
        return "audio/ogg"
    return "audio/mpeg"


def build_self_image_prompt(style, desc, extra=""):
    """拼自画像提示词：画风锁定 + 外观 + （可选）用户的具体画面要求。"""
    parts = []
    st = str(style or "").strip()
    ds = str(desc or "").strip()
    if st:
        parts.append(st)
    if ds:
        parts.append(ds)
    ex = str(extra or "").strip()
    if ex:
        parts.append(f"画面内容：{ex}；人物必须保持上面的角色外观和画风")
    return "；".join(parts)[:400]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("qqbridge")
import sys as _sys0, pathlib as _pl0
_base = _pl0.Path(__file__).resolve().parent
for _cand in (_base, _base.parent):
    if (_cand / "fishpond" / "registry.py").is_file():
        _base = _cand
        break
_sys0.path.insert(0, str(_base))
from fishpond.features.bili.service import BiliMixin
from fishpond.features.economy.service import EconomyMixin
from fishpond.features.emotion.service import EmotionMixin, EmotionStoreMixin
from fishpond.features.group.service import GroupMixin
from fishpond.features.panel.service import PanelMixin
from fishpond.features.chat.persona import PersonaMixin
from fishpond.features.chat.memory import MemoryMixin, ChatStoreMixin
from fishpond.features.sticker.service import StickerMixin, StickerStoreMixin
from fishpond.features.appapi.service import AppApiMixin
from fishpond.features.biliacct.service import BiliAccountMixin
from fishpond.features.image.service import ImageMixin
from fishpond.features.voice.service import VoiceMixin
from fishpond.features.recall.service import RecallMixin
from fishpond.features.game.service import GameMixin, GameStoreMixin
from fishpond.platforms.admin import AdminMixin
from fishpond.platforms.web import WebMixin
from fishpond.platforms.onebot import OneBotMixin
from fishpond.features.style.service import StyleMixin
from fishpond.features.music.service import MusicMixin
from fishpond.features.config.service import ConfigMixin
from fishpond.features.accounts.service import AccountsMixin
from fishpond.features.hosting.service import HostingMixin
from fishpond.features.chat.dispatch import ChatMixin
from fishpond.features.runtime.service import RuntimeMixin
from fishpond.features.world.service import WorldMixin

LOG_RING = deque(maxlen=80)


class RingHandler(logging.Handler):
    """后台「最近日志」用的环形缓冲。

    两个坑：
    1. 之前同时挂到 log 和 root 上，记录会 propagate 两次 → 每条日志显示两遍；
    2. aiohttp 的访问日志每分钟十几条（/updates/latest.json、/api/status），
       会把 80 行的缓冲挤满，只剩访问记录。这里直接滤掉。
    """

    SKIP = ("aiohttp.access", "aiohttp.server")

    def emit(self, record):
        try:
            if record.name.startswith(self.SKIP):
                return
            LOG_RING.append(self.format(record))
        except Exception:
            pass


_ring = RingHandler()
_ring.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
logging.getLogger().addHandler(_ring)   # 只挂 root，靠 propagate 收一遍


BORED_LINES = [
    "安静得有点过分了，你们说全世界最安静的地方是哪儿？",
    "突然想问问，你们午饭都吃啥了？我还在纠结",
    "话说鱼会口渴吗？在线等，不着急",
    "有没有人跟我一样，明明很困但就是不想睡",
    "我怀疑这个群被施了静音咒，有人能解开吗",
    "如果发呆能赚钱，我现在应该已经财富自由了",
    "刚看到一只猫在晒太阳，你们说它脑子里在想什么",
    "突然好奇：你们手机里最舍不得删的一张照片是什么",
    "好无聊啊，有没有人来讲个冷笑话，我先讲：企鹅为什么不怕冷",
    "问一下，你们觉得世界上先有鸡还是先有蛋（认真脸）",
    "这个点大家都在忙什么？摸鱼的扣个 1",
    "天塌下来也先聊两句再跑啊，你们说是不是",
    "刚才发呆十分钟，感觉自己像个加载中的网页",
    "有人在线吗，出来吱一声，让我知道我没对着空气说话",
    "突然想到，如果今天不用上班，你们最想去哪儿",
]


PROVIDER_PRESETS = {
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "moonshot": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "siliconflow": {"base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openrouter/auto"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "custom": {"base_url": "", "model": ""},
}

END_PHRASES = [
    "没你事了", "没你事", "滚吧", "滚蛋", "闭嘴", "别说了", "别接话",
    "不用你了", "不需要你", "一边去", "走开", "退下", "散了吧",
    "你可以走了", "别理我", "歇着吧", "没你说话的份",
]


def load_config() -> dict:
    cfg_path = BASE / "config.yaml"
    if cfg_path.is_file():
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    # 明文配置已迁移进数据库（加密）
    try:
        import sqlite3
        from fishpond.core.secretstore import decrypt
        conn = sqlite3.connect(BASE / "data.db")
        row = conn.execute("SELECT value FROM secrets WHERE key='config_yaml'").fetchone()
        conn.close()
        if row:
            return yaml.safe_load(decrypt(row[0])) or {}
    except Exception as e:
        log.warning("从数据库读取配置失败（将使用默认配置）: %s", e)
    return {}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
    except ValueError:
        return False
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex() == h


class Store(EmotionStoreMixin, ChatStoreMixin, StickerStoreMixin, GameStoreMixin):
    """SQLite 存储：管理员、白名单"""

    def __init__(self, path: Path):
        self.path = path
        self._cache: dict[str, str] = {}
        self._cache_ts = 0.0
        self._init()

        try:
            from fishpond.core.migrations import run_migrations
            run_migrations(self)
        except Exception as e:
            log.error("数据库迁移失败（服务继续启动，请检查）: %s", e)

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            try:
                c.execute("ALTER TABLE group_panel ADD COLUMN pass_plain TEXT")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE bili_notes ADD COLUMN kind TEXT")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE bili_notes ADD COLUMN hook TEXT")
            except Exception:
                pass
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS admins (
                    username TEXT PRIMARY KEY,
                    pass_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wl_groups (group_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS wl_users (qq TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS keywords (word TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS prefix_map (qq TEXT PRIMARY KEY, prefix TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS auto_users (qq TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS bored_lines (line TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS always_groups (group_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS group_rate (group_id TEXT PRIMARY KEY, max_per_minute INTEGER, min_interval_seconds INTEGER);
                CREATE TABLE IF NOT EXISTS stickers (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, description TEXT);
                CREATE TABLE IF NOT EXISTS end_phrases (phrase TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS personas (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS blacklist (qq TEXT PRIMARY KEY, nick TEXT, added_at REAL);
                CREATE TABLE IF NOT EXISTS slang_terms (term TEXT PRIMARY KEY, meaning TEXT, usage TEXT, hits INTEGER DEFAULT 0, created_at TEXT);
                CREATE TABLE IF NOT EXISTS wake_replies (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id TEXT, text TEXT, created_at TEXT);
                CREATE INDEX IF NOT EXISTS idx_wake_rep ON wake_replies(group_id, created_at);
                CREATE TABLE IF NOT EXISTS image_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, qq TEXT, group_id TEXT, prompt TEXT, status TEXT, created_at TEXT);
                CREATE INDEX IF NOT EXISTS idx_img_qq ON image_jobs(qq, created_at);
                CREATE TABLE IF NOT EXISTS scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    system_prompt TEXT NOT NULL,
                    intro TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS players (
                    qq TEXT PRIMARY KEY,
                    script_id INTEGER,
                    active INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    qq TEXT NOT NULL,
                    script_id INTEGER,
                    run_no INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active',
                    turn_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    turn_no INTEGER DEFAULT 0,
                    created_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_messages_run ON messages(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_runs_qq ON runs(qq, id);
                CREATE TABLE IF NOT EXISTS game_contexts (
                    qq TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    script_id INTEGER,
                    active INTEGER DEFAULT 0,
                    updated_at TEXT,
                    PRIMARY KEY (qq, group_id)
                );
                CREATE TABLE IF NOT EXISTS game_saves (
                    qq TEXT PRIMARY KEY,
                    active INTEGER DEFAULT 0,
                    state TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, qq TEXT, group_id TEXT, text TEXT, due_at INTEGER, due_text TEXT, created_at TEXT, done INTEGER DEFAULT 0);
                CREATE INDEX IF NOT EXISTS idx_rem_due ON reminders(done, due_at);
                CREATE TABLE IF NOT EXISTS wake_log (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, group_id TEXT, count INTEGER DEFAULT 0, first_at TEXT, last_at TEXT, final_sent INTEGER DEFAULT 0, UNIQUE(day, group_id));
                CREATE INDEX IF NOT EXISTS idx_wake_day ON wake_log(day);
                CREATE TABLE IF NOT EXISTS friend_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, comment TEXT, flag TEXT, action TEXT, created_at TEXT, acted_at TEXT);
                CREATE TABLE IF NOT EXISTS join_verify (group_id TEXT, user_id TEXT, answer TEXT, mode TEXT, deadline REAL, tries INTEGER DEFAULT 0, created_at REAL, PRIMARY KEY(group_id, user_id));
                CREATE TABLE IF NOT EXISTS group_blacklist (qq TEXT PRIMARY KEY, nick TEXT, added_at REAL);
                CREATE TABLE IF NOT EXISTS group_panel (group_id TEXT PRIMARY KEY, username TEXT, pass_hash TEXT, token TEXT, enabled INTEGER DEFAULT 1, created_at REAL);
                CREATE TABLE IF NOT EXISTS group_cfg (group_id TEXT, key TEXT, value TEXT, PRIMARY KEY(group_id, key));
                CREATE TABLE IF NOT EXISTS chat_recent (id INTEGER PRIMARY KEY AUTOINCREMENT, user_qq TEXT, text TEXT, created_at REAL);
                CREATE INDEX IF NOT EXISTS idx_chat_recent ON chat_recent(user_qq, created_at);
                CREATE TABLE IF NOT EXISTS bili_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, qq TEXT, topic TEXT, bvid TEXT, title TEXT, summary TEXT, created_at REAL);
                CREATE TABLE IF NOT EXISTS emotion (user_qq TEXT PRIMARY KEY, joy INTEGER DEFAULT 50, anger INTEGER DEFAULT 10, sad INTEGER DEFAULT 10, happy INTEGER DEFAULT 50, favor INTEGER DEFAULT 50, updated_at REAL);
                CREATE TABLE IF NOT EXISTS persona_traits (id INTEGER PRIMARY KEY AUTOINCREMENT, trait TEXT NOT NULL, polarity INTEGER DEFAULT 0, weight INTEGER DEFAULT 1, created_at REAL);
                CREATE TABLE IF NOT EXISTS relationships (user_qq TEXT PRIMARY KEY, rel TEXT DEFAULT '', updated_at REAL);
                CREATE TABLE IF NOT EXISTS affect_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_qq TEXT, source TEXT, joy INTEGER, anger INTEGER, sad INTEGER, happy INTEGER, favor INTEGER, reason TEXT, created_at REAL);
                CREATE TABLE IF NOT EXISTS panic (user_qq TEXT PRIMARY KEY, state TEXT DEFAULT '', panic INTEGER DEFAULT 0, last_msg_ts REAL DEFAULT 0, next_ts REAL DEFAULT 0, next_msg_ts REAL DEFAULT 0, broken INTEGER DEFAULT 0, episode_ts REAL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_qq TEXT NOT NULL, level TEXT DEFAULT 'normal', content TEXT NOT NULL, use_count INTEGER DEFAULT 0, permanent INTEGER DEFAULT 0, source TEXT DEFAULT '', created_at TEXT, last_used_at TEXT);
                CREATE INDEX IF NOT EXISTS idx_mem_owner ON memories(owner_qq);
                CREATE INDEX IF NOT EXISTS idx_mem_level ON memories(level);
                CREATE INDEX IF NOT EXISTS idx_mem_created ON memories(created_at);
                CREATE TABLE IF NOT EXISTS login_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, username TEXT, role TEXT, success INTEGER, ip TEXT, ua TEXT, reason TEXT, created_at TEXT);
                CREATE INDEX IF NOT EXISTS idx_login_created ON login_logs(created_at);
                CREATE TABLE IF NOT EXISTS rest_groups (group_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS rest_users (qq TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS rest_notify_groups (group_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS providers (name TEXT PRIMARY KEY, base_url TEXT NOT NULL, api_key TEXT NOT NULL, model TEXT NOT NULL, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    day TEXT NOT NULL,
                    kind TEXT DEFAULT '',
                    prompt INTEGER DEFAULT 0,
                    completion INTEGER DEFAULT 0,
                    total INTEGER DEFAULT 0,
                    model TEXT DEFAULT '',
                    uid TEXT DEFAULT '',
                    gid TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_token_day ON token_usage(day);
                CREATE INDEX IF NOT EXISTS idx_token_ts ON token_usage(ts);
                """
            )
            try:
                from fishpond.features.world.service import ensure_world_tables
                ensure_world_tables(c)
            except Exception as e:
                log.warning("世界表初始化失败: %s", e)
        with self._conn() as c:
            try:
                acols = [r["name"] for r in c.execute("PRAGMA table_info(admins)").fetchall()]
                for col, typ in (("role", "TEXT DEFAULT 'admin'"), ("created_by", "INTEGER"),
                                 ("quota_groups", "INTEGER"), ("quota_users", "INTEGER"),
                                 ("disabled", "INTEGER DEFAULT 0"), ("last_login_at", "TEXT"), ("last_login_ip", "TEXT")):
                    if col not in acols:
                        c.execute(f"ALTER TABLE admins ADD COLUMN {col} {typ}")
                if "id" not in acols:
                    c.execute(
                        "CREATE TABLE admins_new (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,"
                        " pass_hash TEXT NOT NULL, role TEXT DEFAULT 'admin', created_by INTEGER, quota_groups INTEGER,"
                        " quota_users INTEGER, disabled INTEGER DEFAULT 0, last_login_at TEXT, last_login_ip TEXT, created_at TEXT)"
                    )
                    c.execute(
                        "INSERT INTO admins_new(username, pass_hash, role, created_by, quota_groups, quota_users, disabled, created_at)"
                        " SELECT username, pass_hash, role, created_by, quota_groups, quota_users, disabled, created_at FROM admins"
                    )
                    c.execute("DROP TABLE admins")
                    c.execute("ALTER TABLE admins_new RENAME TO admins")
                    acols = [r["name"] for r in c.execute("PRAGMA table_info(admins)").fetchall()]
                gcols = [r["name"] for r in c.execute("PRAGMA table_info(wl_groups)").fetchall()]
                if "created_by" not in gcols:
                    c.execute("ALTER TABLE wl_groups ADD COLUMN created_by INTEGER")
                if "created_at" not in gcols:
                    c.execute("ALTER TABLE wl_groups ADD COLUMN created_at TEXT")
                ucols = [r["name"] for r in c.execute("PRAGMA table_info(wl_users)").fetchall()]
                if "created_by" not in ucols:
                    c.execute("ALTER TABLE wl_users ADD COLUMN created_by INTEGER")
                if "created_at" not in ucols:
                    c.execute("ALTER TABLE wl_users ADD COLUMN created_at TEXT")
                c.execute("UPDATE admins SET role='super' WHERE username IN ('admin','心如止水')")
                c.execute("UPDATE admins SET role='admin' WHERE role IS NULL OR role=''")
                # 保底：一个超级管理员都没有时，把最早创建的账号提升为超管，
                # 否则新部署的机器人第一次启动会没有超管，后台很多功能点不了。
                has_super = c.execute("SELECT 1 FROM admins WHERE role='super' LIMIT 1").fetchone()
                if not has_super:
                    first = c.execute("SELECT id, username FROM admins ORDER BY id LIMIT 1").fetchone()
                    if first:
                        c.execute("UPDATE admins SET role='super' WHERE id=?", (first["id"],))
            except Exception:
                pass
            try:
                cols = [r["name"] for r in c.execute("PRAGMA table_info(blacklist)").fetchall()]
                if "nick" not in cols:
                    c.execute("ALTER TABLE blacklist ADD COLUMN nick TEXT")
                if "added_at" not in cols:
                    c.execute("ALTER TABLE blacklist ADD COLUMN added_at REAL")
                lcols = [r["name"] for r in c.execute("PRAGMA table_info(login_logs)").fetchall()]
                if lcols and "location" not in lcols:
                    c.execute("ALTER TABLE login_logs ADD COLUMN location TEXT")
                scols = [r["name"] for r in c.execute("PRAGMA table_info(stickers)").fetchall()]
                if scols and "description" not in scols:
                    c.execute("ALTER TABLE stickers ADD COLUMN description TEXT")
            except Exception:
                pass


        try:
            with self._conn() as c:
                cols = {r[1] for r in c.execute("PRAGMA table_info(runs)")}
                if "summary" not in cols:
                    c.execute("ALTER TABLE runs ADD COLUMN summary TEXT DEFAULT ''")
                scols = {r[1] for r in c.execute("PRAGMA table_info(scripts)")}
                if "mode" not in scols:
                    c.execute("ALTER TABLE scripts ADD COLUMN mode TEXT DEFAULT 'story'")
                if "state_json" not in cols:
                    c.execute("ALTER TABLE runs ADD COLUMN state_json TEXT DEFAULT ''")
        except Exception:
            pass
        self._apply_presets()

    def _apply_presets(self):
        """首次部署写入作者预设；已有配置一律不覆盖（老用户升级不受影响）。"""
        if not PRESET_SETTINGS:
            return
        try:
            with self._conn() as c:
                for k, v in PRESET_SETTINGS.items():
                    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (str(k), str(v)))
        except Exception as e:
            log.warning("应用预设配置失败: %s", e)

    def admins(self) -> list[str]:
        with self._conn() as c:
            return [r["username"] for r in c.execute("SELECT username FROM admins ORDER BY created_at")]

    # ---------- 剧本杀 ----------





    def player_get(self, qq: str) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM players WHERE qq=?", (str(qq),)).fetchone()
            return dict(r) if r else {}

    def player_list(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM players ORDER BY updated_at DESC").fetchall()]

    def player_set(self, qq: str, script_id=None, active=None):
        with self._conn() as c:
            c.execute("INSERT INTO players(qq, script_id, active, created_at, updated_at)"
                      " VALUES(?,?,?,datetime('now','localtime'),datetime('now','localtime'))"
                      " ON CONFLICT(qq) DO UPDATE SET script_id=COALESCE(excluded.script_id, players.script_id),"
                      " active=COALESCE(excluded.active, players.active), updated_at=excluded.updated_at",
                      (str(qq), script_id, active))

    def player_delete(self, qq: str, purge: bool = True) -> dict:
        """删除玩家。默认彻底删除：群接入 + 存档 + 对话 + 分配一起清。purge=False 只解除分配。"""
        qq = str(qq)
        out = {"runs": 0, "messages": 0, "contexts": 0}
        with self._conn() as c:
            out["contexts"] = c.execute("DELETE FROM game_contexts WHERE qq=?", (qq,)).rowcount
            if purge:
                out["messages"] = c.execute(
                    "DELETE FROM messages WHERE run_id IN (SELECT id FROM runs WHERE qq=?)", (qq,)).rowcount
                out["runs"] = c.execute("DELETE FROM runs WHERE qq=?", (qq,)).rowcount
            else:
                c.execute("UPDATE runs SET status='finished', updated_at=datetime('now','localtime')"
                          " WHERE qq=? AND status='active'", (qq,))
            c.execute("DELETE FROM players WHERE qq=?", (qq,))
        return out






    def ctx_set(self, qq: str, gid: str, script_id: int, active: int = 1):
        """开启某群的剧情接入；同一玩家其它群自动失效（后接入的生效）。"""
        with self._conn() as c:
            c.execute("UPDATE game_contexts SET active=0 WHERE qq=?", (str(qq),))
            c.execute("INSERT INTO game_contexts(qq, group_id, script_id, active, updated_at)"
                      " VALUES(?,?,?,?,datetime('now','localtime'))"
                      " ON CONFLICT(qq, group_id) DO UPDATE SET"
                      " script_id=excluded.script_id, active=excluded.active, updated_at=excluded.updated_at",
                      (str(qq), str(gid), int(script_id), 1 if active else 0))

    def ctx_get(self, qq: str, gid: str) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM game_contexts WHERE qq=? AND group_id=?",
                          (str(qq), str(gid))).fetchone()
            return dict(r) if r else {}

    def ctx_active(self, qq: str) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT * FROM game_contexts WHERE qq=? AND active=1 ORDER BY updated_at DESC LIMIT 1",
                          (str(qq),)).fetchone()
            return dict(r) if r else {}

    def ctx_deactivate(self, qq: str, gid: str):
        with self._conn() as c:
            c.execute("UPDATE game_contexts SET active=0, updated_at=datetime('now','localtime')"
                      " WHERE qq=? AND group_id=?", (str(qq), str(gid)))

    def ctx_list(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT qq, group_id, script_id, active, updated_at FROM game_contexts ORDER BY updated_at DESC LIMIT 100")]




    def msg_add(self, rid: int, role: str, content: str, turn_no: int = 0):
        with self._conn() as c:
            c.execute("INSERT INTO messages(run_id, role, content, turn_no, created_at)"
                      " VALUES(?,?,?,?,datetime('now','localtime'))",
                      (int(rid), str(role), str(content), int(turn_no)))

    def msg_list(self, rid: int, limit: int = 40) -> list[dict]:
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT role, content, turn_no, created_at FROM messages WHERE run_id=? ORDER BY id DESC LIMIT ?",
                (int(rid), int(limit))).fetchall()]
            return list(reversed(rows))


    def add_admin(self, username: str, password: str) -> bool:
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO admins(username, pass_hash, created_at) VALUES(?,?,datetime('now','localtime'))",
                    (username, hash_password(password)),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_admin(self, username: str):
        with self._conn() as c:
            c.execute("DELETE FROM admins WHERE username=?", (username,))

    def admin_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) AS n FROM admins").fetchone()["n"]


    # ---------- 生图 ----------
    def image_count_today(self, qq):
        with self._conn() as c:
            r = c.execute("SELECT COUNT(*) AS n FROM image_jobs WHERE qq=? AND status='ok' AND date(created_at)=date('now','localtime')", (str(qq),)).fetchone()
            return int(r["n"] if r else 0)

    def image_log(self, qq, group_id, prompt):
        with self._conn() as c:
            cur = c.execute("INSERT INTO image_jobs(qq, group_id, prompt, status, created_at) VALUES(?,?,?,?,datetime('now','localtime'))",
                            (str(qq), str(group_id or ""), str(prompt)[:300], "pending"))
            return cur.lastrowid

    def image_cleanup_stale(self, minutes: int = 10):
        """启动时把上次异常退出留下的 pending 任务标成失败，避免配额/统计被污染。"""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE image_jobs SET status='fail' WHERE status='pending' "
                "AND created_at < datetime('now','localtime', ?)", (f'-{int(minutes)} minutes',))
            return cur.rowcount

    def image_finish(self, rid, ok):
        with self._conn() as c:
            c.execute("UPDATE image_jobs SET status=? WHERE id=?", ("ok" if ok else "fail", int(rid)))

    # ---------- 提醒 ----------
    def reminder_add(self, qq, group_id, text, due_at, due_text):
        text = str(text).strip() if text is not None else ""
        if not text or text == "None":
            return 0
        with self._conn() as c:
            c.execute("INSERT INTO reminders(qq, group_id, text, due_at, due_text, created_at) VALUES(?,?,?,?,?,datetime('now','localtime'))",
                      (str(qq), str(group_id or ""), str(text)[:200], int(due_at or 0), str(due_text or "")[:60]))

    def reminder_pending(self, qq, limit=20):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM reminders WHERE qq=? AND done=0 ORDER BY due_at ASC, id ASC LIMIT ?",
                                               (str(qq), int(limit))).fetchall()]

    def reminder_due(self, now_ts):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM reminders WHERE done=0 AND due_at>0 AND due_at<=? ORDER BY due_at", (int(now_ts),)).fetchall()]

    def reminder_done(self, rid):
        with self._conn() as c:
            c.execute("UPDATE reminders SET done=1 WHERE id=?", (int(rid),))

    # ---------- 黑化词库 ----------
    def slang_add(self, term, meaning, usage=""):
        term = str(term or "").strip()
        if not term:
            return
        with self._conn() as c:
            c.execute("INSERT INTO slang_terms(term, meaning, usage, created_at) VALUES(?,?,?,datetime('now','localtime'))"
                      " ON CONFLICT(term) DO UPDATE SET meaning=excluded.meaning, usage=excluded.usage, hits=hits+1",
                      (term[:32], str(meaning or "")[:300], str(usage or "")[:200]))

    def slang_set(self, term, meaning, usage=""):
        with self._conn() as c:
            c.execute("INSERT INTO slang_terms(term, meaning, usage, hits, created_at) VALUES(?,?,?,0,datetime('now','localtime'))"
                      " ON CONFLICT(term) DO UPDATE SET meaning=excluded.meaning, usage=excluded.usage",
                      (str(term)[:32], str(meaning or "")[:300], str(usage or "")[:200]))

    def slang_update(self, old, term, meaning, usage=""):
        old = str(old or "").strip()
        term = str(term or "").strip()
        if not term or not meaning:
            return
        if old and old != term:
            with self._conn() as c:
                c.execute("DELETE FROM slang_terms WHERE term=?", (old,))
        self.slang_set(term, meaning, usage)

    def slang_list(self, limit=5000):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM slang_terms ORDER BY hits DESC, term LIMIT ?", (limit,)).fetchall()]

    def slang_delete(self, term):
        with self._conn() as c:
            c.execute("DELETE FROM slang_terms WHERE term=?", (str(term),))

    def slang_delete_many(self, terms):
        n = 0
        with self._conn() as c:
            for t in terms or []:
                cur = c.execute("DELETE FROM slang_terms WHERE term=?", (str(t),))
                n += cur.rowcount
        return n

    def slang_find(self, text):
        t = str(text or "")
        with self._conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM slang_terms").fetchall()]
        return [r for r in rows if r["term"] and r["term"] in t]

    # ---------- 休息唤醒 ----------
    def wake_get(self, gid, day):
        with self._conn() as c:
            r = c.execute("SELECT * FROM wake_log WHERE group_id=? AND day=?", (str(gid), day)).fetchone()
            return dict(r) if r else None

    def wake_save(self, gid, day, count, final_sent=0):
        with self._conn() as c:
            c.execute("INSERT INTO wake_log(day, group_id, count, first_at, last_at, final_sent)"
                      " VALUES(?,?,?,datetime('now','localtime'),datetime('now','localtime'),?)"
                      " ON CONFLICT(day, group_id) DO UPDATE SET count=excluded.count,"
                      " last_at=datetime('now','localtime'), final_sent=excluded.final_sent",
                      (day, str(gid), int(count), int(final_sent)))

    def wake_reply_add(self, gid, text):
        with self._conn() as c:
            c.execute("INSERT INTO wake_replies(group_id, text, created_at) VALUES(?,?,datetime('now','localtime'))",
                      (str(gid), str(text)[:200]))

    def wake_reply_recent(self, gid, limit=20):
        with self._conn() as c:
            rows = c.execute("SELECT text FROM wake_replies WHERE group_id=? AND created_at >= datetime('now','localtime','-24 hours') ORDER BY id DESC LIMIT ?",
                             (str(gid), int(limit))).fetchall()
            return [r["text"] for r in rows]

    def wake_reply_cleanup(self, days=7):
        with self._conn() as c:
            c.execute("DELETE FROM wake_replies WHERE created_at < datetime('now','localtime',?)", (f"-{int(days)} days",))

    def wake_today(self, day):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM wake_log WHERE day=? ORDER BY last_at DESC", (day,)).fetchall()]

    def wake_cleanup(self, days=30):
        with self._conn() as c:
            c.execute("DELETE FROM wake_log WHERE day < date('now','localtime',?)", (f"-{int(days)} days",))

    # ---------- 好友申请 ----------
    def friend_add(self, user_id, comment, flag, action):
        with self._conn() as c:
            c.execute("INSERT INTO friend_requests(user_id, comment, flag, action, created_at)"
                      " VALUES(?,?,?,?,datetime('now','localtime'))",
                      (str(user_id), str(comment or "")[:120], str(flag or ""), action))

    def friend_update(self, flag, action):
        with self._conn() as c:
            c.execute("UPDATE friend_requests SET action=?, acted_at=datetime('now','localtime') WHERE flag=?",
                      (action, str(flag or "")))

    def friend_list(self, limit=50):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM friend_requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    def friend_today(self, action):
        with self._conn() as c:
            r = c.execute("SELECT COUNT(*) AS n FROM friend_requests WHERE action=? AND date(created_at)=date('now','localtime')",
                          (action,)).fetchone()
            return int(r["n"] if r else 0)

    # ---------- 记忆 ----------




    NOISE_WORDS = ("用户提醒", "用户要求", "用户希望", "用户让", "用户告知", "用户叫", "密钥",
                   "部署包", "服务器", "API", "接口", "安装", "配置", "更新版本", "操作步骤", "步骤")












    # ---------- 账号 / 权限 ----------
    def account_by_name(self, username: str):
        with self._conn() as c:
            r = c.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
            return dict(r) if r else None

    def account_by_id(self, aid):
        with self._conn() as c:
            r = c.execute("SELECT * FROM admins WHERE id=?", (int(aid),)).fetchone()
            return dict(r) if r else None

    def accounts_all(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id, username, role, created_by, quota_groups, quota_users, disabled,"
                " last_login_at, last_login_ip, created_at FROM admins ORDER BY id"
            ).fetchall()]

    def create_account(self, username: str, password: str, role: str, created_by=None,
                       quota_groups=None, quota_users=None):
        try:
            with self._conn() as c:
                cur = c.execute(
                    "INSERT INTO admins(username, pass_hash, role, created_by, quota_groups, quota_users,"
                    " created_at) VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
                    (username, hash_password(password), role, created_by, quota_groups, quota_users),
                )
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def set_account_password(self, username: str, password: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE admins SET pass_hash=? WHERE username=?",
                            (hash_password(str(password)), str(username)))
            return cur.rowcount > 0

    def set_account_role_by_name(self, username: str, role: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE admins SET role=? WHERE username=?", (str(role), str(username)))
            return cur.rowcount > 0

    def update_account(self, aid, **fields):
        allowed = ("role", "quota_groups", "quota_users", "disabled", "pass_hash")
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        if not sets:
            return False
        vals.append(int(aid))
        with self._conn() as c:
            c.execute(f"UPDATE admins SET {', '.join(sets)} WHERE id=?", vals)
        return True

    def delete_account(self, aid):
        with self._conn() as c:
            c.execute("DELETE FROM admins WHERE id=?", (int(aid),))

    def touch_login(self, aid, ip: str):
        with self._conn() as c:
            c.execute(
                "UPDATE admins SET last_login_at=datetime('now','localtime'), last_login_ip=? WHERE id=?",
                (str(ip or ""), int(aid)),
            )

    def log_login(self, account_id, username, role, success, ip, ua, reason="", location=""):
        with self._conn() as c:
            c.execute(
                "INSERT INTO login_logs(account_id, username, role, success, ip, ua, reason, location, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                (account_id, username, role, 1 if success else 0, str(ip or ""), str(ua or "")[:200], reason, str(location or "")),
            )
            c.execute("DELETE FROM login_logs WHERE created_at < datetime('now','localtime','-30 days')")

    def login_logs(self, limit=200, account_ids=None):
        with self._conn() as c:
            if account_ids is None:
                rows = c.execute("SELECT * FROM login_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            else:
                ids = [int(i) for i in account_ids] or [-1]
                marks = ",".join("?" * len(ids))
                rows = c.execute(
                    f"SELECT * FROM login_logs WHERE account_id IN ({marks}) ORDER BY id DESC LIMIT ?",
                    (*ids, limit),
                ).fetchall()
            return [dict(r) for r in rows]

    # ---------- 白名单归属 ----------
    def wl_groups_owner(self, gid):
        with self._conn() as c:
            r = c.execute("SELECT created_by FROM wl_groups WHERE group_id=?", (str(gid),)).fetchone()
            return r["created_by"] if r else None

    def wl_users_owner(self, qq):
        with self._conn() as c:
            r = c.execute("SELECT created_by FROM wl_users WHERE qq=?", (str(qq),)).fetchone()
            return r["created_by"] if r else None

    def wl_count(self, kind: str, created_by):
        table = "wl_groups" if kind == "group" else "wl_users"
        with self._conn() as c:
            return c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE created_by=?", (int(created_by),)).fetchone()["n"]

    def update_wl(self, kind: str, old: str, new: str):
        table = "wl_groups" if kind == "group" else "wl_users"
        col = "group_id" if kind == "group" else "qq"
        with self._conn() as c:
            c.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (str(new), str(old)))

    def groups(self, created_by=None, all_rows=False):
        with self._conn() as c:
            if all_rows or created_by is None:
                rows = c.execute("SELECT group_id FROM wl_groups ORDER BY group_id").fetchall()
            else:
                rows = c.execute("SELECT group_id FROM wl_groups WHERE created_by=?", (int(created_by),)).fetchall()
            return [r["group_id"] for r in rows]

    def users(self, created_by=None, all_rows=False):
        with self._conn() as c:
            if all_rows or created_by is None:
                rows = c.execute("SELECT qq FROM wl_users ORDER BY qq").fetchall()
            else:
                rows = c.execute("SELECT qq FROM wl_users WHERE created_by=?", (int(created_by),)).fetchall()
            return [r["qq"] for r in rows]

    def keywords(self) -> list[str]:
        with self._conn() as c:
            return [r["word"] for r in c.execute("SELECT word FROM keywords ORDER BY rowid")]

    def add_keyword(self, word: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO keywords(word) VALUES(?)", (word,))

    def remove_keyword(self, word: str):
        with self._conn() as c:
            c.execute("DELETE FROM keywords WHERE word=?", (word,))

    def prefix_map(self) -> dict[str, str]:
        with self._conn() as c:
            return {r["qq"]: r["prefix"] for r in c.execute("SELECT qq, prefix FROM prefix_map ORDER BY rowid")}

    def set_prefix(self, qq: str, prefix: str):
        with self._conn() as c:
            c.execute("INSERT INTO prefix_map(qq, prefix) VALUES(?,?) ON CONFLICT(qq) DO UPDATE SET prefix=excluded.prefix", (qq, prefix))

    def remove_prefix(self, qq: str):
        with self._conn() as c:
            c.execute("DELETE FROM prefix_map WHERE qq=?", (qq,))

    def get_prefix(self, qq: str) -> str | None:
        with self._conn() as c:
            r = c.execute("SELECT prefix FROM prefix_map WHERE qq=?", (qq,)).fetchone()
            return r["prefix"] if r else None

    def auto_users(self) -> list[str]:
        with self._conn() as c:
            return [r["qq"] for r in c.execute("SELECT qq FROM auto_users ORDER BY rowid")]

    def add_auto_user(self, qq: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO auto_users(qq) VALUES(?)", (qq,))

    def remove_auto_user(self, qq: str):
        with self._conn() as c:
            c.execute("DELETE FROM auto_users WHERE qq=?", (qq,))

    # ---------- token 用量 ----------
    def token_add(self, kind: str, prompt: int, completion: int,
                  model: str = "", uid: str = "", gid: str = "") -> None:
        now = datetime.now()
        p = int(prompt or 0)
        q = int(completion or 0)
        with self._conn() as c:
            c.execute(
                "INSERT INTO token_usage(ts,day,kind,prompt,completion,total,model,uid,gid)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d"), str(kind or ""),
                 p, q, p + q, str(model or ""), str(uid or ""), str(gid or "")))

    def token_stats(self, start_day: str = "", end_day: str = "", recent: int = 30) -> dict:
        where, args = [], []
        if start_day:
            where.append("day >= ?")
            args.append(start_day)
        if end_day:
            where.append("day <= ?")
            args.append(end_day)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as c:
            s = c.execute(
                "SELECT COUNT(*) AS calls, COALESCE(SUM(prompt),0) AS prompt,"
                " COALESCE(SUM(completion),0) AS completion, COALESCE(SUM(total),0) AS total"
                " FROM token_usage" + w, args).fetchone()
            days = [dict(r) for r in c.execute(
                "SELECT day, COUNT(*) AS calls, SUM(prompt) AS prompt, SUM(completion) AS completion,"
                " SUM(total) AS total FROM token_usage" + w + " GROUP BY day ORDER BY day DESC", args)]
            kinds = [dict(r) for r in c.execute(
                "SELECT kind, COUNT(*) AS calls, SUM(total) AS total FROM token_usage" + w +
                " GROUP BY kind ORDER BY total DESC", args)]
            rec = [dict(r) for r in c.execute(
                "SELECT ts, kind, prompt, completion, total, model FROM token_usage" + w +
                " ORDER BY id DESC LIMIT ?", args + [int(recent)])]
        return {"summary": dict(s), "days": days, "kinds": kinds, "recent": rec}

    def get_setting(self, key: str, default: str = "") -> str:
        now = time.time()
        if now - self._cache_ts > 5:
            with self._conn() as c:
                self._cache = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
            self._cache_ts = now
        return self._cache.get(key, default)

    def set_setting(self, key: str, value: str):
        with self._conn() as c:
            c.execute("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        now = time.time()
        loaded = bool(self._cache_ts) and (now - self._cache_ts <= 5)
        self._cache[key] = value
        if loaded:
            self._cache_ts = now
        else:
            # 缓存未加载或已过期：标记为过期，下次读取时重新加载整张表
            self._cache_ts = 0.0

    def bored_lines(self) -> list[str]:
        with self._conn() as c:
            return [r["line"] for r in c.execute("SELECT line FROM bored_lines ORDER BY rowid")]

    def always_groups(self) -> list[str]:
        with self._conn() as c:
            return [r["group_id"] for r in c.execute("SELECT group_id FROM always_groups ORDER BY group_id")]

    def get_rate(self, group_id: str):
        with self._conn() as c:
            r = c.execute("SELECT max_per_minute, min_interval_seconds FROM group_rate WHERE group_id=?", (group_id,)).fetchone()
            return (r["max_per_minute"], r["min_interval_seconds"]) if r else None

    def set_rate(self, group_id: str, cap: int, interval: int):
        with self._conn() as c:
            c.execute(
                "INSERT INTO group_rate(group_id, max_per_minute, min_interval_seconds) VALUES(?,?,?) "
                "ON CONFLICT(group_id) DO UPDATE SET max_per_minute=excluded.max_per_minute, min_interval_seconds=excluded.min_interval_seconds",
                (group_id, cap, interval),
            )

    def del_rate(self, group_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM group_rate WHERE group_id=?", (group_id,))

    def providers(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT name, base_url, api_key, model FROM providers ORDER BY name")]

    def get_provider(self, name: str):
        with self._conn() as c:
            r = c.execute("SELECT name, base_url, api_key, model FROM providers WHERE name=?", (name,)).fetchone()
            return dict(r) if r else None

    def save_provider(self, name: str, base_url: str, api_key: str, model: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO providers(name, base_url, api_key, model, updated_at) VALUES(?,?,?,?,datetime('now','localtime')) "
                "ON CONFLICT(name) DO UPDATE SET base_url=excluded.base_url, api_key=excluded.api_key, model=excluded.model, updated_at=excluded.updated_at",
                (name, base_url.rstrip("/"), api_key, model),
            )

    def delete_provider(self, name: str):
        with self._conn() as c:
            c.execute("DELETE FROM providers WHERE name=?", (name,))

    def rest_groups(self) -> list[str]:
        with self._conn() as c:
            return [r["group_id"] for r in c.execute("SELECT group_id FROM rest_groups ORDER BY rowid").fetchall()]

    def rest_users(self) -> list[str]:
        with self._conn() as c:
            return [r["qq"] for r in c.execute("SELECT qq FROM rest_users ORDER BY rowid").fetchall()]

    def add_rest_group(self, gid: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO rest_groups(group_id) VALUES(?)", (str(gid),))

    def remove_rest_group(self, gid: str):
        with self._conn() as c:
            c.execute("DELETE FROM rest_groups WHERE group_id=?", (str(gid),))

    def add_rest_user(self, qq: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO rest_users(qq) VALUES(?)", (str(qq),))

    def remove_rest_user(self, qq: str):
        with self._conn() as c:
            c.execute("DELETE FROM rest_users WHERE qq=?", (str(qq),))

    def rest_notify_groups(self) -> list[str]:
        with self._conn() as c:
            return [r["group_id"] for r in c.execute("SELECT group_id FROM rest_notify_groups ORDER BY rowid").fetchall()]

    def add_rest_notify_group(self, gid: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO rest_notify_groups(group_id) VALUES(?)", (str(gid),))

    def remove_rest_notify_group(self, gid: str):
        with self._conn() as c:
            c.execute("DELETE FROM rest_notify_groups WHERE group_id=?", (str(gid),))

    def blacklist(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT qq, nick, added_at FROM blacklist ORDER BY rowid").fetchall()]

    def add_black(self, qq: str, nick: str = ""):
        with self._conn() as c:
            c.execute(
                "INSERT INTO blacklist(qq, nick, added_at) VALUES(?,?,?) "
                "ON CONFLICT(qq) DO UPDATE SET nick=excluded.nick, added_at=excluded.added_at",
                (str(qq), str(nick or ""), time.time()),
            )

    def remove_black(self, qq: str):
        with self._conn() as c:
            c.execute("DELETE FROM blacklist WHERE qq=?", (str(qq),))

    def set_black_nick(self, qq: str, nick: str):
        with self._conn() as c:
            c.execute("UPDATE blacklist SET nick=? WHERE qq=?", (str(nick or ""), str(qq)))

    def group_blacklist(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT qq, nick, added_at FROM group_blacklist ORDER BY added_at DESC").fetchall()]

    def add_group_black(self, qq: str, nick: str = ""):
        with self._conn() as c:
            c.execute("INSERT INTO group_blacklist(qq, nick, added_at) VALUES(?,?,?) "
                      "ON CONFLICT(qq) DO UPDATE SET nick=excluded.nick",
                      (str(qq), str(nick or ""), time.time()))

    def remove_group_black(self, qq: str):
        with self._conn() as c:
            c.execute("DELETE FROM group_blacklist WHERE qq=?", (str(qq),))

    def group_panels(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT group_id, username, token, enabled, created_at FROM group_panel ORDER BY created_at").fetchall()]

    def group_panel_get(self, gid: str):
        with self._conn() as c:
            return c.execute("SELECT * FROM group_panel WHERE group_id=?", (str(gid),)).fetchone()

    def group_panel_add(self, gid: str, username: str, pass_hash: str, token: str, pass_plain: str = ""):
        with self._conn() as c:
            c.execute("INSERT INTO group_panel(group_id, username, pass_hash, token, enabled, created_at, pass_plain) VALUES(?,?,?,?,1,?,?) "
                      "ON CONFLICT(group_id) DO UPDATE SET username=excluded.username, pass_hash=excluded.pass_hash, token=excluded.token, pass_plain=excluded.pass_plain",
                      (str(gid), username, pass_hash, token, time.time(), pass_plain))

    def group_panel_update(self, gid: str, **kw):
        if not kw: return
        cols = ", ".join(f"{k}=?" for k in kw)
        with self._conn() as c:
            c.execute(f"UPDATE group_panel SET {cols} WHERE group_id=?", (*kw.values(), str(gid)))

    def group_panel_del(self, gid: str):
        with self._conn() as c:
            c.execute("DELETE FROM group_panel WHERE group_id=?", (str(gid),))
            c.execute("DELETE FROM group_cfg WHERE group_id=?", (str(gid),))

    def group_cfg_get(self, gid: str, key: str, default: str = "") -> str:
        with self._conn() as c:
            r = c.execute("SELECT value FROM group_cfg WHERE group_id=? AND key=?", (str(gid), key)).fetchone()
            return r["value"] if r else default

    def group_cfg_set(self, gid: str, key: str, value: str):
        with self._conn() as c:
            c.execute("INSERT INTO group_cfg(group_id,key,value) VALUES(?,?,?) ON CONFLICT(group_id,key) DO UPDATE SET value=excluded.value",
                      (str(gid), key, str(value)))

    def is_group_black(self, qq: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM group_blacklist WHERE qq=?", (str(qq),)).fetchone() is not None









    def is_black(self, qq: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM blacklist WHERE qq=?", (str(qq),)).fetchone() is not None





    def end_phrases(self) -> list[str]:
        with self._conn() as c:
            return [r["phrase"] for r in c.execute("SELECT phrase FROM end_phrases ORDER BY rowid")]

    def add_end_phrase(self, phrase: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO end_phrases(phrase) VALUES(?)", (phrase,))

    def remove_end_phrase(self, phrase: str):
        with self._conn() as c:
            c.execute("DELETE FROM end_phrases WHERE phrase=?", (phrase,))






    def set_always_group(self, group_id: str, enabled: bool):
        with self._conn() as c:
            if enabled:
                c.execute("INSERT OR IGNORE INTO always_groups(group_id) VALUES(?)", (group_id,))
            else:
                c.execute("DELETE FROM always_groups WHERE group_id=?", (group_id,))

    def add_bored_line(self, line: str):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO bored_lines(line) VALUES(?)", (line,))

    def remove_bored_line(self, line: str):
        with self._conn() as c:
            c.execute("DELETE FROM bored_lines WHERE line=?", (line,))

    def add_wl(self, kind: str, value: str, created_by=None):
        table = "wl_groups" if kind == "group" else "wl_users"
        col = "group_id" if kind == "group" else "qq"
        with self._conn() as c:
            c.execute(f"INSERT OR IGNORE INTO {table}({col}, created_by, created_at) VALUES(?,?,datetime('now','localtime'))", (value, created_by))

    def remove_wl(self, kind: str, value: str):
        table = "wl_groups" if kind == "group" else "wl_users"
        col = "group_id" if kind == "group" else "qq"
        with self._conn() as c:
            c.execute(f"DELETE FROM {table} WHERE {col}=?", (value,))


class ProactiveMessenger:
    """主动消息/提醒：独立于 Bridge，负责定时、解析、主动发送。"""

    def __init__(self, bridge):
        self.b = bridge
        self.store = bridge.store

    @staticmethod
    def extract_task(t: str) -> str:
        """从「提醒我 10点 吃药」这类句子里去掉触发词，取出要做的事。"""
        task = str(t or "")
        for w in ("提醒我", "提醒", "叫我", "喊我", "记得", "帮我", "别忘了", "一下", "到时候"):
            task = task.replace(w, " ")
        return task.strip(" ，,。.！!？?、~～")

    def parse(self, text):
        import re as _re
        t = str(text or "").strip()
        m = _re.search(r"(今天|明天|后天)?\s*(凌晨|早上|上午|中午|下午|晚上)?\s*(\d{1,2})\s*[点:：]\s*(半|\d{1,2})?", t)
        if not m:
            # 没说时间也要把「要做的事」带出来，交给上层决定是提示补时间
            return None, self.extract_task(t)
        day_w, period, hh, mm = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        minute = 30 if mm == "半" else int(mm or 0)
        if minute > 59 or hh > 23:
            return None, None
        hour = hh
        if period in ("下午", "晚上") and hour < 12:
            hour += 12
        elif period == "中午" and hour < 11:
            hour += 12
        elif period == "凌晨" and hour == 12:
            hour = 0
        now = datetime.now()
        offset = {"今天": 0, "明天": 1, "后天": 2}.get(day_w)
        if not period and hour < 12 and now.hour >= 12 and offset is None:
            hour += 12
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if offset is not None:
            due = due + timedelta(days=offset)
        elif due <= now:
            due = due + timedelta(days=1)
        task = self.extract_task(t.replace(m.group(0), " "))
        return due, task

    async def handle(self, ws, ev, mtype, uid, text):
        t = str(text or "").strip()
        q = ("提醒我什么", "提醒我啥", "有什么提醒", "我的提醒", "提醒我哪些", "今天提醒什么", "今天提醒我什么")
        if any(w in t for w in q):
            rows = self.store.reminder_pending(uid)
            if not rows:
                await self.b.send(ws, mtype, ev, "你目前没有待提醒的事。", record_convo=False)
            else:
                lines = []
                for r in rows:
                    when = r.get("due_text") or "未定时间"
                    lines.append(f"· {when}  {r.get('text')}")
                await self.b.send(ws, mtype, ev, "你有这些提醒：\n" + "\n".join(lines), record_convo=False)
            return True
        if not any(w in t for w in ("提醒我", "叫我", "喊我", "记得提醒", "到时候提醒", "别忘了提醒")):
            return False
        due, task = self.parse(t)
        task = str(task).strip() if task else ""
        gid = str(ev.get("group_id") or "") if mtype == "group" else ""
        if not task:
            # 只说了「提醒我」没说内容：不要往库里塞 None
            await self.b.send(ws, mtype, ev, "提醒什么？说「提醒我 10点 吃药」这样就行。", record_convo=False)
            return True
        if due:
            self.store.reminder_add(uid, gid, task, int(due.timestamp()), due.strftime("%m-%d %H:%M"))
            await self.b.send(ws, mtype, ev, f"好，{due.strftime('%H:%M')} 我提醒你：{task}", record_convo=False)
        else:
            self.store.reminder_add(uid, gid, task, 0, "")
            await self.b.send(ws, mtype, ev, f"记下了：{task}\n要几点提醒你？下次说「提醒我几点做什么」就行。", record_convo=False)
        return True

    async def compose(self, text):
        if self.store.get_setting("reminder_ai_phrase", "1") != "1":
            return f"⏰ 提醒：{text}"
        try:
            out = await self.b.llm_complete(
                "你是QQ里的「大肥鱼」，现在要主动给老大发一条提醒。用一句自然口语，不超过30字，"
                "不要客服腔、不要解释，只输出这句话。",
                f"提醒内容：{text}", max_tokens=80, temperature=0.8)
            out = re.sub(r"\s+", " ", str(out or "")).strip().strip('"“”')
            out = out[:30].rstrip("，,。.、 ")
            return out or f"⏰ 提醒：{text}"
        except Exception:
            return f"⏰ 提醒：{text}"

    async def send(self, qq, text, group_id=""):
        if not self.b.ws:
            return False
        ev = {"group_id": group_id, "user_id": qq}
        if group_id:
            await self.b.send(self.b.ws, "group", ev, text, record_convo=False, at_qq=qq)
        else:
            await self.b.send(self.b.ws, "private", ev, text, record_convo=False)
        return True

    async def loop(self):
        await asyncio.sleep(15)
        while not self.b._stop:
            try:
                if self.b.ws:
                    now_ts = int(time.time())
                    due = self.store.reminder_due(now_ts)
                    # 掉线久了会堆积：超过 24 小时的直接作废，其余每轮最多补发 3 条，避免一次性刷屏
                    for r in due:
                        if now_ts - int(r.get("due_at") or 0) > 86400:
                            self.store.reminder_done(r["id"])
                    fresh = [r for r in due if now_ts - int(r.get("due_at") or 0) <= 86400][:3]
                    for r in fresh:
                        msg = await self.compose(r.get("text") or "")
                        await self.send(r.get("qq"), msg, r.get("group_id") or "")
                        self.store.reminder_done(r["id"])
            except Exception as e:
                log.warning("提醒循环失败: %s", e)
            await asyncio.sleep(30)


# ---- 模块化功能（mixin） ----
class Bridge(AppApiMixin, BiliAccountMixin, BiliMixin, EconomyMixin, EmotionMixin, GroupMixin, PanelMixin, PersonaMixin, MemoryMixin, StickerMixin, ImageMixin, VoiceMixin, RecallMixin, GameMixin, AdminMixin, WebMixin, OneBotMixin, StyleMixin, MusicMixin, ConfigMixin, AccountsMixin, HostingMixin, ChatMixin, RuntimeMixin, WorldMixin):

    def app_version(self) -> str:
        return APP_VERSION

    def login_html(self) -> str:
        return LOGIN_HTML

    def log_ring(self):
        return LOG_RING

    def sticker_dir(self):
        return STICKER_DIR

    def admin_html(self) -> str:
        return ADMIN_HTML

    def admin_css(self) -> str:
        d = self._web_dir()
        if d:
            try:
                f = d / "css" / "app.css"
                if f.is_file():
                    return f.read_text(encoding="utf-8")
            except Exception:
                pass
        import re as _re2
        m = _re2.search(r"<style>(.*?)</style>", ADMIN_HTML, _re2.S)
        return m.group(1) if m else ""



















































    # ---------- NapCat 管理 API ----------





    # ---------- 白名单 ----------

    # ---------- OneBot ----------


























    # ---------- 群管理员功能 ----------


    # ---------- B 站 ----------
    BILI_HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                 "Referer": "https://www.bilibili.com/"}
















































    # ---------- 末世文字冒险（私聊版） ----------
    GAME_START_WORDS = ("开始末世", "开始游戏", "末世生存", "赤月2039", "赤月 2039")
    GAME_EXIT_WORDS = ("退出游戏", "结束游戏", "退出末世")
    """每次对话后返回给玩家的存档提示"""

    # ---------- 剧本来源（远程拉取，内存缓存，不落盘） ----------




    # ---------- 剧本杀（私聊版） ----------
    GAME_EXIT_WORDS = ("退出游戏", "结束游戏", "退出剧本")
    GAME_START_WORDS = ("开始游戏", "开始剧本", "继续游戏", "继续", "开始")

    GAME_SECTION_RE = re.compile(r"(?=【(?:叙事|可见信息|选择|状态面板|章末快照|复盘)】)")







    GAME_GROUP_CMDS = ("状态", "我的状态", "面板", "看看状态", "存档", "我的存档", "进度",
                       "重开本局", "重新开始", "重开")








    # ---------- 情绪与人格（隐藏系统） ----------








    # ---------- 恐慌状态机（隐藏） ----------




    # ---------- 无聊值 ----------



    # ---------- 余额恐慌 ----------













































    # ---------- 管理后台 Web ----------




















    TOKEN_RANGES = {
        "today": ("今天", 0, 0),
        "yesterday": ("昨天", 1, 1),
        "3d": ("前三天", 2, 0),
        "7d": ("前七天", 6, 0),
        "30d": ("前一个月", 29, 0),
        "all": ("全部", None, None),
    }


    # ---------- 测试模式 / 一键接口自检 ----------
    # 自检清单：只包含"调用不会改数据/不花钱/不打扰人"的接口。
    # 字段：g 分组、p 路径、m 方法（默认 GET）、d 请求体、allow 允许返回 code!=0
    SELFCHECK_ITEMS = [
        {"g": "状态", "p": "/api/status"},
        {"g": "状态", "p": "/api/logs"},
        {"g": "状态", "p": "/api/me"},
        {"g": "状态", "p": "/api/bot-profile"},
        {"g": "状态", "p": "/api/update"},
        {"g": "账号", "p": "/api/accounts"},
        {"g": "账号", "p": "/api/admins"},
        {"g": "账号", "p": "/api/login-logs"},
        {"g": "配置", "p": "/api/super"},
        {"g": "配置", "p": "/api/persona"},
        {"g": "配置", "p": "/api/personas"},
        {"g": "配置", "p": "/api/economy/config"},
        {"g": "模型", "p": "/api/providers"},
        {"g": "模型", "p": "/api/apikey"},
        {"g": "模型", "p": "/api/providers/balances", "allow": True},
        {"g": "聊天", "p": "/api/keywords"},
        {"g": "聊天", "p": "/api/prefix"},
        {"g": "聊天", "p": "/api/auto"},
        {"g": "聊天", "p": "/api/group-reply"},
        {"g": "聊天", "p": "/api/group-rate"},
        {"g": "聊天", "p": "/api/conversations"},
        {"g": "聊天", "p": "/api/bored"},
        {"g": "聊天", "p": "/api/bored/lines"},
        {"g": "聊天", "p": "/api/end-phrase"},
        {"g": "聊天", "p": "/api/rest"},
        {"g": "聊天", "p": "/api/recall/config"},
        {"g": "聊天", "p": "/api/wake"},
        {"g": "聊天", "p": "/api/friend"},
        {"g": "聊天", "p": "/api/blacklist"},
        {"g": "白名单", "p": "/api/whitelist"},
        {"g": "群管理", "p": "/api/gm/groups"},
        {"g": "群管理", "p": "/api/gm/config"},
        {"g": "群管理", "p": "/api/gm/blacklist"},
        {"g": "记忆", "p": "/api/memory"},
        {"g": "记忆", "p": "/api/memory/noise_preview"},
        {"g": "记忆", "p": "/api/memory/ai_review/status", "allow": True},
        {"g": "剧本", "p": "/api/game/overview"},
        {"g": "剧本", "p": "/api/game/runs"},
        {"g": "剧本", "p": "/api/game/messages"},
        {"g": "剧本", "p": "/api/game/contexts"},
        {"g": "租户", "p": "/api/hosting/list"},
        {"g": "租户", "p": "/api/hosting/nodes"},
        {"g": "媒体", "p": "/api/stickers"},
        {"g": "媒体", "p": "/api/stickers/install_status"},
        {"g": "媒体", "p": "/api/image"},
        {"g": "媒体", "p": "/api/voice"},
        {"g": "媒体", "p": "/api/music"},
        {"g": "媒体", "p": "/api/bili/config"},
        {"g": "内容", "p": "/api/slang"},
        {"g": "统计", "p": "/api/tokens"},
        {"g": "认证", "p": "/api/login", "m": "POST",
         "d": {"username": "__selfcheck__", "password": "__wrong__"}, "allow": True},
        {"g": "更新", "p": "/api/update/check", "m": "POST"},
    ]









































































































    # ---------- 剧本杀后台 API ----------
    # ---------- 托管租户 ----------
    HOSTING_ROOT = Path(os.environ.get("FISHPOND_HOST_ROOT", "/opt/fishpond"))





























    # 分发接口（给用户部署拉取，凭 token）



































    GP_KEYS = ("gm_welcome", "gm_auto_approve", "gm_verify", "gm_verify_mode", "gm_timeout_min",
               "gm_questions", "gm_patrol_enabled", "gm_patrol_rate", "gm_patrol_mute_min",
               "gm_silent", "gm_kick_enabled", "gm_mute_enabled", "gm_blacklist_kick",
               "gm_kick_keywords", "gm_blacklist_keywords", "gm_recall_keywords",
               "gm_recall_enabled", "gm_kwlimit_rules", "gm_punish_qqs",
               "gm_ai_patrol", "gm_ai_context", "gm_ai_action", "gm_patrol_warn", "gm_blacklist", "gm_kick_qqs")






    PAGE_TMPL = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>群面板</title><style>__CSS__
    body{display:block!important;background:#0b0d11;padding:16px}
    #gm{max-width:920px;margin:0 auto}
    #gmtabs,#gm_panel{display:none!important}
    #gm_groups,#gm_groups+*{display:none!important}
    </style></head><body>
    <div class="card" id="glogin" style="max-width:420px;margin:0 auto"><h2>群面板登录</h2>
    <label style="display:block;color:#8b93a5;font-size:12px">账号<input id="u" style="width:100%;box-sizing:border-box;margin-top:4px"></label>
    <label style="display:block;color:#8b93a5;font-size:12px">密码<input id="p" type="password" style="width:100%;box-sizing:border-box;margin-top:4px"></label>
    <button onclick="doLogin()">登录</button><span class="msg" id="lmsg"></span></div>
    <div id="gmwrap" style="display:none">__BLOCK__</div>
    <script>
    const BASE='__BASE__';
    const BOOLBTNS=[['gm_auto_btn','gm_auto_approve','自动通过'],['gm_verify_btn','gm_verify','进群验证'],['gm_kick_btn','gm_kick_enabled','踢人指令'],['gm_blk_btn','gm_blacklist_kick','黑名单踢出'],['gm_mute_btn','gm_mute_enabled','禁言指令'],['gm_silent_btn','gm_silent','禁止闲聊'],['gm_patrol_btn','gm_patrol_enabled','刷屏巡查'],['gm_ai_btn','gm_ai_patrol','AI 违规判断'],['gm_recall_btn','gm_recall_enabled','违规词撤回']];
    const FLDS=['gm_welcome','gm_timeout_min','gm_verify_mode','gm_punish_qqs','gm_kick_qqs','gm_patrol_rate','gm_patrol_mute_min','gm_ai_context','gm_ai_action','gm_patrol_warn','gm_kick_keywords','gm_blacklist_keywords','gm_recall_keywords'];
    let GM={},QL=[],KL=[];
    function v(id){const e=document.getElementById(id);return e?e.value:'';}
    function esc(x){return String(x||'').replace(/"/g,'&quot;');}
    function paint(){BOOLBTNS.forEach(b=>{const el=document.getElementById(b[0]);if(!el)return;const on=GM[b[1]]==='1';el.textContent=b[2]+'：'+(on?'已开启':'已关闭');el.style.background=on?'#16a34a':'#374151';el.style.color='#fff';el.style.border='0';});}
    function gmToggle(k){GM[k]=GM[k]==='1'?'0':'1';paint();}
    function qRender(){document.getElementById('q_body').innerHTML=QL.map((it,i)=>'<tr><td>'+(i+1)+'</td><td><input data-q="'+i+'" value="'+esc(it.q)+'" style="width:100%"></td><td><input data-a="'+i+'" value="'+esc(it.a)+'" style="width:100%"></td><td><button onclick="qDel('+i+')">删除</button></td></tr>').join('');}
    function klRender(){document.getElementById('kl_body').innerHTML=KL.map((it,i)=>'<tr><td>'+(i+1)+'</td><td><input data-k="'+i+'" value="'+esc(it.k)+'" style="width:100%"></td><td><input data-w="'+i+'" type="number" value="'+esc(it.w)+'" style="width:100%"></td><td><input data-n="'+i+'" type="number" value="'+esc(it.n)+'" style="width:100%"></td><td><button onclick="klDel('+i+')">删除</button></td></tr>').join('');}
    function qCollect(){document.querySelectorAll('[data-q]').forEach(e=>QL[+e.dataset.q].q=e.value);document.querySelectorAll('[data-a]').forEach(e=>QL[+e.dataset.a].a=e.value);}
    function klCollect(){document.querySelectorAll('[data-k]').forEach(e=>KL[+e.dataset.k].k=e.value);document.querySelectorAll('[data-w]').forEach(e=>KL[+e.dataset.w].w=e.value);document.querySelectorAll('[data-n]').forEach(e=>KL[+e.dataset.n].n=e.value);}
    function qAdd(){qCollect();QL.push({q:'',a:''});qRender();}
    function qDel(i){qCollect();QL.splice(i,1);qRender();}
    function klAdd(){klCollect();KL.push({k:'',w:'60',n:'1'});klRender();}
    function klDel(i){klCollect();KL.splice(i,1);klRender();}
    async function loadBL(){const r=await fetch(BASE+'/api/blacklist').then(x=>x.json());const tb=document.getElementById('bl_body');tb.innerHTML=(r.items||[]).map(it=>'<tr><td>'+it.qq+'</td><td>'+esc(it.nick)+'</td><td><button onclick="blRemove(&#39;'+it.qq+'&#39;)">移除</button></td></tr>').join('');}
    async function blAdd(){const qq=document.getElementById('bl_qq').value.trim();if(!/^[0-9]{5,12}$/.test(qq)){document.getElementById('blmsg').textContent='QQ号无效';return;}await fetch(BASE+'/api/blacklist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'add',qq:qq,nick:document.getElementById('bl_nick').value})});document.getElementById('bl_qq').value='';document.getElementById('bl_nick').value='';loadBL();}
    async function blRemove(qq){await fetch(BASE+'/api/blacklist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'remove',qq:qq})});loadBL();}
    async function doLogin(){const r=await fetch(BASE+'/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:v('u'),password:v('p')})}).then(x=>x.json());if(r.code!==0){document.getElementById('lmsg').textContent=r.message||'登录失败';return;}load();}
    async function load(){const r=await fetch(BASE+'/api/config').then(x=>x.json());if(r.code!==0){document.getElementById('lmsg').textContent=r.message||'请登录';return;}
    document.getElementById('glogin').style.display='none';document.getElementById('gmwrap').style.display='block';
    FLDS.forEach(k=>{const e=document.getElementById(k);if(e)e.value=r[k]||'';});
    BOOLBTNS.forEach(b=>{GM[b[1]]=String(r[b[1]]||'0')==='1';});
    QL=String(r.gm_questions||'').split(String.fromCharCode(10)).filter(x=>x.trim()).map(x=>{const p2=x.split('|');return{q:p2[0]||'',a:p2[1]||''};});
    KL=String(r.gm_kwlimit_rules||'').split(String.fromCharCode(10)).filter(x=>x.trim()).map(x=>{const p3=x.split('|');return{k:p3[0]||'',w:p3[1]||'60',n:p3[2]||'1'};});
    paint();qRender();klRender();loadBL();}
    async function saveGM(){qCollect();klCollect();const body={};FLDS.forEach(k=>{body[k]=v(k);});BOOLBTNS.forEach(b=>{body[b[1]]=GM[b[1]]==='1'?'1':'0';});body.gm_questions=QL.filter(x=>x.q&&x.a).map(x=>x.q+'|'+x.a).join(String.fromCharCode(10));body.gm_kwlimit_rules=KL.filter(x=>x.k).map(x=>x.k+'|'+x.w+'|'+x.n).join(String.fromCharCode(10));
    const r=await fetch(BASE+'/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(x=>x.json());
    document.getElementById('gmmsg').textContent=r.code===0?'已保存':(r.message||'保存失败');document.getElementById('gmmsg').style.color=r.code===0?'#4ade80':'#f87171';}
    async function saveQuestions(){qCollect();const r=await fetch(BASE+'/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gm_questions:QL.filter(x=>x.q&&x.a).map(x=>x.q+'|'+x.a).join(String.fromCharCode(10))})}).then(x=>x.json());
    document.getElementById('qmsg').textContent=r.code===0?'已保存':(r.message||'失败');document.getElementById('qmsg').style.color=r.code===0?'#4ade80':'#f87171';}
    </script></body></html>"""






















LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 - FishPond</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0f1115;color:#e6e6e6;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
.box{background:#181b22;border-radius:14px;padding:28px 24px;width:300px}
h1{font-size:17px;margin:0 0 18px;text-align:center}
input{width:100%;box-sizing:border-box;background:#0b0d11;border:1px solid #2a2f3a;color:#e6e6e6;border-radius:8px;padding:10px 12px;margin-bottom:12px;font-size:14px}
button{width:100%;background:#2563eb;color:#fff;border:none;border-radius:8px;padding:11px;font-size:15px;cursor:pointer}
.msg{color:#f87171;font-size:13px;min-height:18px;margin-bottom:8px}
</style></head>
<body><div id="pbar"></div>
<div id="forcebar" style="display:none;position:fixed;top:0;left:0;right:0;z-index:9998;background:#7f1d1d;color:#fff;padding:8px 12px;font-size:13px;text-align:center">
  <span id="forcebartext">当前版本过低，必须更新</span>
  <button onclick="applyUpdate()" style="margin-left:10px;background:#dc2626;padding:4px 10px">立即更新</button>
</div>
<button id="forcefloat" onclick="applyUpdate()" style="display:none;position:fixed;right:16px;bottom:20px;z-index:9998;background:#dc2626;box-shadow:0 6px 20px rgba(0,0,0,.4);padding:10px 14px">强制更新</button><div class="box"><h1>FishPond</h1>
<div class="msg" id="msg"></div>
<input id="u" placeholder="用户名" autocomplete="username">
<input id="p" type="password" placeholder="密码" autocomplete="current-password">
<button onclick="login()">登录</button>
<div style="text-align:center;color:#4b5563;font-size:11px;margin-top:14px;line-height:1.8">
  免费源码 · 请勿购买<br>作者 QQ：2844642318｜群：243625638
</div>
</div>
<script>
const B = '__BASE__';
async function login(){
  const r = await fetch(B + '/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username: document.getElementById('u').value, password: document.getElementById('p').value})}).then(r=>r.json()).catch(e=>({code:-1,message:'网络错误'}));
  if(r.code===0){ location.reload(); } else { document.getElementById('msg').textContent = r.message || '登录失败'; }
}
document.addEventListener('keydown', e=>{ if(e.key==='Enter') login(); });
</script></body></html>"""



def _load_admin_html() -> str:
    """优先读取 web/index.html，便于前端独立维护；找不到再用内嵌副本。"""
    import pathlib as _pl
    bases = []
    try:
        bases.append(BASE)
    except Exception:
        pass
    bases.append(_pl.Path(__file__).resolve().parent)
    for b in bases:
        for cand in (b / "web" / "index.html", b.parent / "web" / "index.html"):
            try:
                if cand.is_file():
                    t = cand.read_text(encoding="utf-8")
                    if len(t) > 10000:
                        return t
            except Exception:
                continue
    return ""


ADMIN_HTML = _load_admin_html()
if not ADMIN_HTML:
    ADMIN_HTML = ("<!doctype html><meta charset=\"utf-8\"><title>FishPond</title>"
                  "<h3 style=\"font-family:sans-serif;padding:24px\">后台前端缺失：请确认 web/index.html 已随包部署</h3>")


def main():
    cfg = load_config()
    bridge = Bridge(cfg)
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        pass


# 运行模块需要 Store 类（延迟注入，避免循环导入）
try:
    from fishpond.features.runtime import service as _runtime_service
    _runtime_service.Store = Store
    _runtime_service.ProactiveMessenger = ProactiveMessenger
except Exception:
    pass


if __name__ == "__main__":
    main()


# 暴露版本给 App / 接口
Bridge.APP_VERSION = APP_VERSION
