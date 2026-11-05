"""世界引擎 P0：世界时钟、日程、状态、事件日志、对话注入。"""
import asyncio
import aiohttp
import datetime as _dt
import json
import re
import hashlib
import logging
import time

import aiohttp.web as aiohttp_web

log = logging.getLogger("qqbridge")

WEEK = "一二三四五六日"


def _today_index() -> int:
    return (_dt.date.today() - _dt.date(2026, 1, 1)).days


def ensure_world_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS world_state (
        id INTEGER PRIMARY KEY CHECK (id=1),
        day_index INTEGER NOT NULL,
        minutes INTEGER NOT NULL,
        weather TEXT DEFAULT '晴',
        place TEXT DEFAULT '家',
        activity TEXT DEFAULT '休息',
        energy INTEGER DEFAULT 80,
        mood TEXT DEFAULT '平静',
        updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_index INTEGER NOT NULL,
        minutes INTEGER NOT NULL,
        kind TEXT DEFAULT 'life',
        text TEXT NOT NULL,
        created_at REAL
    );
    CREATE INDEX IF NOT EXISTS idx_we_day ON world_events(day_index);
    CREATE TABLE IF NOT EXISTS world_npcs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL, role TEXT, traits TEXT,
        closeness INTEGER DEFAULT 30, last_met_day INTEGER DEFAULT -1
    );
    CREATE TABLE IF NOT EXISTS world_user_sentiment (
        user_qq TEXT PRIMARY KEY, score INTEGER DEFAULT 0, updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_group_mood (
        group_id TEXT PRIMARY KEY, score INTEGER DEFAULT 0, updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_index INTEGER, minutes INTEGER, joy INTEGER, anger INTEGER,
        sad INTEGER, stress INTEGER, energy INTEGER, money INTEGER, activity TEXT
    );
    CREATE TABLE IF NOT EXISTS world_emotion (
        id INTEGER PRIMARY KEY CHECK (id=1),
        joy INTEGER DEFAULT 50, anger INTEGER DEFAULT 10,
        sad INTEGER DEFAULT 10, happy INTEGER DEFAULT 50,
        stress INTEGER DEFAULT 20, updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_needs (
        id INTEGER PRIMARY KEY CHECK (id=1),
        hunger INTEGER DEFAULT 20,
        social INTEGER DEFAULT 30,
        updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_event_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day_index INTEGER, text TEXT,
        segment TEXT, place TEXT, kind TEXT, used INTEGER DEFAULT 0, created_at REAL,
        photo INTEGER DEFAULT 0, photo_prompt TEXT
    );
    CREATE TABLE IF NOT EXISTS user_promises (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_qq TEXT, text TEXT,
        due_day INTEGER, asked INTEGER DEFAULT 0, created_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_qq TEXT NOT NULL, kind TEXT DEFAULT 'errand', title TEXT NOT NULL,
        status TEXT DEFAULT 'doing', place TEXT DEFAULT '',
        due_day INTEGER, due_minutes INTEGER, created_at REAL, done_at REAL, source TEXT,
        done_text TEXT, failed_reason TEXT, msg_id TEXT, deferred INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS world_pending (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, text TEXT,
        day_index INTEGER, shared INTEGER DEFAULT 0, created_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, target INTEGER DEFAULT 3000,
        progress INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day_index INTEGER, minutes INTEGER,
        amount INTEGER NOT NULL, reason TEXT, created_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, public INTEGER DEFAULT 0, tags TEXT
    );
    CREATE TABLE IF NOT EXISTS world_knowledge (
        npc_id INTEGER, fact_id INTEGER, learned_day INTEGER, PRIMARY KEY(npc_id, fact_id)
    );
    CREATE TABLE IF NOT EXISTS world_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_index INTEGER, minutes INTEGER, state_json TEXT, created_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_diary (
        day_index INTEGER PRIMARY KEY,
        text TEXT NOT NULL,
        created_at REAL
    );
    CREATE TABLE IF NOT EXISTS world_profile (
        id INTEGER PRIMARY KEY CHECK (id=1),
        card TEXT DEFAULT '',
        persona_hash TEXT DEFAULT '',
        settings_hash TEXT DEFAULT '',
        updated_at REAL
    );
    """)
    for col, typ in (("name", "TEXT DEFAULT ''"), ("gender", "TEXT DEFAULT ''"), ("age", "INTEGER DEFAULT 0"),
                     ("personality", "TEXT DEFAULT ''"), ("hobbies", "TEXT DEFAULT ''"), ("job", "TEXT DEFAULT ''"),
                     ("job_desc", "TEXT DEFAULT ''"), ("work_time", "TEXT DEFAULT ''"), ("salary", "INTEGER DEFAULT 0"),
                     ("home", "TEXT DEFAULT ''"), ("habits", "TEXT DEFAULT ''"),
                     ("likes", "TEXT DEFAULT ''"), ("dislikes", "TEXT DEFAULT ''"),
                     ("food", "TEXT DEFAULT ''"), ("catchphrase", "TEXT DEFAULT ''"), ("appearance", "TEXT DEFAULT ''")):
        try:
            conn.execute(f"ALTER TABLE world_profile ADD COLUMN {col} {typ}")
        except Exception:
            pass
    for col, typ in (("wake_day", "INTEGER DEFAULT 0"), ("wake_count", "INTEGER DEFAULT 0"),
                     ("awake_until_minutes", "INTEGER DEFAULT 0"), ("awake_until_day", "INTEGER DEFAULT 0"),
                     ("awake_activity", "TEXT DEFAULT ''")):
        try:
            conn.execute(f"ALTER TABLE world_state ADD COLUMN {col} {typ}")
        except Exception:
            pass
    for col, typ in (("msg_id", "TEXT"), ("deferred", "INTEGER DEFAULT 0")):
        try:
            conn.execute(f"ALTER TABLE world_tasks ADD COLUMN {col} {typ}")
        except Exception:
            pass
    for col, typ in (("persona_hash", "TEXT DEFAULT ''"), ("settings_hash", "TEXT DEFAULT ''")):
        try:
            conn.execute(f"ALTER TABLE world_profile ADD COLUMN {col} {typ}")
        except Exception:
            pass
    for col, typ in (("trust", "INTEGER DEFAULT 30"), ("respect", "INTEGER DEFAULT 30"), ("wary", "INTEGER DEFAULT 0")):
        try:
            conn.execute(f"ALTER TABLE world_npcs ADD COLUMN {col} {typ}")
        except Exception:
            pass
    try:
        conn.execute("ALTER TABLE world_state ADD COLUMN money INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        m = conn.execute("SELECT money FROM world_state WHERE id=1").fetchone()
        led = conn.execute("SELECT COUNT(*) FROM world_ledger").fetchone()[0]
        if m and (m["money"] or 0) == 0 and led == 0:
            conn.execute("UPDATE world_state SET money=200 WHERE id=1")
    except Exception:
        pass
    if not conn.execute("SELECT COUNT(*) FROM world_goals").fetchone()[0]:
        conn.execute("INSERT INTO world_goals(title,target,progress,status,created_at) VALUES(?,?,?,?,?)",
                     ("攒钱买一台数位屏", 3000, 0, "active", time.time()))
    if not conn.execute("SELECT COUNT(*) FROM world_facts").fetchone()[0]:
        conn.executemany("INSERT INTO world_facts(text,public,tags) VALUES(?,?,?)", [
            ("店长王姐下个月要盘下隔壁店面", 0, "工作"),
            ("阿凯在偷偷准备考试", 0, "朋友"),
            ("小区这周要停水两天", 1, "生活"),
        ])
    if not conn.execute("SELECT COUNT(*) FROM world_npcs").fetchone()[0]:
        conn.executemany("INSERT OR IGNORE INTO world_npcs(name,role,traits) VALUES(?,?,?)", [
            ("王姐", "便利店店长", "爽快、爱唠叨、护短"),
            ("阿凯", "夜班同事", "话多、爱打游戏、讲义气"),
            ("小陈", "常来买东西的熟客", "安静、喜欢猫、睡不好"),
            ("张阿姨", "楼下邻居", "热心、爱打听、会送吃的"),
            ("猫猫", "网上认识的朋友", "神秘、爱发猫图、作息乱"),
        ])
    if not conn.execute("SELECT id FROM world_emotion WHERE id=1").fetchone():
        conn.execute("INSERT INTO world_emotion(id,joy,anger,sad,happy,stress,updated_at) VALUES(1,50,10,10,50,20,?)", (time.time(),))
    if not conn.execute("SELECT id FROM world_needs WHERE id=1").fetchone():
        conn.execute("INSERT INTO world_needs(id,hunger,social,updated_at) VALUES(1,20,30,?)", (time.time(),))
    row = conn.execute("SELECT id FROM world_state WHERE id=1").fetchone()
    if not row:
        conn.execute("INSERT INTO world_state(id,day_index,minutes,weather,place,activity,energy,mood,updated_at)"
                     " VALUES(1,?,?,?,?,?,?,?,?)",
                     (_today_index(), 8 * 60, "晴", "家", "刚起床", 80, "平静", time.time()))
    conn.execute("UPDATE world_state SET money=200 WHERE id=1 AND COALESCE(money,0)=0 "
                 "AND (SELECT COUNT(*) FROM world_ledger)=0")


def _hm(text: str, default: int) -> int:
    try:
        h, m = str(text).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return default


def _in_window(minutes: int, start: int, end: int) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= minutes < end
    return minutes >= start or minutes < end


def _schedule(minutes: int, rest_start: int, rest_end: int, work_start: int, work_end: int, day: int = 0, emo: dict = None):
    """精确到分钟（5 分钟粒度）的一天；情绪会影响睡眠、加班和晚间安排。"""
    emo = emo or {}
    anger = int(emo.get("anger") or 0)
    sad = int(emo.get("sad") or 0)
    joy = int(emo.get("joy") or 0)
    stress = int(emo.get("stress") or 0)
    if _in_window(minutes, rest_start, rest_end):
        if anger >= 60 or stress >= 70:
            return "家", "失眠，翻来覆去", 0
        if sad >= 70:
            return "家", "睡得不安稳", +1
        return "家", "睡觉", +2
    m = minutes
    h = m // 60
    has_work = work_start != work_end
    weekday = (day + 3) % 7
    weekend = weekday >= 5
    pick = (day * 7 + h) % 4
    if has_work and work_end <= m < work_end + 60 and stress >= 70:
        return "公司", "心里烦，留下来加班", -1
    if has_work and _in_window(m, work_start, work_end):
        if 12 * 60 <= m < 12 * 60 + 40:
            return "公司", "午休吃饭", +1
        if 12 * 60 + 40 <= m < 13 * 60:
            return "公司", "刷手机休息", 0
        if 15 * 60 <= m < 15 * 60 + 20:
            return "公司", "接水发呆", 0
        if 17 * 60 + 40 <= m < work_end:
            return "公司", "收拾东西准备下班", 0
        return "公司", "上班", -1
    if 6 * 60 + 30 <= m < 6 * 60 + 55:
        return "家", "刚醒，赖床", +1
    if 6 * 60 + 55 <= m < 7 * 60 + 20:
        return "家", "洗漱", +1
    if 7 * 60 + 20 <= m < 7 * 60 + 45:
        return "家", "吃早饭", +1
    if 7 * 60 + 45 <= m < 8 * 60:
        return "家", "换衣服准备出门", 0
    if has_work:
        if m < work_start and m >= 8 * 60:
            return ("路上", "通勤上班", 0) if m < work_start - 15 else ("公司楼下", "买杯咖啡", 0)
        if work_end <= m < work_end + 25:
            return "路上", "下班回家", 0
        if work_end + 25 <= m < work_end + 45:
            return "超市", "顺路买菜", 0
    elif not weekend:
        if 8 * 60 <= m < 9 * 60 + 30:
            return "家", "做家务", -1
        if 9 * 60 + 30 <= m < 10 * 60 + 30:
            return "超市", "买菜", 0
        if 10 * 60 + 30 <= m < 11 * 60 + 30:
            return "家", "做饭", 0
        if 11 * 60 + 30 <= m < 12 * 60:
            return "家", "吃午饭", +1
        if 12 * 60 <= m < 13 * 60:
            return "家", ["看书", "打游戏", "刷手机", "整理房间"][pick], 0
        if 14 * 60 <= m < 16 * 60:
            return "街上", ["散步", "逛超市", "去咖啡店坐坐", "随便走走"][pick], 0
        if 16 * 60 <= m < 17 * 60:
            return "家", ["打游戏", "看剧", "摆弄东西", "发呆"][pick], 0
    else:
        if 8 * 60 <= m < 9 * 60 + 30:
            return "家", "睡懒觉", +1
        if 9 * 60 + 30 <= m < 11 * 60:
            return "家", ["打游戏", "追剧", "赖在床上", "刷手机"][pick], 0
        if 11 * 60 <= m < 11 * 60 + 40:
            return "家", "收拾屋子", -1
        if 11 * 60 + 40 <= m < 13 * 60:
            return "家", "做午饭", 0
        if 13 * 60 <= m < 17 * 60:
            return "街上", ["出去逛逛", "找朋友坐坐", "看电影", "在公园待着"][pick], 0
    if 17 * 60 <= m < 17 * 60 + 40:
        return "家", "择菜准备晚饭", 0
    if 17 * 60 + 40 <= m < 18 * 60 + 30:
        return "家", "做饭", 0
    if 18 * 60 + 30 <= m < 19 * 60:
        return "家", "吃晚饭", +1
    if 19 * 60 <= m < 19 * 60 + 25:
        return "家", "洗碗收拾", 0
    if 19 * 60 + 25 <= m < 20 * 60:
        return "家", "洗澡", +1
    if 20 * 60 <= m < 20 * 60 + 30:
        return "家", "晾衣服/收拾", 0
    if 20 * 60 + 30 <= m:
        if joy >= 70:
            return "街上", "心情好，出去走走", 0
        if sad >= 70:
            return "家", "缩在床上不想动", 0
        return "家", ["追剧", "打游戏", "看小说", "听歌发呆"][pick], 0
    return "家", "随便待着", 0


class WorldMixin:
    async def world_loop(self):
        # 停机期间漏掉的推进，启动时补齐（最多补一天）
        try:
            st = self.world_state()
            if st and time.time() - float(st.get("updated_at") or 0) > 600:
                missed = min(288, int((time.time() - float(st["updated_at"])) // 300))
                for _ in range(missed):
                    _st = self.world_tick(5)
                try:
                    if _st:
                        await self._maybe_greetings(
                            _st["day_index"], _st["minutes"],
                            _hm(self.store.get_setting("world_rest_start", "22:00"), 22 * 60),
                            _hm(self.store.get_setting("world_rest_end", "07:00"), 7 * 60))
                except Exception as e:
                    log.warning("问候检查失败: %s", e)
                try:
                    if _st and self.store.get_setting("event_pool_day", "") != str(_st["day_index"]):
                        self.store.set_setting("event_pool_day", str(_st["day_index"]))
                        await self.generate_event_pool(_st["day_index"])
                    await self._promise_tick()
                except Exception:
                    pass
                log.info("世界补推进 %d 个刻度", missed)
        except Exception as e:
            log.warning("世界补推进失败: %s", e)
        while not self._stop:
            try:
                if self.store.get_setting("world_enabled", "1") == "1":
                    from datetime import datetime as _dt
                    _now = _dt.now()
                    _st = self.world_state()
                    if _st:
                        _diff = ((_now.hour * 60 + _now.minute) - int(_st.get("minutes") or 0)) % 1440
                        if 5 < _diff <= 720:
                            for _ in range(min(288, _diff // 5)):
                                self.world_tick(5)
                            _st = self.world_state()
                            log.info("世界时钟对齐: %s", self._world_clock_text(_st["day_index"], _st["minutes"]))
                    _st2 = self.world_state()
                    if _st2:
                        try:
                            await self._maybe_greetings(
                                _st2["day_index"], _st2["minutes"],
                                _hm(self.store.get_setting("world_rest_start", "22:00"), 22 * 60),
                                _hm(self.store.get_setting("world_rest_end", "07:00"), 7 * 60))
                        except Exception:
                            pass
            except Exception as e:
                log.warning("世界时钟对齐失败: %s", e)
            await asyncio.sleep(300)
            try:
                if self.store.get_setting("world_enabled", "1") != "1":
                    continue
                _st3 = self.world_tick(5)
                if _st3:
                    try:
                        await self._maybe_greetings(
                            _st3["day_index"], _st3["minutes"],
                            _hm(self.store.get_setting("world_rest_start", "22:00"), 22 * 60),
                            _hm(self.store.get_setting("world_rest_end", "07:00"), 7 * 60))
                        await self._promise_tick()
                    except Exception:
                        pass
            except Exception as e:
                log.warning("世界 tick 异常: %s", e)

    def world_state(self) -> dict:
        with self.store._conn() as c:
            r = c.execute("SELECT * FROM world_state WHERE id=1").fetchone()
        return dict(r) if r else {}

    def world_tick(self, advance: int = 5) -> dict:
        st = self.world_state()
        if not st:
            return {}
        minutes = st["minutes"] + advance
        day = st["day_index"]
        while minutes >= 1440:
            minutes -= 1440
            day += 1
        rest_start = _hm(self.store.get_setting("world_rest_start", "22:00"), 22 * 60)
        diary_day = day if st["minutes"] < rest_start <= minutes else None
        rest_end = _hm(self.store.get_setting("world_rest_end", "07:00"), 7 * 60)
        wake_day = day if st["minutes"] < rest_end <= minutes else None
        work_start = _hm(self.store.get_setting("world_work_start", ""), 0)
        work_end = _hm(self.store.get_setting("world_work_end", ""), 0)
        place, activity, delta = _schedule(minutes, rest_start, rest_end, work_start, work_end, day, self.world_emotion())
        awake_until = st.get("awake_until_minutes", 0) or 0
        awake_day = st.get("awake_until_day", 0) or 0
        still_awake = awake_day > day or (awake_day == day and awake_until > minutes)
        was_sleep = "睡觉" in str(st.get("activity") or "")
        if still_awake and _in_window(minutes, rest_start, rest_end):
            place, activity, delta = "家", (st.get("awake_activity") or "刷手机"), 0
        elif was_sleep and not still_awake and _in_window(minutes, rest_start, rest_end):
            pass
        if not still_awake and (st.get("awake_activity") or ""):
            pass
        energy = max(0, min(100, st["energy"] + delta * (advance // 5 or 1)))
        if "睡觉" in activity:
            mood = "困"
        elif "失眠" in activity:
            mood = "烦躁"
        elif "加班" in activity:
            mood = "累"
        else:
            mood = "疲惫" if energy < 25 else ("有精神" if energy > 70 else "平静")
        emo_d = {"joy": 0, "anger": 0, "sad": 0, "happy": 0, "stress": 0}
        needs = self.world_needs()
        hunger = min(100, needs["hunger"] + max(1, advance // 30))
        social = min(100, needs["social"] + max(1, advance // 30))
        with self.store._conn() as c:
            old_day = st["day_index"] if day != st["day_index"] else None
            c.execute("UPDATE world_state SET day_index=?,minutes=?,place=?,activity=?,energy=?,mood=?,updated_at=? WHERE id=1",
                      (day, minutes, place, activity, energy, mood, time.time()))
            if day != st.get("day_index"):
                c.execute("UPDATE world_state SET wake_count=0,wake_day=? WHERE id=1", (day,))
                c.execute("DELETE FROM world_pending WHERE day_index<?", (day - 7,))
                e2 = dict(c.execute("SELECT * FROM world_emotion WHERE id=1").fetchone())
                c.execute("UPDATE world_emotion SET joy=?,anger=?,sad=?,stress=? WHERE id=1",
                          (50 + int((e2["joy"] - 50) * 0.6), max(0, e2["anger"] - 3),
                           max(0, e2["sad"] - 3), max(0, e2["stress"] - 5)))
            if not still_awake and st.get("awake_activity"):
                c.execute("UPDATE world_state SET awake_activity='',awake_until_day=0,awake_until_minutes=0 WHERE id=1")
                c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                          (day, minutes, "sleep", f"{self._world_clock_text(day, minutes)} 又睡着了", time.time()))
            c.execute("UPDATE world_needs SET hunger=?,social=?,updated_at=? WHERE id=1", (hunger, social, time.time()))
            if place != st["place"] or activity != st["activity"]:
                log.info("世界状态: %s 在%s%s", self._world_clock_text(day, minutes), place, activity)
                c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                          (day, minutes, "move", f"{self._world_clock_text(day, minutes)} 在{place}{activity}", time.time()))
            paid_today = c.execute("SELECT 1 FROM world_ledger WHERE day_index=? AND reason='工资'", (day,)).fetchone()
            if not paid_today and ((st["activity"] == "上班" and activity != "上班") or (st["minutes"] < 1080 <= minutes)):
                try:
                    _sal = int(self.store.get_setting("world_salary", "0") or 0)
                except Exception:
                    _sal = 0
                _daily = max(50, round(_sal / 22)) if _sal else 120
                c.execute("INSERT INTO world_ledger(day_index,minutes,amount,reason,created_at) VALUES(?,?,?,?,?)",
                          (day, minutes, _daily, "工资", time.time()))
                c.execute("UPDATE world_state SET money=COALESCE(money,0)+? WHERE id=1", (_daily,))
                c.execute("UPDATE world_goals SET progress=progress+? WHERE status='active'", (_daily,))
            if minutes % 60 < advance:
                e0 = dict(c.execute("SELECT * FROM world_emotion WHERE id=1").fetchone())
                c.execute("UPDATE world_emotion SET anger=?,sad=?,stress=?,joy=? WHERE id=1",
                          (max(0, e0["anger"] - 1), max(0, e0["sad"] - 1), max(0, e0["stress"] - 2),
                           50 + int((e0["joy"] - 50) * 0.95)))
            hour_slot = minutes // 60
            has_hour = c.execute("SELECT 1 FROM world_history WHERE day_index=? AND minutes>=? AND minutes<?",
                                 (day, hour_slot * 60, hour_slot * 60 + 60)).fetchone()
            if not has_hour:
                e = self.world_emotion()
                c.execute("INSERT INTO world_history(day_index,minutes,joy,anger,sad,stress,energy,money,activity)"
                          " VALUES(?,?,?,?,?,?,?,?,?)",
                          (day, hour_slot * 60, e["joy"], e["anger"], e["sad"], e["stress"], energy,
                           int((c.execute("SELECT money FROM world_state WHERE id=1").fetchone() or [0])[0] or 0),
                           activity))
                c.execute("DELETE FROM world_history WHERE id NOT IN (SELECT id FROM world_history ORDER BY id DESC LIMIT 240)")
                c.execute("INSERT INTO world_snapshots(day_index,minutes,state_json,created_at) VALUES(?,?,?,?)",
                          (day, minutes, json.dumps({"day_index": day, "minutes": minutes, "place": place,
                                                     "activity": activity, "energy": energy, "mood": mood,
                                                     "weather": st.get("weather", "晴")}, ensure_ascii=False), time.time()))
            if minutes % 60 < advance:
                if activity == "睡觉":
                    emo_d["stress"] -= 2; emo_d["joy"] += 1
                elif activity == "上班":
                    emo_d["stress"] += 1
                else:
                    e0 = self.world_emotion()
                    if e0["joy"] > 50: emo_d["joy"] -= 1
                    elif e0["joy"] < 50: emo_d["joy"] += 1
                    if e0["stress"] > 20: emo_d["stress"] -= 1
            if minutes % 120 < advance and activity not in ("睡觉",):
                texts = ["在家翻到以前的东西，愣了一会儿", "刷到个挺有意思的视频，看了两遍",
                         "突然想起一件一直没做的事", "闻到楼下飘上来的饭味，有点想吃"]
                c.execute("INSERT INTO world_pending(kind,text,day_index,shared,created_at) VALUES(?,?,?,0,?)",
                          ("discover", texts[(day + minutes // 60) % len(texts)], day, time.time()))
            npcs = self.world_npcs()
            if npcs and place == "街上" and minutes % 60 < advance:
                n = npcs[min(len(npcs) - 1, (minutes // 60) % len(npcs))]
                if n["last_met_day"] != day:
                    c.execute("UPDATE world_npcs SET closeness=MIN(100,closeness+1),trust=MIN(100,COALESCE(trust,30)+1),last_met_day=? WHERE id=?", (day, n["id"]))
                    c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                              (day, minutes, "meet", f"{self._world_clock_text(day, minutes)} 在街上遇到{n['name']}", time.time()))
                    if (day + minutes // 60) % 3 == 0:
                        mood_texts = [f"被{n['name']}当众数落了两句", f"跟{n['name']}说话被敷衍了",
                                      f"和{n['name']}有点小别扭"]
                        txt = mood_texts[(day + minutes // 60) % len(mood_texts)]
                        c.execute("INSERT INTO world_pending(kind,text,day_index,shared,created_at) VALUES(?,?,?,0,?)",
                                  ("social", txt, day, time.time()))
                        c.execute("UPDATE world_state SET mood='郁闷' WHERE id=1")
                        emo_d["sad"] += 4; emo_d["anger"] += 3; emo_d["joy"] -= 2
                    elif minutes % 90 < advance:
                        good = [f"在街上看到一只很胖的猫，蹲那看了半天", f"发现楼下新开了一家店",
                                f"听到路边有人弹吉他，还挺好听"]
                        c.execute("INSERT INTO world_pending(kind,text,day_index,shared,created_at) VALUES(?,?,?,0,?)",
                                  ("discover", good[(day + minutes // 60) % len(good)], day, time.time()))
                        emo_d["joy"] += 2
                    if minutes % 120 < advance:
                        fact = c.execute("SELECT * FROM world_facts ORDER BY RANDOM() LIMIT 1").fetchone()
                        if fact:
                            c.execute("INSERT OR IGNORE INTO world_knowledge(npc_id,fact_id,learned_day) VALUES(?,?,?)",
                                      (n["id"], fact["id"], day))
                            c.execute("INSERT INTO world_pending(kind,text,day_index,shared,created_at) VALUES(?,?,?,0,?)",
                                      ("fact", f"听说{fact['text']}", day, time.time()))
        try:
            if wake_day is not None:
                with self.store._conn() as c:
                    slept = c.execute("SELECT COUNT(*) FROM world_history WHERE day_index=? AND activity LIKE '%睡%'", (day - 1,)).fetchone()[0]
                if slept and slept * 60 < 390:
                    with self.store._conn() as c:
                        c.execute("UPDATE world_state SET energy=MIN(energy,45),mood='没睡够' WHERE id=1")
                        c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                                  (day, minutes, "tired", f"{self._world_clock_text(day, minutes)} 昨晚没睡够，有点困", time.time()))
                    energy = min(energy, 45)
            if self.store.get_setting("incident_day", "") != str(day) and 15 < (minutes // 60) < 22:
                import random as _r
                if _r.random() < 0.25:
                    self.store.set_setting("incident_day", str(day))
                    inc = _r.choice(["钥匙找不到了，翻了半天", "快递到了，懒得下楼拿", "楼下在装修，有点吵",
                                     "手机差点没电，赶紧充上", "发现冰箱里没什么吃的了"])
                    with self.store._conn() as c:
                        c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                                  (day, minutes, "incident", f"{self._world_clock_text(day, minutes)} {inc}", time.time()))
            if 9 <= (minutes // 60) <= 21 and minutes % 120 < advance:
                ev = self._pop_event(day, minutes, place)
                if ev:
                    with self.store._conn() as c:
                        c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                                  (day, minutes, "life", f"{self._world_clock_text(day, minutes)} {ev['text']}", time.time()))
                    if ev.get("kind") in ("生活", "兴趣", "小意外"):
                        self.world_emotion_adjust(joy=1)
                    import random as _r
                    if ev.get("photo"):
                        asyncio.get_running_loop().create_task(self.maybe_live_photo(ev, day, minutes))
                    if _r.random() < 0.45 and ev.get("kind") in ("生活", "兴趣", "小意外", "社交"):
                        with self.store._conn() as c:
                            c.execute("INSERT INTO world_pending(kind,text,day_index,shared,created_at) VALUES(?,?,?,0,?)",
                                      ("life", ev["text"], day, time.time()))
            asyncio.get_running_loop().create_task(self._promise_tick())
            asyncio.get_running_loop().create_task(self._maybe_greetings(day, minutes, rest_start, rest_end))
            if diary_day is not None and not self.diary_exists(diary_day):
                asyncio.get_running_loop().create_task(self._write_diary_ai(diary_day))
            if old_day is not None and not self.diary_exists(old_day):
                asyncio.get_running_loop().create_task(self._write_diary_ai(old_day))
        except Exception:
            pass
        if any(emo_d.values()):
            self.world_emotion_adjust(**{k: v for k, v in emo_d.items() if v})
        try:
            self._task_tick()
        except Exception as e:
            log.warning("任务检查失败: %s", e)
        new_st = self.world_state()
        try:
            if place != st["place"] or activity != st["activity"]:
                self._world_proactive(st, new_st)
            else:
                with self.store._conn() as c:
                    has = c.execute("SELECT COUNT(*) FROM world_pending WHERE shared=0 AND day_index=?", (day,)).fetchone()[0]
                if has:
                    self._world_proactive(st, new_st)
        except Exception as e:
            log.warning("世界主动消息异常: %s", e)
        return new_st

    def world_money(self) -> int:
        with self.store._conn() as c:
            r = c.execute("SELECT money FROM world_state WHERE id=1").fetchone()
        return int(r["money"] or 0) if r else 0

    def world_goals(self) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM world_goals WHERE status='active' ORDER BY id")]

    def world_ledger(self, limit: int = 8) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM world_ledger ORDER BY id DESC LIMIT ?", (limit,))]

    def world_knowledge(self) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT n.name, f.text FROM world_knowledge k JOIN world_npcs n ON n.id=k.npc_id "
                "JOIN world_facts f ON f.id=k.fact_id ORDER BY k.learned_day DESC LIMIT 6")]

    def world_emotion(self) -> dict:
        with self.store._conn() as c:
            r = c.execute("SELECT * FROM world_emotion WHERE id=1").fetchone()
        return dict(r) if r else {"joy": 50, "anger": 10, "sad": 10, "happy": 50, "stress": 20}

    POS_WORDS = ("谢谢", "喜欢", "开心", "哈哈", "可爱", "辛苦", "加油", "抱抱", "想你", "厉害", "好看")
    NEG_WORDS = ("傻", "滚", "闭嘴", "废物", "讨厌", "烦死", "去死", "骂", "垃圾", "没用", "别烦我")

    COMFORT_WORDS = ("别难过", "抱抱", "没事的", "辛苦了", "理解你", "对不起", "别生气")

    def world_chat_mood(self, text: str, uid: str = "", gid: str = "") -> dict:
        """聊天内容对 AI 自身情绪、对这个人、对这个群的影响；纯规则，零模型成本。"""
        t = (text or "")[:300]
        if not t:
            return self.world_emotion()
        pos = sum(1 for w in self.POS_WORDS if w in t)
        neg = sum(1 for w in self.NEG_WORDS if w in t)
        comfort = sum(1 for w in self.COMFORT_WORDS if w in t)
        delta = 0
        if pos and not neg:
            self.world_emotion_adjust(joy=min(3, pos), stress=-1)
            delta = min(3, pos)
            if comfort:
                self.world_emotion_adjust(anger=-2, sad=-2)
        elif neg and not pos:
            self.world_emotion_adjust(anger=min(4, neg * 2), sad=min(3, neg), joy=-2, stress=1)
            delta = -min(4, neg * 2)
        if uid and delta:
            with self.store._conn() as c:
                c.execute("INSERT INTO world_user_sentiment(user_qq,score,updated_at) VALUES(?,?,?) "
                          "ON CONFLICT(user_qq) DO UPDATE SET score=MAX(-100,MIN(100,score+?)),updated_at=?",
                          (str(uid), delta, time.time(), delta, time.time()))
        if gid and delta:
            with self.store._conn() as c:
                c.execute("INSERT INTO world_group_mood(group_id,score,updated_at) VALUES(?,?,?) "
                          "ON CONFLICT(group_id) DO UPDATE SET score=MAX(-100,MIN(100,score+?)),updated_at=?",
                          (str(gid), delta, time.time(), delta, time.time()))
        return self.world_emotion()

    def world_user_sentiment(self, uid: str) -> int:
        if not uid:
            return 0
        with self.store._conn() as c:
            r = c.execute("SELECT score FROM world_user_sentiment WHERE user_qq=?", (str(uid),)).fetchone()
        return int(r["score"] or 0) if r else 0

    def world_group_mood(self, gid: str) -> int:
        if not gid:
            return 0
        with self.store._conn() as c:
            r = c.execute("SELECT score FROM world_group_mood WHERE group_id=?", (str(gid),)).fetchone()
        return int(r["score"] or 0) if r else 0

    def world_emotion_adjust(self, joy=0, anger=0, sad=0, happy=0, stress=0):
        e = self.world_emotion()
        vals = {k: max(0, min(100, int(e.get(k, 0)) + v)) for k, v in
                (("joy", joy), ("anger", anger), ("sad", sad), ("happy", happy), ("stress", stress))}
        with self.store._conn() as c:
            c.execute("UPDATE world_emotion SET joy=?,anger=?,sad=?,happy=?,stress=?,updated_at=? WHERE id=1",
                      (vals["joy"], vals["anger"], vals["sad"], vals["happy"], vals["stress"], time.time()))

    def world_mood_text(self) -> str:
        e = self.world_emotion()
        if e["anger"] >= 60:
            return "有点窝火"
        if e["sad"] >= 60:
            return "低落"
        if e["joy"] >= 65:
            return "心情不错"
        if e["stress"] >= 60:
            return "有点累"
        return "平静"

    def world_needs(self) -> dict:
        with self.store._conn() as c:
            r = c.execute("SELECT * FROM world_needs WHERE id=1").fetchone()
        return dict(r) if r else {"hunger": 20, "social": 30}

    def world_npcs(self) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM world_npcs ORDER BY closeness DESC")]

    def world_diary(self, day: int = -1):
        with self.store._conn() as c:
            if day < 0:
                r = c.execute("SELECT * FROM world_diary ORDER BY day_index DESC LIMIT 1").fetchone()
            else:
                r = c.execute("SELECT * FROM world_diary WHERE day_index=?", (day,)).fetchone()
        return dict(r) if r else None

    def diary_exists(self, day: int) -> bool:
        with self.store._conn() as c:
            return bool(c.execute("SELECT 1 FROM world_diary WHERE day_index=?", (day,)).fetchone())

    def _diary_material(self, day: int) -> str:
        with self.store._conn() as c:
            events = [r["text"] for r in c.execute(
                "SELECT text FROM world_events WHERE day_index=? ORDER BY id", (day,))]
            acts = [r["activity"] for r in c.execute(
                "SELECT DISTINCT activity FROM world_history WHERE day_index=? ORDER BY id", (day,))]
            meets = [r["name"] for r in c.execute(
                "SELECT name FROM world_npcs WHERE last_met_day=?", (day,))]
            tasks = [r["title"] for r in c.execute(
                "SELECT title FROM world_tasks WHERE status='done' AND due_day=?", (day,))]
        emo = self.world_emotion()
        lines = []
        if events:
            lines.append("当天经历：" + "；".join(x.split(" ", 1)[-1] for x in events[-20:]))
        if acts:
            lines.append("做过的事：" + "、".join(acts[:20]))
        if tasks:
            lines.append("帮人办成的事：" + "、".join(tasks[:6]))
        if meets:
            lines.append("见到的人：" + "、".join(meets[:6]))
        lines.append(f"当天情绪：开心{emo['joy']} 烦躁{emo['anger']} 低落{emo['sad']} 压力{emo['stress']}")
        return "\n".join(lines)

    async def _write_diary_ai(self, day: int):
        material = self._diary_material(day)
        if not material.strip():
            return
        text = ""
        try:
            text = await self.llm_complete(
                "你是这个角色本人。睡觉前用第一人称写今天的日记，像普通人随手记，150~250字。"
                "口语、自然、有情绪，可以写今天累了、开心、吃了什么、见了谁、帮人做了什么。"
                "不要列点，不要写“作为AI”，不要提世界引擎、时间线、系统。",
                material, max_tokens=400, temperature=0.85, timeout=60)
            text = (text or "").strip()
        except Exception as e:
            log.warning("AI 日记生成失败，改用事件摘要: %s", e)
        if not text:
            text = "昨天：" + "；".join(x for x in material.split("\n") if x)[:300] + "。"
        text = text[:800]
        with self.store._conn() as c:
            c.execute("INSERT OR REPLACE INTO world_diary(day_index,text,created_at) VALUES(?,?,?)",
                      (day, text, time.time()))
        log.info("日记已生成: 第%s天 %s 字", day, len(text))

    def world_low_mood(self) -> bool:
        try:
            e = self.world_emotion()
            return e.get("anger", 0) >= 70 or e.get("sad", 0) >= 70
        except Exception:
            return False

    async def update_weather_location(self, ip: str, force: bool = False):
        try:
            if not force and self.store.get_setting("weather_loc_source", "") == "manual" \
                    and self.store.get_setting("weather_lat", ""):
                return
            self.store.set_setting("weather_admin_ip", str(ip)[:64])
            if not ip or ip.startswith(("127.", "10.", "192.168.", "172.")):
                return
            async with self.http.get(f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,district,lat,lon",
                                     timeout=aiohttp.ClientTimeout(total=5)) as r:
                d = await r.json(content_type=None)
            if d.get("status") == "success" and d.get("lat"):
                self.store.set_setting("weather_lat", str(d.get("lat")))
                self.store.set_setting("weather_lon", str(d.get("lon")))
                self.store.set_setting("weather_city", f"{d.get('regionName') or ''}{d.get('city') or ''}"[:40])
                self.store.set_setting("weather_district", str(d.get("district") or "")[:40])
                self.store.set_setting("weather_updated", "0")
                if self.store.get_setting("weather_loc_source", "") != "manual":
                    self.store.set_setting("weather_loc_source", "ip")
                log.info("天气定位: %s %s%s", ip, d.get("city"), d.get("district") or "")
        except Exception as e:
            log.warning("天气定位失败: %s", e)

    async def weather_data(self, force: bool = False) -> dict:
        try:
            lat = float(self.store.get_setting("weather_lat", "0") or 0)
            lon = float(self.store.get_setting("weather_lon", "0") or 0)
        except Exception:
            lat = lon = 0
        if not lat or not lon:
            ip = self.store.get_setting("weather_admin_ip", "")
            if ip:
                await self.update_weather_location(ip)
                try:
                    lat = float(self.store.get_setting("weather_lat", "0") or 0)
                    lon = float(self.store.get_setting("weather_lon", "0") or 0)
                except Exception:
                    pass
        if not lat or not lon:
            return {}
        cached = self.store.get_setting("weather_cache", "")
        try:
            updated = float(self.store.get_setting("weather_updated", "0") or 0)
        except Exception:
            updated = 0
        if cached and not force and time.time() - updated < 1800:
            try:
                return json.loads(cached)
            except Exception:
                pass
        try:
            url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                   "&current=temperature_2m,precipitation,weather_code,relative_humidity_2m,wind_speed_10m"
                   "&hourly=temperature_2m,precipitation_probability,precipitation,weather_code,relative_humidity_2m,wind_speed_10m"
                   "&daily=precipitation_probability_max,weather_code,temperature_2m_max,temperature_2m_min"
                   "&timezone=Asia/Shanghai&forecast_days=1" % (lat, lon))
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                d = await r.json(content_type=None)
            cur = d.get("current") or {}
            hourly = d.get("hourly") or {}
            daily = d.get("daily") or {}
            times = hourly.get("time") or []
            probs = hourly.get("precipitation_probability") or []
            precs = hourly.get("precipitation") or []
            codes = hourly.get("weather_code") or []
            hums = hourly.get("relative_humidity_2m") or []
            winds = hourly.get("wind_speed_10m") or []
            rain_codes = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
            windows = []
            curw = None
            for i, t in enumerate(times):
                code = int(codes[i] or 0) if i < len(codes) else 0
                prob = int(probs[i] or 0) if i < len(probs) else 0
                pre = float(precs[i] or 0) if i < len(precs) else 0
                wet = pre > 0.05 or (code in rain_codes and prob >= 50) or prob >= 70
                if wet:
                    sev = "小雨"
                    if code in (63, 66, 80, 81):
                        sev = "中雨"
                    elif code in (65, 67, 82, 95, 96, 99):
                        sev = "大雨"
                    if curw is None:
                        curw = [int(t[11:13]), int(t[11:13]), sev]
                    else:
                        curw[1] = int(t[11:13])
                        if sev == "大雨":
                            curw[2] = "大雨"
                        elif sev == "中雨" and curw[2] == "小雨":
                            curw[2] = "中雨"
                else:
                    if curw:
                        windows.append(curw)
                        curw = None
            if curw:
                windows.append(curw)
            code_now = int(cur.get("weather_code") or 0)
            fog = code_now in (45, 48) or any(int(c or 0) in (45, 48) for c in codes)
            pm25 = 0
            try:
                aq = ("https://air-quality-api.open-meteo.com/v1/air-quality?latitude=%s&longitude=%s"
                      "&hourly=pm2_5,pm10&timezone=Asia/Shanghai&forecast_days=1" % (lat, lon))
                async with self.http.get(aq, timeout=aiohttp.ClientTimeout(total=8)) as ar:
                    ad = await ar.json(content_type=None)
                ah = ad.get("hourly") or {}
                vals = [v for v in (ah.get("pm2_5") or []) if v is not None]
                if vals:
                    pm25 = max(vals)
            except Exception:
                pass
            tmax = (daily.get("temperature_2m_max") or [None])[0]
            tmin = (daily.get("temperature_2m_min") or [None])[0]
            wmax = max([float(w or 0) for w in winds], default=0)
            havg = sum([float(h or 0) for h in hums]) / max(1, len([h for h in hums if h is not None]))
            windows = windows[:4]
            def hh(h):
                return f"{h:02d}点"
            rain_desc = ""
            if windows:
                rain_desc = "、".join(f"{hh(a)}-{hh(b+1)}{sev}" for a, b, sev in windows)
            else:
                rain_desc = "没有明显降雨"
            haze = pm25 >= 75
            advice = []
            try:
                lo = float(tmin) if tmin is not None else None
                hi = float(tmax) if tmax is not None else None
            except Exception:
                lo = hi = None
            if lo is not None:
                if lo <= 0:
                    advice.append("很冷，羽绒服/厚棉服")
                elif lo <= 5:
                    advice.append("冷，厚外套加毛衣")
                elif lo <= 10:
                    advice.append("偏冷，外套或风衣")
                elif lo <= 16:
                    advice.append("凉，薄外套/长袖")
                elif lo <= 22:
                    advice.append("舒适，长袖或薄衫")
                else:
                    advice.append("偏热，短袖")
            if hi is not None and hi >= 33:
                advice.append("中午热，注意防中暑、多喝水")
            if wmax >= 25:
                advice.append("风大，注意保暖别着凉")
            if havg >= 80:
                advice.append("湿度高，容易感冒")
            if haze:
                advice.append("有雾霾，出门戴口罩")
            if fog:
                advice.append("有雾，骑车开车慢点")
            facts = (f"地点：{self.store.get_setting('weather_city','')}{self.store.get_setting('weather_district','')}；"
                     f"今天气温 {tmin}~{tmax}℃；降雨：{rain_desc}；"
                     + ("有雾霾；" if haze else "") + ("有雾；" if fog else "")
                     + f"最大风速 {round(wmax)}km/h，平均湿度 {round(havg)}%；"
                     + "；".join(advice))
            text = ("今天有雨：" + rain_desc) if windows else "今天没雨"
            if haze:
                text += "，有雾霾"
            out = {"rain": bool(windows), "windows": windows, "rain_desc": rain_desc,
                   "fog": fog, "haze": haze, "pm25": round(pm25), "prob": int((daily.get("precipitation_probability_max") or [0])[0] or 0),
                   "temp": cur.get("temperature_2m"), "tmax": tmax, "tmin": tmin,
                   "wind": round(wmax), "humidity": round(havg),
                   "city": self.store.get_setting("weather_city", ""),
                   "district": self.store.get_setting("weather_district", ""),
                   "facts": facts, "advice": advice, "text": text, "updated": time.time()}
            self.store.set_setting("weather_cache", json.dumps(out, ensure_ascii=False))
            self.store.set_setting("weather_updated", str(time.time()))
            return out
        except Exception as e:
            log.warning("天气获取失败: %s", e)
            try:
                return json.loads(cached) if cached else {}
            except Exception:
                return {}

    async def detect_promise(self, uid: str, text: str):
        text = str(text or "").strip()
        if not text or not re.search(r"明天|后天|下周|下个月|周末|过几天", text):
            return
        if not re.search(r"面试|考试|复查|体检|出差|搬家|生日|见面|约会|开会|答辩|入职|开学|旅行|回家", text):
            return
        st = self.world_state()
        if not st:
            return
        today = self._world_clock_text(st["day_index"], st["minutes"]).split(" ")[0]
        try:
            raw = await self.llm_complete(
                '从这句话里提取对方接下来要做的一件事和日期，只输出 JSON：{"promise":"事情，不超过20字","date":"YYYY-MM-DD"}；判断不出就输出 {}。',
                f"今天是 {today}。句子：{text[:200]}", max_tokens=80, temperature=0.1, timeout=30)
            m = re.search(r"\{.*\}", raw or "", re.S)
            if not m:
                return
            d = json.loads(m.group(0))
            promise = str(d.get("promise") or "").strip()[:40]
            date_s = str(d.get("date") or "").strip()
            if not promise or not re.match(r"\d{4}-\d{2}-\d{2}", date_s):
                return
            import datetime as _d
            due = _d.date.fromisoformat(date_s)
            due_day = (due - _d.date(2026, 1, 1)).days
            if due_day < st["day_index"] or due_day > st["day_index"] + 30:
                return
            with self.store._conn() as c:
                c.execute("INSERT INTO user_promises(user_qq,text,due_day,asked,created_at) VALUES(?,?,?,0,?)",
                          (str(uid), promise, due_day, time.time()))
        except Exception as e:
            log.warning("承诺识别失败: %s", e)

    def promises_context(self, uid: str) -> str:
        try:
            st = self.world_state()
            if not st or not uid:
                return ""
            with self.store._conn() as c:
                rows = c.execute("SELECT text,due_day FROM user_promises WHERE user_qq=? AND asked=0 AND due_day BETWEEN ? AND ? ORDER BY due_day LIMIT 2",
                                 (str(uid), st["day_index"], st["day_index"] + 3)).fetchall()
            if not rows:
                return ""
            return "\n你记得对方说过：" + "；".join(r["text"] for r in rows) + "。合适的时候可以问一句。"
        except Exception:
            return ""

    async def _promise_tick(self):
        st = self.world_state()
        if not st:
            return
        with self.store._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM user_promises WHERE asked=0 AND due_day<=? ORDER BY due_day LIMIT 3", (st["day_index"],))]
        for r in rows:
            with self.store._conn() as c:
                c.execute("UPDATE user_promises SET asked=1 WHERE id=?", (r["id"],))
            try:
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(r["user_qq"]),
                    "message": [{"type": "text", "data": {"text": f"你之前说{r['text']}，怎么样了？"}}]})
            except Exception:
                pass

    async def generate_event_pool(self, day: int):
        with self.store._conn() as c:
            for col, typ in (("photo", "INTEGER DEFAULT 0"), ("photo_prompt", "TEXT")):
                try:
                    c.execute(f"ALTER TABLE world_event_pool ADD COLUMN {col} {typ}")
                except Exception:
                    pass
        pr = self._profile()
        persona = ""
        try:
            persona = (self.persona_text() or "")[:400]
        except Exception:
            pass
        weather = ""
        try:
            weather = self.weather_note("") or ""
        except Exception:
            pass
        weekday = "一二三四五六日"[(day + 3) % 7]
        sys = ('你是生活编剧。根据这个角色的身份、性格、爱好、工作和天气，写 6 件今天可能发生的小事。'
               '只输出 JSON：{"events":[{"text":"一句话，第一人称，具体、有生活毛边",'
               '"segment":"早上/中午/下午/晚上","place":"家/公司/街上/任意","kind":"生活/工作/社交/兴趣/小意外",'
               '"photo":true或false,"photo_prompt":"如果拍照，描述画面，不含人物外观，20~40字"}]}。'
               '6 件里只给 1~2 件 photo=true，要真的值得拍。'
               '要求：6 件各不相同，贴合这个角色，不要泛泛的“发呆/刷手机”，不要重复，不要写系统或AI。')
        user = (f"角色：{pr.get('name')}，{pr.get('gender')}，{pr.get('age')}岁；性格：{pr.get('personality')}；"
                f"工作：{pr.get('job')}（{pr.get('job_desc')}）；爱好：{pr.get('hobbies')}；喜欢：{pr.get('likes')}；"
                f"讨厌：{pr.get('dislikes')}；常吃：{pr.get('food')}；住处：{pr.get('home')}；习惯：{pr.get('habits')}。"
                f"今天是周{weekday}。{weather}\n人设补充：{persona}")
        events = []
        try:
            raw = await self.llm_complete(sys, user, max_tokens=650, temperature=0.95, timeout=60)
            m = re.search(r"\{.*\}", raw or "", re.S)
            if m:
                data = json.loads(m.group(0))
                events = data.get("events") or []
        except Exception as e:
            log.warning("事件包生成失败: %s", e)
        if events:
            with self.store._conn() as c:
                keep = []
                for e in events:
                    tx = str(e.get("text") or "").strip()[:120]
                    if not tx:
                        continue
                    dup = c.execute("SELECT 1 FROM world_events WHERE text LIKE ? LIMIT 1", (f"%{tx[:20]}%",)).fetchone()
                    if not dup:
                        keep.append(e)
                events = keep
        if not events:
            hobbies = (pr.get("hobbies") or "做饭、刷视频").split("、")[:3]
            job = pr.get("job") or "上班"
            events = [
                {"text": f"做{ hobbies[0] if hobbies else '饭'}的时候发现缺东西，只好凑合", "segment": "中午", "place": "家", "kind": "生活"},
                {"text": f"{job}那边临时来了点活，忙了一阵", "segment": "下午", "place": "任意", "kind": "工作"},
                {"text": "路上碰到个熟人，站着聊了半天", "segment": "下午", "place": "街上", "kind": "社交"},
                {"text": "刷到一个挺有意思的东西，看了好一会儿", "segment": "晚上", "place": "家", "kind": "兴趣"},
                {"text": "想找的东西找不到，翻了半天", "segment": "早上", "place": "家", "kind": "小意外"},
                {"text": "闻到楼下飘上来的饭味，突然就饿了", "segment": "下午", "place": "任意", "kind": "生活"},
            ]
        with self.store._conn() as c:
            c.execute("DELETE FROM world_event_pool WHERE day_index=?", (day,))
            for e in events[:8]:
                text = str(e.get("text") or "").strip()[:120]
                if not text:
                    continue
                c.execute("INSERT INTO world_event_pool(day_index,text,segment,place,kind,used,created_at,photo,photo_prompt) VALUES(?,?,?,?,?,0,?,?,?)",
                          (day, text, str(e.get("segment") or "任意")[:6], str(e.get("place") or "任意")[:6],
                           str(e.get("kind") or "生活")[:6], time.time(),
                           1 if e.get("photo") else 0, str(e.get("photo_prompt") or "")[:160]))
        log.info("生成事件包: 第%s天 %s 条", day, min(8, len(events)))

    def _pop_event(self, day: int, minutes: int, place: str) -> dict:
        h = minutes // 60
        seg = "早上" if h < 11 else ("中午" if h < 14 else ("下午" if h < 18 else "晚上"))
        with self.store._conn() as c:
            row = c.execute(
                "SELECT * FROM world_event_pool WHERE day_index=? AND used=0 AND (segment=? OR segment='任意') "
                "AND (place='任意' OR place=?) ORDER BY RANDOM() LIMIT 1",
                (day, seg, place)).fetchone()
            if not row:
                row = c.execute(
                    "SELECT * FROM world_event_pool WHERE day_index=? AND used=0 ORDER BY RANDOM() LIMIT 1",
                    (day,)).fetchone()
            if row:
                c.execute("UPDATE world_event_pool SET used=1 WHERE id=?", (row["id"],))
                return dict(row)
        return {}

    async def _maybe_greetings(self, day: int, minutes: int, rest_start: int, rest_end: int):
        try:
            import random as _r
            # 每天随机 0~15 分钟偏移：早安起床后，晚安入睡前
            if str(self.store.get_setting("greet_m_day", "")) != str(day):
                self.store.set_setting("greet_m_day", str(day))
                self.store.set_setting("greet_m_off", str(_r.randint(0, 15)))
            if str(self.store.get_setting("greet_n_day", "")) != str(day):
                self.store.set_setting("greet_n_day", str(day))
                self.store.set_setting("greet_n_off", str(_r.randint(0, 15)))
            try:
                moff = int(self.store.get_setting("greet_m_off", "0"))
                noff = int(self.store.get_setting("greet_n_off", "0"))
            except Exception:
                moff = noff = 0
            mt = (rest_end + moff) % 1440
            nt = (rest_start - noff) % 1440
            # 早安：起床后 0~15 分钟，只在起床后 3 小时内补发
            if str(self.store.get_setting("greet_morning_day", "")) != str(day):
                passed = (minutes >= mt) if (rest_end + 180 <= 1440) else (minutes >= mt)
                if passed and minutes <= ((rest_end + 180) % 1440 or 1440):
                    await self.world_greeting("morning")
            # 晚安：入睡前 0~15 分钟
            if str(self.store.get_setting("greet_night_day", "")) != str(day):
                if minutes >= nt and minutes <= ((rest_start + 30) % 1440 or 1440):
                    await self.world_greeting("night")
        except Exception as e:
            log.warning("问候调度失败: %s", e)

    async def maybe_live_photo(self, ev: dict, day: int, minutes: int):
        if not ev.get("photo") or self.store.get_setting("world_photo_enabled", "1") != "1":
            return
        owner = (self.store.get_setting("world_owner_qq", "") or "")
        if not owner:
            try:
                owner = str((self.super_admin_qqs() or [""])[0])
            except Exception:
                owner = ""
        if not owner:
            return
        if str(self.store.get_setting("photo_day", "")) != str(day):
            import random as _r
            self.store.set_setting("photo_day", str(day))
            try:
                _pmax = max(1, min(10, int(self.store.get_setting("world_photo_max", "3") or 3)))
            except Exception:
                _pmax = 3
            self.store.set_setting("photo_target", str(_r.randint(1, _pmax)))
            self.store.set_setting("photo_count", "0")
        try:
            target = int(self.store.get_setting("photo_target", "1"))
            count = int(self.store.get_setting("photo_count", "0"))
        except Exception:
            target, count = 1, 0
        if count >= target:
            return
        pr = self._profile()
        look = pr.get("appearance") or "黑色长发，深色眼睛，穿宽松卫衣"
        scene = ev.get("photo_prompt") or ev.get("text") or "日常生活"
        prompt = f"二次元动漫插画，日系清新风格，{look}，{scene}，自然光，干净线条，画面精致，不要文字水印"
        try:
            data = await self.generate_image(prompt, enhance=False, uid=owner, is_super=True)
            if not data:
                return
            import base64 as _b64
            await self.onebot_action("send_msg", {
                "message_type": "private", "user_id": str(owner),
                "message": [{"type": "text", "data": {"text": "给你看，刚拍的。"}},
                            {"type": "image", "data": {"file": "base64://" + _b64.b64encode(data).decode()}}]})
            self.store.set_setting("photo_count", str(count + 1))
            with self.store._conn() as c:
                c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                          (day, minutes, "photo", f"{self._world_clock_text(day, minutes)} 拍了张照片：{ev['text']}", time.time()))
            log.info("实况照片已发送: %s", ev["text"][:30])
        except Exception as e:
            log.warning("实况照片失败: %s", e)

    async def world_selfie(self, uid: str):
        if self.store.get_setting("world_photo_enabled", "1") != "1":
            await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(uid),
                "message": [{"type": "text", "data": {"text": "相册关着呢，先去后台打开实况照片。"}}]})
            return
        st = self.world_state() or {}
        day = st.get("day_index", 0)
        if str(self.store.get_setting("photo_day", "")) != str(day):
            import random as _r
            try:
                _pmax = max(1, min(10, int(self.store.get_setting("world_photo_max", "3") or 3)))
            except Exception:
                _pmax = 3
            self.store.set_setting("photo_day", str(day))
            self.store.set_setting("photo_target", str(_r.randint(1, _pmax)))
            self.store.set_setting("photo_count", "0")
        try:
            target = int(self.store.get_setting("photo_target", "1"))
            count = int(self.store.get_setting("photo_count", "0"))
        except Exception:
            target, count = 1, 0
        if count >= target:
            await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(uid),
                "message": [{"type": "text", "data": {"text": "今天拍够啦，明天再给你看。"}}]})
            return
        pr = self._profile()
        look = pr.get("appearance") or "黑色长发，深色眼睛，穿宽松卫衣"
        act = str(st.get("activity") or "待着")
        mood = str(st.get("mood") or "")
        energy = int(st.get("energy") or 0)
        weather_txt = ""
        try:
            raw = self.store.get_setting("weather_cache", "")
            if raw:
                w = json.loads(raw)
                bits = []
                if w.get("city"):
                    bits.append(str(w.get("city")))
                if w.get("rain"):
                    bits.append("外面在下雨")
                if w.get("haze"):
                    bits.append("有点雾霾")
                if w.get("temp") is not None:
                    bits.append(f"气温{w.get('temp')}度")
                weather_txt = "，".join(bits)
        except Exception:
            pass
        scene = f"{st.get('place','家')}，{act}"
        extras = []
        if mood:
            extras.append(f"心情{mood}")
        if weather_txt:
            extras.append(weather_txt)
        if energy and energy < 40:
            extras.append("看起来有点累")
        if "睡" in act or "赖床" in act:
            extras.append("刚被吵醒，头发有点乱")
        extra_txt = ("，".join(extras) + "，") if extras else ""
        prompt = (f"二次元动漫自拍，日系插画，{look}，{scene}，{extra_txt}"
                  "手持手机自拍的角度，自然光，干净线条，不要文字水印")
        try:
            data = await self.generate_image(prompt, enhance=False, uid=uid, is_super=True)
            if not data:
                await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(uid),
                    "message": [{"type": "text", "data": {"text": "没拍好，等我缓缓。"}}]})
                return
            import base64 as _b64
            await self.onebot_action("send_msg", {"message_type": "private", "user_id": str(uid),
                "message": [{"type": "text", "data": {"text": "喏，刚拍的。"}},
                            {"type": "image", "data": {"file": "base64://" + _b64.b64encode(data).decode()}}]})
            self.store.set_setting("photo_count", str(count + 1))
            with self.store._conn() as c:
                c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                          (st.get("day_index", 0), st.get("minutes", 0), "photo", "给超管发了张自拍", time.time()))
        except Exception as e:
            log.warning("自拍失败: %s", e)

    def past_events_note(self) -> str:
        try:
            st = self.world_state()
            if not st:
                return ""
            with self.store._conn() as c:
                rows = c.execute(
                    "SELECT text FROM world_events WHERE day_index BETWEEN ? AND ? AND kind IN ('life','social','proactive') "
                    "ORDER BY id DESC LIMIT 2", (st["day_index"] - 3, st["day_index"] - 1)).fetchall()
            if not rows:
                return ""
            return "\n你前几天经历过：" + "；".join(r["text"].split(" ", 1)[-1] for r in rows) + "。聊到相关话题可以自然提起，别硬背。"
        except Exception:
            return ""

    def weather_note(self, uid: str = "") -> str:
        try:
            raw = self.store.get_setting("weather_cache", "")
            if not raw:
                return ""
            w = json.loads(raw)
            if uid and hasattr(self, "is_super_admin") and not self.is_super_admin(str(uid)):
                return ""
            city = str(w.get("city") or "")
            district = str(w.get("district") or "")
            where = (city + district) or "你那边"
            facts = str(w.get("facts") or "")
            if facts:
                return f"\n{where}天气：{facts}。有人问你天气，就按这个说，别现编。"
            if w.get("rain"):
                return f"\n{where}今天有雨，出门要带伞。"
            return f"\n{where}今天没雨，气温 {w.get('temp')}℃。"
        except Exception:
            return ""

    async def world_greeting(self, kind: str):
        if self.store.get_setting("world_greetings", "1") != "1":
            return
        st = self.world_state()
        if not st:
            return
        day = st["day_index"]
        key = "greet_morning_day" if kind == "morning" else "greet_night_day"
        if str(self.store.get_setting(key, "")) == str(day):
            return
        text = "醒了，早。" if kind == "morning" else "困了，先睡，晚安。"
        if kind == "morning":
            try:
                w = await self.weather_data(force=True)
                facts = str(w.get("facts") or "")
                if facts:
                    polished = await self.llm_complete(
                        "你是生活助理。根据天气信息，用第一人称口语给用户发一条早安提醒，1~3 句，"
                        "包含：是否下雨/几点下、温度、穿衣建议、雾霾或大风等注意点。"
                        "不要列点、不要报数据清单、不要提“根据天气信息”。",
                        facts, max_tokens=160, temperature=0.7, timeout=30)
                    if polished and len(polished.strip()) >= 6:
                        text = "早。" + polished.strip()
                    else:
                        text = "早。" + facts
            except Exception as e:
                log.warning("早安天气润色失败: %s", e)
        qq = (self.store.get_setting("world_owner_qq", "") or "")
        if not qq:
            try:
                qq = str((self.super_admin_qqs() or [""])[0])
            except Exception:
                qq = ""
        if not qq:
            return
        try:
            await self.onebot_action("send_msg", {"message_type": "private", "user_id": qq,
                                                  "message": [{"type": "text", "data": {"text": text}}]})
            self.store.set_setting(key, str(day))
            log.info("作息问候 -> %s: %s", qq, text)
        except Exception as e:
            log.warning("作息问候发送失败: %s", e)

    def in_world_rest(self) -> bool:
        """世界是否处于休息时段且没被叫醒。"""
        try:
            st = self.world_state()
            if not st:
                return False
            rs = _hm(self.store.get_setting("world_rest_start", "22:00"), 22 * 60)
            re_ = _hm(self.store.get_setting("world_rest_end", "07:00"), 7 * 60)
            if not _in_window(st["minutes"], rs, re_):
                return False
            awake = bool(st.get("awake_activity")) and (
                st.get("awake_until_day", 0) > st["day_index"] or
                (st.get("awake_until_day", 0) == st["day_index"] and st.get("awake_until_minutes", 0) > st["minutes"]))
            return not awake
        except Exception:
            return False

    def world_wake(self, reason: str = "被吵醒") -> dict:
        st = self.world_state()
        if not st:
            return {}
        rest_start = _hm(self.store.get_setting("world_rest_start", "22:00"), 22 * 60)
        rest_end = _hm(self.store.get_setting("world_rest_end", "07:00"), 7 * 60)
        awake = bool(st.get("awake_activity")) and (
            st.get("awake_until_day", 0) > st["day_index"] or
            (st.get("awake_until_day", 0) == st["day_index"] and st.get("awake_until_minutes", 0) > st["minutes"]))
        if not _in_window(st["minutes"], rest_start, rest_end) and not awake:
            return st
        import random as _r
        choices = ["刷视频", "玩手机", "看小说", "翻来覆去", "坐着发呆"]
        new_act = (st.get("awake_activity") if awake and st.get("awake_activity") else _r.choice(choices))
        now_min = st["minutes"] + _r.randint(10, 20)
        now_day = st["day_index"]
        while now_min >= 1440:
            now_min -= 1440
            now_day += 1
        count = int(st.get("wake_count") or 0) if st.get("wake_day") == st["day_index"] else 0
        count += 1
        with self.store._conn() as c:
            c.execute("UPDATE world_state SET awake_activity=?,awake_until_day=?,awake_until_minutes=?,wake_day=?,wake_count=? WHERE id=1",
                      (new_act, now_day, now_min, st["day_index"], count))
            c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                      (st["day_index"], st["minutes"], "wake" if count == 1 else "wake_again",
                       f"{self._world_clock_text(st['day_index'], st['minutes'])} {reason}（今天第{count}次），起来{new_act}", time.time()))
        if count >= 3:
            self.world_emotion_adjust(anger=2, sad=1, joy=-1, stress=1)
            log.info("世界叫醒：今天第 %d 次被吵醒，情绪变差", count)
        else:
            log.info("世界叫醒：%s，%s，约 %d 分钟后继续睡", reason, new_act, 20)
        return self.world_state()

    @staticmethod
    def _world_clock_text(day: int, minutes: int) -> str:
        d = _dt.date(2026, 1, 1) + _dt.timedelta(days=day)
        return f"{d.month}月{d.day}日 周{WEEK[d.weekday()]} {minutes // 60:02d}:{minutes % 60:02d}"

    def world_context(self, uid: str = "", gid: str = "") -> str:
        if self.store.get_setting("world_enabled", "1") != "1":
            return ""
        st = self.world_state()
        if not st:
            return ""
        clock = self._world_clock_text(st["day_index"], st["minutes"])
        recent = self.world_recent_events(4)
        life = ""
        if recent:
            life = "\n你最近的生活：" + "；".join(e["text"].split(" ", 1)[-1] for e in reversed(recent)) + "。"
        needs = self.world_needs()
        diary = self.world_diary()
        extra = ""
        if diary:
            extra += "\n" + diary["text"]
        if needs["hunger"] > 70:
            extra += "\n你现在有点饿。"
        if needs["social"] > 75:
            extra += "\n你有点想找人说说话。"
        goals = self.world_goals()
        if goals:
            g = goals[0]
            extra += f"\n你在攒钱：{g['title']}，已攒 {g['progress']}/{g['target']}。"
        known = self.world_knowledge()
        if known:
            extra += "\n你最近听说：" + "；".join(f"{k['name']}说{k['text']}" for k in known[:2]) + "。"
        try:
            extra += self.past_events_note()
        except Exception:
            pass
        try:
            extra += self.promises_context(uid)
        except Exception:
            pass
        try:
            extra += self.weather_note(uid)
        except Exception:
            pass
        prof = self._profile()
        if prof.get("name"):
            extra += (f"\n你的身份：{prof.get('name')}，{prof.get('gender')}，{prof.get('age')}岁；"
                      f"工作：{prof.get('job')}（{prof.get('job_desc')}），工作时间 {prof.get('work_time')}，"
                      f"月工资 {prof.get('salary')} 元；当前余额 {self.world_money()} 元；"
                      f"喜欢：{prof.get('likes')}；讨厌：{prof.get('dislikes')}；常吃：{prof.get('food')}；"
                      f"口头禅：{prof.get('catchphrase')}。"
                      "有人问你的工作、工资、余额，就按这个回答，不要现编。")
        emo = self.world_emotion()
        tasks = self._tasks_context(uid)
        wake_note = ""
        if int(st.get("wake_count") or 0) >= 3 and st.get("wake_day") == st.get("day_index"):
            wake_note = "\n今天你已经被叫醒好几次了，有点烦，说话带点不耐烦。"
        rel = ""
        try:
            us = self.world_user_sentiment(uid) if uid else 0
            if us >= 8:
                rel += "\n你和这个人最近相处得不错，你对他比较有好感。"
            elif us <= -8:
                rel += "\n这个人最近对你不太客气，你心里有点介意。"
            gm = self.world_group_mood(gid) if gid else 0
            if gm <= -10:
                rel += "\n这个群最近对你不太友好，你在这个群里话会少一些。"
            elif gm >= 10:
                rel += "\n这个群对你挺友好的，你在这里比较放松。"
        except Exception:
            pass
        mood = self.world_mood_text()
        return (f"\n【你现在的生活】世界时间 {clock}。你人在{st['place']}，正在{st['activity']}，"
                f"精力{'充足' if st['energy'] > 70 else ('一般' if st['energy'] > 25 else '很差')}，心情{mood}。"
                f"（开心 {emo['joy']}、烦躁 {emo['anger']}、低落 {emo['sad']}、压力 {emo['stress']}）{life}{extra}{tasks}{rel}{wake_note}"
                f"\n聊到相关话题时，可以像真人一样提起你刚做过的事、正在忙什么；不要每句都汇报，也不要编造和你生活冲突的内容。"
                + ("\n你现在心情不太好，回复要比平时短，少解释，不要主动展开话题。" if emo["anger"] >= 60 or emo["sad"] >= 60 else ""))

    def world_check(self) -> list:
        issues = []
        st = self.world_state()
        if not st:
            return ["世界状态不存在"]
        if not (0 <= st["minutes"] < 1440):
            issues.append("世界时间不在 0~1439 分钟范围内")
        with self.store._conn() as c:
            bad = c.execute("SELECT COUNT(*) FROM world_events WHERE minutes<0 OR minutes>=1440").fetchone()[0]
            if bad:
                issues.append(f"有 {bad} 条事件时间越界")
            bad2 = c.execute("SELECT COUNT(*) FROM world_npcs WHERE last_met_day > ?", (st["day_index"],)).fetchone()[0]
            if bad2:
                issues.append(f"有 {bad2} 个 NPC 的相遇时间在未来")
            bad3 = c.execute("SELECT COUNT(*) FROM world_goals WHERE progress > target").fetchone()[0]
            if bad3:
                issues.append("目标进度超过目标值")
        money = self.world_money()
        if money < 0:
            issues.append("现金为负数")
        return issues

    def world_snapshot(self):
        st = self.world_state()
        with self.store._conn() as c:
            c.execute("INSERT INTO world_snapshots(day_index,minutes,state_json,created_at) VALUES(?,?,?,?)",
                      (st["day_index"], st["minutes"], json.dumps(st, ensure_ascii=False), time.time()))
            c.execute("DELETE FROM world_snapshots WHERE id NOT IN (SELECT id FROM world_snapshots ORDER BY id DESC LIMIT 48)")
        return st

    def world_snapshots(self, limit: int = 6) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id,day_index,minutes,created_at FROM world_snapshots ORDER BY id DESC LIMIT ?", (limit,))]

    def world_rollback(self, sid: int) -> bool:
        with self.store._conn() as c:
            row = c.execute("SELECT * FROM world_snapshots WHERE id=?", (sid,)).fetchone()
            if not row:
                return False
            st = json.loads(row["state_json"])
            c.execute("UPDATE world_state SET day_index=?,minutes=?,place=?,activity=?,energy=?,mood=?,updated_at=? WHERE id=1",
                      (st["day_index"], st["minutes"], st["place"], st["activity"], st["energy"], st["mood"], time.time()))
        return True

    def _world_proactive(self, old: dict, new: dict, npc_name: str = ""):
        if self.store.get_setting("world_proactive", "0") != "1":
            return
        owner = (self.store.get_setting("world_owner_qq", "") or "").strip()
        if not owner:
            try:
                qqs = self.super_admin_qqs() or []
                owner = str(qqs[0]) if qqs else ""
            except Exception:
                owner = ""
        if not owner:
            return
        today = new["day_index"]
        with self.store._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM world_events WHERE kind='proactive' AND day_index=?", (today,)).fetchone()[0]
            last = c.execute("SELECT minutes FROM world_events WHERE kind='proactive' AND day_index=? ORDER BY id DESC LIMIT 1",
                             (today,)).fetchone()
        # 拟人化：每天最多 3 条，间隔至少 90 分钟，同类 4 小时内不重复
        try:
            _max = max(0, min(20, int(self.store.get_setting("world_share_max", "3") or 3)))
        except Exception:
            _max = 3
        if _max <= 0 or n >= _max:
            return
        if last and new["day_index"] == today and (new["minutes"] - last["minutes"]) < 90:
            return
        with self.store._conn() as c:
            pend = c.execute("SELECT * FROM world_pending WHERE shared=0 AND day_index=? ORDER BY CASE kind "
                             "WHEN 'social' THEN 0 WHEN 'fact' THEN 1 ELSE 2 END, id LIMIT 1", (today,)).fetchone()
        if pend:
            emo = self.world_emotion()
            if pend["kind"] == "social":
                line = f"今天{pend['text']}，越想越气。" if emo["anger"] >= 60 else f"今天{pend['text']}，有点烦。"
            elif pend["kind"] == "fact":
                line = f"{pend['text']}，你说这是真的吗？"
            else:
                line = f"今天{pend['text']}，还挺开心的。" if emo["joy"] >= 65 else f"今天{pend['text']}。"
        elif old.get("activity") == new["activity"]:
            return
        elif new["place"] == "公司":
            line = "到公司了，开始干活。"
        elif new["activity"] in ("下班回家",):
            line = "下班了，往回走。"
        else:
            return
        with self.store._conn() as c:
            recent = [r["text"] for r in c.execute("SELECT text FROM world_events WHERE kind='proactive' ORDER BY id DESC LIMIT 12")]
        if any(line[:10] in r for r in recent):
            if pend:
                with self.store._conn() as c:
                    c.execute("UPDATE world_pending SET shared=1 WHERE id=?", (pend["id"],))
            return
        if pend:
            try:
                with self.store._conn() as c:
                    c.execute("UPDATE world_pending SET shared=1 WHERE id=?", (pend["id"],))
            except Exception:
                pass
        try:
            asyncio.get_running_loop().create_task(
                self.onebot_action("send_msg", {"message_type": "private", "user_id": owner, "message": line}))
            with self.store._conn() as c:
                c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                          (new["day_index"], new["minutes"], "proactive", f"主动消息：{line}", time.time()))
        except Exception as e:
            log.warning("世界主动消息失败: %s", e)

    def _world_card_inputs(self):
        # 保持签名包含工作与工资，改动后自动刷新身份卡
        try:
            persona = (self.persona_text() or "").strip()
        except Exception:
            persona = ""
        rest_s = self.store.get_setting("world_rest_start", "22:00")
        rest_e = self.store.get_setting("world_rest_end", "07:00")
        work_s = self.store.get_setting("world_work_start", "") or ""
        work_e = self.store.get_setting("world_work_end", "") or ""
        job = self.store.get_setting("world_job", "") or ""
        salary = self.store.get_setting("world_salary", "") or ""
        sig = f"{persona}|{rest_s}|{rest_e}|{work_s}|{work_e}|{job}|{salary}"
        shadow_hash = hashlib.sha256(sig.encode()).hexdigest()[:16]
        return persona, rest_s, rest_e, work_s, work_e, shadow_hash

    def _rule_card(self) -> str:
        import re as _re
        persona, rest_s, rest_e, work_s, work_e, _ = self._world_card_inputs()
        m = _re.search(r"[「『]([^」』]{1,12})[」』]", persona)
        name = m.group(1) if m else "肥鱼"
        work = f"{work_s}-{work_e}" if work_s and work_e else "没有固定工作"
        return (f"姓名：{name}\n身份：按人设生活的人\n作息：休息 {rest_s}-{rest_e}；工作 {work}\n"
                f"性格：由人设提示词决定，嘴硬心软、懒散但靠得住")

    def _profile(self) -> dict:
        with self.store._conn() as c:
            r = c.execute("SELECT * FROM world_profile WHERE id=1").fetchone()
        return dict(r) if r else {}

    def _rule_card(self) -> str:
        return ("【身份卡】\n姓名：未命名\n性别：未设置\n年龄：未设置\n性格：未设置\n"
                "爱好：未设置\n工作：未设置\n月工资：未设置\n余额：" + str(self.world_money()) + " 元")

    def _compose_card(self, pr: dict) -> str:
        def g(k, d="未设置"):
            v = pr.get(k)
            return str(v) if v not in (None, "", 0) else d
        lines = ["【身份卡】",
                 "姓名：" + g("name"),
                 "性别：" + g("gender"),
                 "年龄：" + (str(pr.get("age")) if pr.get("age") else "未设置"),
                 "性格：" + g("personality"),
                 "爱好：" + g("hobbies"),
                 "工作：" + g("job"),
                 "工作内容：" + g("job_desc"),
                 "工作时间：" + g("work_time"),
                 "月工资：" + (str(pr.get("salary")) + " 元" if pr.get("salary") else "未设置"),
                 "住处：" + g("home"),
                 "小习惯：" + g("habits"),
                 "喜欢：" + g("likes"),
                 "讨厌：" + g("dislikes"),
                 "常吃：" + g("food"),
                 "口头禅：" + g("catchphrase"),
                 "外观：" + g("appearance"),
                 "当前余额：" + str(self.world_money()) + " 元"]
        return "\n".join(lines)

    async def refresh_world_card(self, force: bool = False) -> str:
        persona, rest_s, rest_e, work_s, work_e, sig = self._world_card_inputs()
        pr = self._profile()
        if pr and not force and pr.get("settings_hash") == sig and pr.get("name"):
            return self._compose_card(pr)
        job_setting = (self.store.get_setting("world_job", "") or "").strip()
        try:
            salary_setting = int(self.store.get_setting("world_salary", "0") or 0)
        except Exception:
            salary_setting = 0
        sys = ("你是角色设定师。根据人设提示词与作息参数，生成一张拟人化身份卡，只输出 JSON："
               '{"name":"名字","gender":"男/女","age":整数,"personality":"性格一句话",'
               '"hobbies":["爱好1","爱好2","爱好3"],"job":"职业","job_desc":"工作内容一句话",'
               '"work_time":"如 09:00-18:00 或 自由职业","salary":整数,"home":"住在哪一句话","habits":"小习惯一句话","likes":"喜欢的东西一句话","dislikes":"讨厌的东西一句话","food":"常吃/爱吃的一句话","catchphrase":"偶尔会说的口头禅","appearance":"外观：发型发色、眼睛、常穿的衣服，一句话"}。'
               "要求：从人设提炼，不照抄原句；工作、工资、作息要和参数一致；"
               "不出现 AI、模型、系统、机器人等字眼。")
        user = (f"人设提示词：{persona[:600]}\n休息：{rest_s}-{rest_e}\n工作时段：{work_s or '无固定工作'}-{work_e or ''}\n"
                f"用户指定职业：{job_setting or '由你设定'}\n用户指定月工资：{salary_setting or '由你设定（4000~9000）'}")
        data = {}
        try:
            raw = await self.llm_complete(sys, user, max_tokens=360, temperature=0.7)
            m = re.search(r"\{.*\}", raw or "", re.S)
            if m:
                data = json.loads(m.group(0))
        except Exception as e:
            log.warning("身份卡生成失败: %s", e)
        if not data.get("name"):
            data = {"name": "小满", "gender": "女", "age": 23, "personality": "慢热，嘴硬心软",
                    "hobbies": ["做饭", "画画", "刷视频"], "job": job_setting or "自由职业",
                    "job_desc": "接一些零散的活", "work_time": "时间比较自由",
                    "salary": salary_setting or 5000, "home": "租的小单间", "habits": "熬夜，爱睡懒觉",
                    "likes": "猫、安静的地方", "dislikes": "吵闹、被催", "food": "可乐、麻辣烫", "catchphrase": "行吧", "appearance": "黑色长发，深色眼睛，常穿宽松卫衣和牛仔裤"}
        if job_setting:
            data["job"] = job_setting
        if salary_setting:
            data["salary"] = salary_setting
        hobbies = data.get("hobbies") or []
        if isinstance(hobbies, list):
            hobbies = "、".join(str(x) for x in hobbies[:5])
        rec = {"name": str(data.get("name"))[:20], "gender": str(data.get("gender"))[:4],
               "age": int(data.get("age") or 0) if str(data.get("age") or 0).isdigit() else 0,
               "personality": str(data.get("personality") or "")[:60],
               "hobbies": str(hobbies)[:80], "job": str(data.get("job") or "")[:30],
               "job_desc": str(data.get("job_desc") or "")[:80],
               "work_time": str(data.get("work_time") or "")[:40],
               "salary": int(data.get("salary") or 0) if str(data.get("salary") or 0).isdigit() else 0,
               "home": str(data.get("home") or "")[:60], "habits": str(data.get("habits") or "")[:60],
               "likes": str(data.get("likes") or "")[:60], "dislikes": str(data.get("dislikes") or "")[:60],
               "food": str(data.get("food") or "")[:60], "catchphrase": str(data.get("catchphrase") or "")[:30], "appearance": str(data.get("appearance") or "")[:100]}
        with self.store._conn() as c:
            c.execute("""INSERT OR REPLACE INTO world_profile
                (id,card,persona_hash,settings_hash,updated_at,name,gender,age,personality,hobbies,job,job_desc,work_time,salary,home,habits,likes,dislikes,food,catchphrase,appearance)
                VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      ("", "", sig, time.time(), rec["name"], rec["gender"], rec["age"], rec["personality"],
                       rec["hobbies"], rec["job"], rec["job_desc"], rec["work_time"], rec["salary"], rec["home"], rec["habits"],
                       rec["likes"], rec["dislikes"], rec["food"], rec["catchphrase"], rec["appearance"]))
        return self._compose_card(rec)

    def world_card(self) -> str:
        pr = self._profile()
        return self._compose_card(pr) if pr.get("name") else self._rule_card()

    TASK_HINTS = ("帮我", "带", "买", "拿", "取", "查", "提醒", "顺便", "替我", "记得", "回来")

    async def detect_task(self, uid: str, text: str, msg_id: str = ""):
        text = (text or "").strip()
        if not text or not any(k in text for k in self.TASK_HINTS):
            return None
        sys = ("判断用户是否在让对话对象做一件具体的事。是则输出 JSON："
               '{"task":true,"kind":"errand|check|remind","title":"不超过20字",'
               '"done_text":"完成后自然的一句话，如：可乐买好了。","minutes":整数}；'
               "否则输出 {\"task\":false}。只输出 JSON。")
        try:
            raw = await self.llm_complete(sys, text[:300], max_tokens=120, temperature=0.1)
        except Exception:
            return None
        import re as _re
        m = _re.search(r"\{.*\}", raw or "", _re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except Exception:
            return None
        if not d.get("task"):
            return None
        title = str(d.get("title") or text[:20])[:40]
        done_text = str(d.get("done_text") or "").strip()[:60]
        kind = d.get("kind") if d.get("kind") in ("errand", "check", "remind") else "errand"
        try:
            minutes = max(1, min(1440, int(d.get("minutes") or 20)))
        except Exception:
            minutes = 20
        st = self.world_state()
        due = st["minutes"] + minutes
        due_day = st["day_index"]
        while due >= 1440:
            due -= 1440
            due_day += 1
        with self.store._conn() as c:
            tid = c.execute("INSERT INTO world_tasks(user_qq,kind,title,status,due_day,due_minutes,created_at,source,done_text,msg_id)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (uid, kind, title, "doing", due_day, due, time.time(), text[:200], done_text, msg_id)).lastrowid
            c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                      (st["day_index"], st["minutes"], "task", f"答应了{uid}：{title}", time.time()))
        log.info("世界任务: %s 答应 %s %s，%d 分钟后完成", tid, uid, title, minutes)
        return tid

    async def detect_cancel(self, uid: str, text: str):
        t = (text or "").strip()
        if not any(k in t for k in ("不用了", "算了", "取消", "别买了", "不要了")):
            return
        rows = self.world_tasks(uid, active_only=True)
        if not rows:
            return
        with self.store._conn() as c:
            c.execute("UPDATE world_tasks SET status='cancelled',done_at=? WHERE id=?", (time.time(), rows[0]["id"]))

    def world_tasks(self, uid: str = "", active_only: bool = False) -> list:
        sql = "SELECT * FROM world_tasks"
        cond, args = [], []
        if uid:
            cond.append("user_qq=?")
            args.append(uid)
        if active_only:
            cond.append("status='doing'")
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY status='doing' DESC, due_day, due_minutes, id LIMIT 20"
        with self.store._conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def _tasks_context(self, uid: str) -> str:
        if not uid:
            return ""
        rows = self.world_tasks(uid, active_only=True)
        if not rows:
            return ""
        items = "；".join(f"{r['title']}（约 {r['due_minutes']//60:02d}:{r['due_minutes']%60:02d} 完成）" for r in rows[:3])
        return f"\n你答应了对方：{items}。如果对方问你在做什么，可以自然提到正在办这件事。"

    def _task_tick(self):
        st = self.world_state()
        if not st:
            return
        with self.store._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM world_tasks WHERE status='doing' AND (due_day<? OR (due_day=? AND due_minutes<=?)) "
                "ORDER BY due_day, due_minutes, id",
                (st["day_index"], st["day_index"], st["minutes"]))]
        for r in rows:
            if st["activity"] == "睡觉" and r["kind"] != "remind" and not r["deferred"]:
                rest_end = _hm(self.store.get_setting("world_rest_end", "07:00"), 7 * 60)
                due_day = st["day_index"] if rest_end > st["minutes"] else st["day_index"] + 1
                with self.store._conn() as c:
                    c.execute("UPDATE world_tasks SET due_day=?,due_minutes=?,deferred=1 WHERE id=?",
                              (due_day, min(1439, rest_end + 5), r["id"]))
                continue
            if st["activity"] == "睡觉" and r["kind"] != "remind":
                continue
            money = self.world_money()
            if r["kind"] == "errand" and money < 10:
                self.world_emotion_adjust(sad=3, stress=2)
                with self.store._conn() as c:
                    c.execute("UPDATE world_tasks SET status='failed',failed_reason=?,done_at=? WHERE id=?",
                              ("钱不够", time.time(), r["id"]))
                try:
                    asyncio.get_running_loop().create_task(self.onebot_action("send_msg", {
                        "message_type": "private", "user_id": str(r["user_qq"]),
                        "message": f"{r['title']}没办成，钱不太够。"}))
                except Exception:
                    pass
                continue
            with self.store._conn() as c:
                if r["kind"] == "errand":
                    c.execute("INSERT INTO world_ledger(day_index,minutes,amount,reason,created_at) VALUES(?,?,?,?,?)",
                              (st["day_index"], st["minutes"], -10, r["title"], time.time()))
                    c.execute("UPDATE world_state SET money=COALESCE(money,0)-10 WHERE id=1")
                c.execute("UPDATE world_tasks SET status='done',done_at=? WHERE id=?", (time.time(), r["id"]))
                c.execute("INSERT INTO world_events(day_index,minutes,kind,text,created_at) VALUES(?,?,?,?,?)",
                          (st["day_index"], st["minutes"], "task", f"完成了：{r['title']}", time.time()))
            self.world_emotion_adjust(joy=3, stress=-1)
            try:
                asyncio.get_running_loop().create_task(self._notify_task_done(r))
            except Exception:
                pass

    async def _notify_task_done(self, task: dict):
        try:
            if task["kind"] == "remind":
                line = f"提醒你一下：{task['title']}。"
            elif task["kind"] == "check":
                line = f"{task['title']}，我查过了，没查到特别靠谱的。"
            else:
                line = (task.get("done_text") or f"{task['title']}，弄好了。")
            try:
                self.emotion_apply(str(task["user_qq"]), joy=2, favor=2, reason="帮他办了件事")
            except Exception:
                pass
            await self.onebot_action("send_msg", {"message_type": "private",
                                                  "user_id": str(task["user_qq"]), "message": line})
        except Exception as e:
            log.warning("任务完成通知失败: %s", e)

    def cancel_task_by_msg(self, uid: str, msg_id: str) -> bool:
        if not msg_id:
            return False
        with self.store._conn() as c:
            row = c.execute("SELECT id FROM world_tasks WHERE user_qq=? AND msg_id=? AND status='doing'",
                            (str(uid), str(msg_id))).fetchone()
            if not row:
                return False
            c.execute("UPDATE world_tasks SET status='cancelled',done_at=? WHERE id=?", (time.time(), row["id"]))
        return True

    def world_pending(self, limit: int = 20) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM world_pending ORDER BY id DESC LIMIT ?", (limit,))]

    def world_history(self, limit: int = 24) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM world_history ORDER BY id DESC LIMIT ?", (limit,))]

    def world_events_for_day(self, day_index: int) -> list:
        with self.store._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT day_index,minutes,kind,text,created_at FROM world_events WHERE day_index=? ORDER BY minutes,id",
                (day_index,))]

    def world_event_days(self, limit: int = 60) -> list:
        with self.store._conn() as c:
            return [int(r[0]) for r in c.execute(
                "SELECT DISTINCT day_index FROM world_events ORDER BY day_index DESC LIMIT ?", (limit,))]

    def world_recent_events(self, limit: int = 40) -> list:
        with self.store._conn() as c:
            rows = c.execute("SELECT * FROM world_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out, last = [], None
        for r in rows:
            d = dict(r)
            if d["text"] == last:
                continue
            last = d["text"]
            out.append(d)
        return out

    async def api_world_events(self, request):
        self.require_super(request)
        try:
            day = int(request.query.get("day_index") or 0)
        except Exception:
            day = 0
        if not day:
            day = (self.world_state() or {}).get("day_index", 0)
        return aiohttp_web.json_response({"code": 0, "day_index": day,
                                          "events": self.world_events_for_day(day),
                                          "days": self.world_event_days()})

    async def api_world_state(self, request):
        self.require_super(request)
        st = self.world_state()
        st["clock"] = self._world_clock_text(st.get("day_index", 0), st.get("minutes", 0)) if st else ""
        st["enabled"] = self.store.get_setting("world_enabled", "1")
        st["context_preview"] = self.world_context("")
        st["rest_start"] = self.store.get_setting("world_rest_start", "22:00")
        st["rest_end"] = self.store.get_setting("world_rest_end", "07:00")
        st["work_start"] = self.store.get_setting("world_work_start", "")
        st["work_end"] = self.store.get_setting("world_work_end", "")
        try:
            st["card"] = await self.refresh_world_card()
        except Exception:
            st["card"] = self.world_card()
        st["awake"] = bool(st.get("awake_activity")) and (
            st.get("awake_until_day", 0) > st.get("day_index", 0) or
            (st.get("awake_until_day", 0) == st.get("day_index", 0) and st.get("awake_until_minutes", 0) > st.get("minutes", 0)))
        st["wake_count"] = int(st.get("wake_count") or 0)
        st["profile"] = self._profile()
        st["emotion"] = self.world_emotion()
        st["mood_text"] = self.world_mood_text()
        st["needs"] = self.world_needs()
        st["npcs"] = self.world_npcs()
        st["diary"] = self.world_diary()
        st["snapshots"] = self.world_snapshots()
        st["money"] = self.world_money()
        st["goals"] = self.world_goals()
        st["ledger"] = self.world_ledger()
        st["knowledge"] = self.world_knowledge()
        st["proactive"] = self.store.get_setting("world_proactive", "0")
        st["greetings"] = self.store.get_setting("world_greetings", "1")
        st["share_max"] = self.store.get_setting("world_share_max", "3")
        st["photo_enabled"] = self.store.get_setting("world_photo_enabled", "1")
        st["photo_max"] = self.store.get_setting("world_photo_max", "3")
        st["weather_loc_source"] = self.store.get_setting("weather_loc_source", "")
        st["weather_loc_saved_at"] = self.store.get_setting("weather_loc_saved_at", "")
        try:
            st["owner_qq"] = self.store.get_setting("world_owner_qq", "") or str((self.super_admin_qqs() or [""])[0])
        except Exception:
            st["owner_qq"] = self.store.get_setting("world_owner_qq", "")
        st["scale"] = self.store.get_setting("world_scale", "1")
        return aiohttp_web.json_response({"code": 0, "state": st,
                                          "events": self.world_events_for_day(st.get("day_index", 0)),
                                          "days": self.world_event_days(),
                                          "today": st.get("day_index", 0)})

    async def api_world_config(self, request):
        self.require_super(request)
        data = await request.json()
        if "enabled" in data:
            self.store.set_setting("world_enabled", "1" if data.get("enabled") else "0")
        if "proactive" in data:
            self.store.set_setting("world_proactive", "1" if data.get("proactive") else "0")
        if "photo_enabled" in data:
            self.store.set_setting("world_photo_enabled", "1" if data.get("photo_enabled") else "0")
        if "photo_max" in data:
            try:
                self.store.set_setting("world_photo_max", str(max(1, min(10, int(data.get("photo_max") or 3)))))
            except Exception:
                pass
        if "share_max" in data:
            try:
                self.store.set_setting("world_share_max", str(max(0, min(20, int(data.get("share_max") or 0)))))
            except Exception:
                pass
        if "greetings" in data:
            self.store.set_setting("world_greetings", "1" if data.get("greetings") else "0")
        if "job" in data:
            self.store.set_setting("world_job", str(data.get("job") or "")[:30])
        if "salary" in data:
            try:
                self.store.set_setting("world_salary", str(max(0, min(200000, int(data.get("salary") or 0)))))
            except Exception:
                pass
        if "job" in data or "salary" in data:
            try:
                asyncio.get_running_loop().create_task(self.refresh_world_card(force=True))
            except Exception:
                pass
        if "scale" in data or "rest_start" in data or "work_start" in data:
            return aiohttp_web.json_response({"code": -1, "message": "作息和倍率由系统统一安排，不能修改"})
        return aiohttp_web.json_response({"code": 0})

    async def api_world_trend(self, request):
        self.require_super(request)
        with self.store._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT day_index,minutes,joy,anger,sad,stress,energy,money,activity FROM world_history ORDER BY id DESC LIMIT 24")]
            rows = list(reversed(rows))
            for r in rows:
                ev = [x["text"] for x in c.execute(
                    "SELECT text FROM world_events WHERE day_index=? AND minutes>=? AND minutes<? ORDER BY id LIMIT 6",
                    (r["day_index"], r["minutes"], r["minutes"] + 60))]
                r["events"] = [x.split(" ", 1)[-1] for x in ev]
                if r["joy"] >= 70:
                    r["face"] = "😊"
                elif r["anger"] >= 60:
                    r["face"] = "😤"
                elif r["sad"] >= 60:
                    r["face"] = "😔"
                elif r["stress"] >= 60:
                    r["face"] = "😮💨"
                else:
                    r["face"] = "🙂"
        return aiohttp_web.json_response({"code": 0, "items": rows})

    def world_day_summary(self, day: int = -1) -> dict:
        st = self.world_state()
        if not st:
            return {"items": [], "money_delta": 0, "tasks_done": 0, "events": 0}
        if day < 0:
            day = st["day_index"]
        with self.store._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT minutes,activity,money FROM world_history WHERE day_index=? ORDER BY minutes", (day,))]
            tasks_done = c.execute("SELECT COUNT(*) FROM world_tasks WHERE status='done' AND due_day=?", (day,)).fetchone()[0]
            events = c.execute("SELECT COUNT(*) FROM world_events WHERE day_index=?", (day,)).fetchone()[0]
        cats = {}
        def cat(a):
            if "睡" in a or "失眠" in a or "赖床" in a:
                return "睡觉"
            if "上班" in a or "加班" in a or "接水" in a or "收拾东西" in a or "午休" in a or "刷手机休息" in a:
                return "工作"
            if "通勤" in a or "路上" in a or "咖啡" in a:
                return "通勤"
            if "做饭" in a or "吃" in a or "买菜" in a or "择菜" in a or "洗碗" in a:
                return "吃饭家务"
            if "家务" in a or "收拾" in a or "洗澡" in a or "晾" in a:
                return "吃饭家务"
            if "街" in a or "超市" in a or "散步" in a or "公园" in a or "电影" in a or "朋友" in a or "出去" in a:
                return "外出"
            return "休闲"
        for r in rows:
            k = cat(str(r["activity"] or ""))
            cats[k] = cats.get(k, 0) + 60
        total = sum(cats.values()) or 1
        items = [{"name": k, "minutes": v, "pct": round(v * 100 / total)} for k, v in sorted(cats.items(), key=lambda x: -x[1])]
        money_delta = (rows[-1]["money"] - rows[0]["money"]) if len(rows) >= 2 else 0
        return {"items": items, "money_delta": money_delta, "tasks_done": tasks_done, "events": events}

    async def api_weather_loc(self, request):
        self.require_super(request)
        d = await request.json()
        try:
            lat = float(d.get("lat")); lon = float(d.get("lon"))
        except Exception:
            return aiohttp_web.json_response({"code": -1, "message": "坐标不对"})
        self.store.set_setting("weather_lat", str(lat))
        self.store.set_setting("weather_lon", str(lon))
        self.store.set_setting("weather_updated", "0")
        self.store.set_setting("weather_loc_source", "manual")
        self.store.set_setting("weather_loc_saved_at", str(int(time.time())))
        self.store.set_setting("weather_admin_ip", "")
        city = district = ""
        try:
            async with self.http.get(
                f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&accept-language=zh",
                headers={"User-Agent": "FishPond/1.0"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                j = await r.json(content_type=None)
            addr = (j or {}).get("address") or {}
            city = addr.get("city") or addr.get("town") or addr.get("state") or ""
            district = addr.get("city_district") or addr.get("district") or addr.get("suburb") or addr.get("county") or ""
            self.store.set_setting("weather_city", str(city)[:40])
            self.store.set_setting("weather_district", str(district)[:40])
        except Exception as e:
            log.warning("反查区县失败: %s", e)
        w = await self.weather_data(force=True)
        return aiohttp_web.json_response({"code": 0, "weather": w, "city": city, "district": district, "saved": True})

    async def api_weather(self, request):
        self.require_super(request)
        force = request.query.get("refresh") == "1"
        return aiohttp_web.json_response({"code": 0, "weather": await self.weather_data(force=force)})

    async def api_world_summary(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({"code": 0, **self.world_day_summary()})

    async def api_world_tasks(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({"code": 0, "items": self.world_tasks()})

    async def api_world_check(self, request):
        self.require_super(request)
        return aiohttp_web.json_response({"code": 0, "issues": self.world_check()})

    async def start_world_loop(self):
        self._world_task = asyncio.get_running_loop().create_task(self.world_loop())
