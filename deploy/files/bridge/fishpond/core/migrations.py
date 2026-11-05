"""数据库迁移：版本表 + 幂等迁移步骤。"""
import json
import logging
import sqlite3
import time

log = logging.getLogger("qqbridge")


def _ensure_version_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")


def _current(conn) -> int:
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return int(row[0] or 0)
    except Exception:
        return 0


def _v1_secrets(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS secrets (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at REAL
    )""")


def _ensure_crypto():
    try:
        import cryptography  # noqa: F401
        return True
    except Exception:
        pass
    import subprocess
    import sys

    def _pip_install():
        return subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                               "cryptography"], timeout=120, check=False)

    try:
        log.warning("缺少 cryptography，尝试自动安装到当前运行环境…")
        r = _pip_install()
        try:
            import cryptography  # noqa: F401
            log.info("cryptography 自动安装成功")
            return True
        except Exception:
            pass
        # venv 里可能没有 pip，先 ensurepip 再试一次
        log.warning("pip 安装未生效，尝试 ensurepip 后重试…")
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], timeout=120, check=False)
        _pip_install()
        import cryptography  # noqa: F401
        log.info("cryptography 自动安装成功（ensurepip）")
        return True
    except Exception as e:
        log.error("cryptography 自动安装失败，保留明文配置；可手动执行: %s -m pip install cryptography（原因: %s）",
                  sys.executable, e)
        return False


def _v2_config(conn, store):
    path = store.path.parent / "config.yaml"
    if not path.is_file():
        return
    if not _ensure_crypto():
        raise RuntimeError("cryptography 不可用")
    from fishpond.core.secretstore import encrypt, decrypt
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return
    enc = encrypt(text)
    if decrypt(enc) != text:
        raise RuntimeError("配置加密校验失败，保留 config.yaml")
    conn.execute("INSERT OR REPLACE INTO secrets(key,value,updated_at) VALUES(?,?,?)",
                 ("config_yaml", enc, time.time()))
    conn.commit()
    path.unlink()
    log.warning("配置已迁移到数据库加密存储，明文 config.yaml 已删除")


MIGRATIONS = [
    (1, _v1_secrets),
    (2, _v2_config),
]


def run_migrations(store):
    conn = sqlite3.connect(store.path)
    try:
        _ensure_version_table(conn)
        conn.commit()
        cur = _current(conn)
        for ver, fn in MIGRATIONS:
            if ver <= cur:
                continue
            try:
                if fn is _v2_config:
                    fn(conn, store)
                else:
                    fn(conn)
                conn.execute("INSERT OR REPLACE INTO schema_version(version,applied_at) VALUES(?,datetime('now','localtime'))", (ver,))
                conn.commit()
                log.info("数据库迁移完成: v%s", ver)
            except Exception as e:
                conn.rollback()
                log.error("数据库迁移 v%s 失败: %s", ver, e)
                raise
    finally:
        conn.close()


def read_encrypted_secret(db_path, key):
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT value FROM secrets WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None
