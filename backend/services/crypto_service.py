"""Backup encryption — AES-256-CBC with auto-key (machine-derived) or password (PBKDF2).

Interface:
  encrypt_backup(src, dst, password=None) → None
  decrypt_backup(src, dst, password=None) → bool
  detect_enc_type(path) → "auto" | "password" | "plain" | "unknown"

Format v2 (password-aware):
  [magic 4B "FSEB"] + [type 1B] + [salt 16B] + [IV 16B] + [encrypted data]
  type 0x01 = auto-key (machine-derived), salt = 16 zero bytes
  type 0x02 = password-key (PBKDF2-derived), salt = random 16 bytes
Legacy format: [IV 16B] + [encrypted data] (auto-key only)
"""
import os
import hashlib

_ENC_MAGIC = b"FSEB"
_ENC_TYPE_AUTO = 0x01
_ENC_TYPE_PASSWORD = 0x02
_SALT_LEN = 16
_IV_LEN = 16
_PBKDF2_ITERATIONS = 100_000
_ENCRYPTION_KEY: str | None = None


# ── Public interface ──


def encrypt_backup(src: str, dst: str, password: str | None = None) -> None:
    """Encrypt *src* file to *dst*. With password → PBKDF2; without → machine key."""
    with open(src, "rb") as f:
        data = f.read()

    if password:
        salt = os.urandom(_SALT_LEN)
        key = _derive_key(password, salt)
        enc_type = _ENC_TYPE_PASSWORD
    else:
        salt = b"\x00" * _SALT_LEN
        key = _machine_key().encode()
        enc_type = _ENC_TYPE_AUTO

    iv, ciphertext = _aes_encrypt(data, key)

    with open(dst, "wb") as f:
        f.write(_ENC_MAGIC)
        f.write(bytes([enc_type]))
        f.write(salt)
        f.write(iv)
        f.write(ciphertext)


def decrypt_backup(src: str, dst: str, password: str | None = None) -> bool:
    """Decrypt *src* to *dst*. Returns False on wrong password or key mismatch.

    Auto-detects v2 (magic header) vs legacy (no header) format.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding

    with open(src, "rb") as f:
        data = f.read()

    if data[:4] == _ENC_MAGIC:
        enc_type = data[4]
        salt = data[5:5 + _SALT_LEN]
        iv = data[5 + _SALT_LEN:5 + _SALT_LEN + _IV_LEN]
        ciphertext = data[5 + _SALT_LEN + _IV_LEN:]

        if enc_type == _ENC_TYPE_PASSWORD:
            if not password:
                return False
            key = _derive_key(password, salt)
        else:
            key = _machine_key().encode()
    else:
        iv = data[:_IV_LEN]
        ciphertext = data[_IV_LEN:]
        key = _machine_key().encode()

    try:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
    except (ValueError, Exception):
        return False

    with open(dst, "wb") as f:
        f.write(plaintext)
    return True


def detect_enc_type(path: str) -> str:
    """Return 'auto', 'password', 'plain', or 'unknown'."""
    if not path.endswith(".enc.db"):
        return "plain"
    try:
        with open(path, "rb") as f:
            head = f.read(5)
        if head[:4] == _ENC_MAGIC:
            if head[4] == _ENC_TYPE_PASSWORD:
                return "password"
            return "auto"
        return "auto"
    except OSError:
        return "unknown"


# ── Internals ──


def _aes_encrypt(data: bytes, key: bytes) -> tuple[bytes, bytes]:
    """AES-256-CBC encrypt → (iv, ciphertext)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding

    iv = os.urandom(_IV_LEN)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return iv, encryptor.update(padded) + encryptor.finalize()


def _machine_key() -> str:
    """Machine-derived encryption key, cached after first call."""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY:
        return _ENCRYPTION_KEY
    key = os.environ.get("BACKUP_ENCRYPTION_KEY", "")
    if not key:
        machine = os.environ.get("COMPUTERNAME", "unknown")
        # Walk up two dirs from this file to reach project root
        app_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        key = hashlib.sha256(f"{machine}:{app_root}".encode()).hexdigest()
    _ENCRYPTION_KEY = key[:32]
    return _ENCRYPTION_KEY


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive 32-byte AES key from password via PBKDF2-HMAC-SHA256."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_PBKDF2_ITERATIONS)
    return kdf.derive(password.encode("utf-8"))
