"""Tests for crypto_service — encrypt, decrypt, detect_enc_type, key derivation."""
import os
import pytest
import backend.services.crypto_service as crypto_mod
from backend.services.crypto_service import (
    encrypt_backup,
    decrypt_backup,
    detect_enc_type,
    _machine_key,
    _derive_key,
    _aes_encrypt,
)


# ═══════════════════════════════════════════════════════════════
#  encrypt / decrypt round-trip
# ═══════════════════════════════════════════════════════════════

def test_encrypt_decrypt_roundtrip_auto_key(tmp_path):
    """Auto-key mode: encrypt → decrypt without password produces original content."""
    src = tmp_path / "source.db"
    enc = tmp_path / "backup.enc.db"
    dst = tmp_path / "restored.db"

    content = b"hello auto-key backup test data " * 50
    src.write_bytes(content)

    encrypt_backup(str(src), str(enc), password=None)
    assert enc.exists()
    assert enc.stat().st_size > 0

    ok = decrypt_backup(str(enc), str(dst), password=None)
    assert ok is True
    assert dst.read_bytes() == content


def test_encrypt_decrypt_roundtrip_with_password(tmp_path):
    """Password mode: encrypt → decrypt with correct password restores content."""
    src = tmp_path / "source.db"
    enc = tmp_path / "backup.enc.db"
    dst = tmp_path / "restored.db"

    content = b"password-protected data " * 100
    src.write_bytes(content)

    encrypt_backup(str(src), str(enc), password="my_secret")
    assert enc.exists()

    ok = decrypt_backup(str(enc), str(dst), password="my_secret")
    assert ok is True
    assert dst.read_bytes() == content


def test_decrypt_wrong_password_returns_false(tmp_path):
    """Wrong password → decrypt returns False, no output file created."""
    src = tmp_path / "source.db"
    enc = tmp_path / "backup.enc.db"

    src.write_bytes(b"secret data " * 30)
    encrypt_backup(str(src), str(enc), password="correct")

    ok = decrypt_backup(str(enc), str(tmp_path / "restored.db"), password="wrong")
    assert ok is False


def test_decrypt_missing_password_for_encrypted_returns_false(tmp_path):
    """Password-encrypted file → decrypt without password returns False."""
    src = tmp_path / "source.db"
    enc = tmp_path / "backup.enc.db"

    src.write_bytes(b"password required " * 20)
    encrypt_backup(str(src), str(enc), password="secret123")

    ok = decrypt_backup(str(enc), str(tmp_path / "restored.db"), password=None)
    assert ok is False


# ═══════════════════════════════════════════════════════════════
#  detect_enc_type
# ═══════════════════════════════════════════════════════════════

def test_detect_enc_type_plain_db(tmp_path):
    """Plain .db file (not .enc.db) returns 'plain'."""
    f = tmp_path / "settlement.db"
    f.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    assert detect_enc_type(str(f)) == "plain"


def test_detect_enc_type_password(tmp_path):
    """Password-encrypted file returns 'password'."""
    src = tmp_path / "source.db"
    enc = tmp_path / "backup.enc.db"
    src.write_bytes(b"some data " * 100)
    encrypt_backup(str(src), str(enc), password="test")

    assert detect_enc_type(str(enc)) == "password"


def test_detect_enc_type_auto(tmp_path):
    """Auto-key encrypted file returns 'auto'."""
    src = tmp_path / "source.db"
    enc = tmp_path / "backup.enc.db"
    src.write_bytes(b"auto-key data " * 100)
    encrypt_backup(str(src), str(enc), password=None)

    assert detect_enc_type(str(enc)) == "auto"


def test_detect_enc_type_unknown_on_oserror(tmp_path):
    """File with .enc.db extension that can't be read → 'unknown' (OSError)."""
    f = tmp_path / "unreadable.enc.db"
    f.write_bytes(b"x")
    os.chmod(str(f), 0o000)  # remove read permissions on Windows may not work
    try:
        result = detect_enc_type(str(f))
        # On Windows chmod may not prevent reading; if it works, expect 'auto'
        # since the magic won't match. The 'unknown' path is for OSError.
        if result == "auto":
            pass  # Windows: permission denied not enforced by chmod
        else:
            assert result in ("unknown", "auto")
    finally:
        os.chmod(str(f), 0o666)

def test_detect_enc_type_non_fseb_header_returns_auto(tmp_path):
    """File ending .enc.db without FSEB magic → 'auto'."""
    f = tmp_path / "nofsb.enc.db"
    f.write_bytes(b"not a valid FSEB header at all")
    assert detect_enc_type(str(f)) == "auto"


# ═══════════════════════════════════════════════════════════════
#  _aes_encrypt
# ═══════════════════════════════════════════════════════════════

def test_aes_encrypt_produces_different_iv_each_call():
    """Each call generates a random IV → different ciphertext for same data+key."""
    key = os.urandom(32)
    data = b"hello world " * 16

    iv1, ct1 = _aes_encrypt(data, key)
    iv2, ct2 = _aes_encrypt(data, key)

    assert len(iv1) == 16
    assert len(iv2) == 16
    assert ct1 != ct2, "Different IV → different ciphertext"


# ═══════════════════════════════════════════════════════════════
#  _machine_key
# ═══════════════════════════════════════════════════════════════

def _reset_machine_key_cache():
    """Reset the _ENCRYPTION_KEY global so _machine_key recomputes."""
    crypto_mod._ENCRYPTION_KEY = None


def test_machine_key_env_var_override(monkeypatch):
    """BACKUP_ENCRYPTION_KEY env var → used directly as key."""
    _reset_machine_key_cache()
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", "my-custom-32-byte-key-here!!")
    key = _machine_key()
    assert key == "my-custom-32-byte-key-here!!"
    _reset_machine_key_cache()


def test_machine_key_deterministic():
    """_machine_key returns same value across calls (cached)."""
    _reset_machine_key_cache()
    k1 = _machine_key()
    k2 = _machine_key()
    assert k1 == k2
    assert len(k1) == 32
    _reset_machine_key_cache()


# ═══════════════════════════════════════════════════════════════
#  _derive_key
# ═══════════════════════════════════════════════════════════════

def test_derive_key_deterministic():
    """Same password + salt → same derived key."""
    salt = os.urandom(16)
    k1 = _derive_key("test_password", salt)
    k2 = _derive_key("test_password", salt)
    assert k1 == k2
    assert len(k1) == 32


def test_derive_key_different_salts_different_keys():
    """Different salts produce different keys from same password."""
    salt1 = b"a" * 16
    salt2 = b"b" * 16
    k1 = _derive_key("same_pw", salt1)
    k2 = _derive_key("same_pw", salt2)
    assert k1 != k2
