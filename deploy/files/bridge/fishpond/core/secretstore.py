"""敏感数据加密存储：AES-GCM + 本机密钥文件。"""
import base64
import logging
import os
import pathlib
import secrets as _secrets

log = logging.getLogger("qqbridge")

_KEY_CACHE = None


def _candidates():
    env = os.environ.get("FISHPOND_SECRET_FILE")
    out = []
    if env:
        out.append(pathlib.Path(env))
    out.append(pathlib.Path("/etc/fishpond/secret.key"))
    out.append(pathlib.Path(__file__).resolve().parents[2] / "secret.key")
    return out


def load_key(create: bool = True) -> bytes:
    global _KEY_CACHE
    if _KEY_CACHE:
        return _KEY_CACHE
    for p in _candidates():
        try:
            if p.is_file():
                raw = p.read_bytes().strip()
                if len(raw) == 32:
                    _KEY_CACHE = raw
                    return raw
                try:
                    decoded = base64.urlsafe_b64decode(raw)
                    if len(decoded) == 32:
                        _KEY_CACHE = decoded
                        return decoded
                except Exception:
                    pass
                log.warning("密钥文件长度异常: %s（应为 32 字节）", p)
        except Exception as e:
            log.warning("读取密钥失败 %s: %s", p, e)
    if not create:
        raise RuntimeError("未找到加密密钥文件")
    p = _candidates()[1]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        key = _secrets.token_bytes(32)
        p.write_bytes(key)
        os.chmod(p, 0o600)
        _KEY_CACHE = key
        log.warning("已生成加密密钥: %s（请备份，丢失将无法解密敏感数据）", p)
        return key
    except Exception as e:
        raise RuntimeError(f"无法创建密钥文件 {p}: {e}")


def encrypt(text: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = load_key()
    nonce = _secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, str(text).encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt(token: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(load_key()).decrypt(nonce, ct, None).decode("utf-8")
