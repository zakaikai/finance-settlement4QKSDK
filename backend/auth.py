"""Authentication module: password management and session tokens.

Uses bcrypt for password hashing (with SHA256 legacy support).
"""

import hashlib
import os
import secrets
import threading
from pathlib import Path

_CONFIG_PATH = None
_tokens: set[str] = set()
_token_lock = threading.Lock()
_attempts: dict[str, tuple[int, float]] = {}
_attempts_lock = threading.Lock()
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 30

# bcrypt is optional — falls back to SHA256-only if not installed
try:
    import bcrypt as _bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False


def _get_config_path() -> str:
    global _CONFIG_PATH
    if _CONFIG_PATH:
        return _CONFIG_PATH
    root = os.environ.get("FINANCE_ROOT", "")
    if root:
        _CONFIG_PATH = os.path.join(root, "config.env")
    else:
        _CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.env")
    return _CONFIG_PATH


def _read_hash() -> str:
    path = _get_config_path()
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("FINANCE_PASSWORD_HASH="):
                return line.split("=", 1)[1].strip()
    return ""


def _write_hash(hash_val: str) -> bool:
    path = _get_config_path()
    try:
        lines = []
        found = False
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()

        with open(path, "w", encoding="utf-8") as f:
            for line in lines:
                if line.strip().startswith("FINANCE_PASSWORD_HASH="):
                    f.write(f"FINANCE_PASSWORD_HASH={hash_val}\n")
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f"FINANCE_PASSWORD_HASH={hash_val}\n")
        return True
    except OSError:
        return False


def _is_bcrypt_hash(hash_val: str) -> bool:
    """Detect whether a stored hash is bcrypt ($2b$/$2a$/$2y$) or legacy SHA256."""
    return hash_val.startswith(("$2b$", "$2a$", "$2y$"))


def _hash_password_sha256(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _hash_password_bcrypt(password: str) -> str:
    """Hash password with bcrypt. Falls back to SHA256 if bcrypt is unavailable."""
    if _HAS_BCRYPT:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
    return _hash_password_sha256(password)


def is_password_set() -> bool:
    return bool(_read_hash())


def check_password(password: str) -> bool:
    if not is_password_set():
        return True  # no password set → allow
    stored = _read_hash()

    if _is_bcrypt_hash(stored):
        # bcrypt verification
        if not _HAS_BCRYPT:
            return False  # can't verify without bcrypt installed
        try:
            return _bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False

    # Legacy SHA256 verification
    return _hash_password_sha256(password) == stored


def set_password(password: str) -> bool:
    if len(password) < 4:
        return False
    return _write_hash(_hash_password_bcrypt(password))


def check_rate_limit(client_ip: str = "127.0.0.1") -> bool:
    import time
    now = time.time()
    with _attempts_lock:
        entry = _attempts.get(client_ip)
        if entry:
            count, first = entry
            if count >= MAX_ATTEMPTS and now - first < LOCKOUT_SECONDS:
                return False
            if now - first >= LOCKOUT_SECONDS:
                del _attempts[client_ip]
    return True


def record_failed_attempt(client_ip: str = "127.0.0.1"):
    import time
    now = time.time()
    with _attempts_lock:
        entry = _attempts.get(client_ip)
        if entry:
            count, first = entry
            if now - first > LOCKOUT_SECONDS:
                _attempts[client_ip] = (1, now)
            else:
                _attempts[client_ip] = (count + 1, first)
        else:
            _attempts[client_ip] = (1, now)


# ── LAN sharing config ──

def get_lan_enabled() -> bool:
    """Read LAN_ENABLED from config.env."""
    path = _get_config_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("LAN_ENABLED="):
                    return line.split("=", 1)[1].strip().lower() == "true"
    return False


def set_lan_enabled(enabled: bool) -> bool:
    """Persist LAN_ENABLED in config.env."""
    path = _get_config_path()
    try:
        lines = []
        found = False
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        with open(path, "w", encoding="utf-8") as f:
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("LAN_ENABLED="):
                    f.write(f"LAN_ENABLED={'true' if enabled else 'false'}\n")
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f"LAN_ENABLED={'true' if enabled else 'false'}\n")
        return True
    except OSError:
        return False


def get_lockout_remaining(client_ip: str = "127.0.0.1") -> int:
    import time
    with _attempts_lock:
        entry = _attempts.get(client_ip)
        if entry and entry[0] >= MAX_ATTEMPTS:
            remaining = int(LOCKOUT_SECONDS - (time.time() - entry[1]))
            return max(0, remaining)
    return 0


def create_token() -> str:
    token = secrets.token_hex(32)
    with _token_lock:
        _tokens.add(token)
    return token


def validate_token(token: str) -> bool:
    with _token_lock:
        return token in _tokens


def remove_token(token: str):
    with _token_lock:
        _tokens.discard(token)
