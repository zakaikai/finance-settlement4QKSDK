"""Tests for auth module: password, tokens, rate limiting."""
import os
import time
from backend import auth


def setup_function():
    """Reset auth state before each test."""
    auth._attempts.clear()
    # Point config to a temp file so tests don't interfere
    auth._CONFIG_PATH = os.path.join(os.environ.get("TEMP", "/tmp"), "_test_auth.env")
    if os.path.exists(auth._CONFIG_PATH):
        os.remove(auth._CONFIG_PATH)


def teardown_function():
    p = auth._CONFIG_PATH
    if p and os.path.exists(p):
        os.remove(p)


def _reset_attempts():
    auth._attempts.clear()


def test_password_set_and_check():
    """set_password 后 check_password 能正确验证。"""
    auth.set_password("test1234")
    assert auth.is_password_set()
    assert auth.check_password("test1234")
    assert not auth.check_password("wrong")


def test_password_min_length():
    """密码长度不能少于4位。"""
    assert not auth.set_password("ab")


def test_check_password_no_password_set():
    """未设密码时 check_password 返回 True（允许访问）。"""
    assert not auth.is_password_set()
    assert auth.check_password("anything")


def test_create_and_validate_token():
    """create_token 返回有效 token，validate_token 能验证。"""
    token = auth.create_token()
    assert len(token) == 64  # 32 bytes hex
    assert auth.validate_token(token)


def test_remove_token():
    """remove_token 后 token 失效。"""
    token = auth.create_token()
    auth.remove_token(token)
    assert not auth.validate_token(token)


def test_remove_token_unknown():
    """删除不存在的 token 不报错。"""
    auth.remove_token("nonexistent_token")  # should not raise


def test_rate_limit_allows_initial():
    """未超过限制时 check_rate_limit 返回 True。"""
    _reset_attempts()
    assert auth.check_rate_limit("test_client")


def test_rate_limit_blocks_after_max_attempts():
    """超过最大尝试次数后 check_rate_limit 返回 False。"""
    _reset_attempts()
    ip = "test_block"
    for _ in range(auth.MAX_ATTEMPTS):
        auth.record_failed_attempt(ip)
    assert not auth.check_rate_limit(ip)


def test_rate_limit_resets_after_lockout():
    """锁定时间过后 check_rate_limit 恢复 True。"""
    _reset_attempts()
    ip = "test_reset"
    for _ in range(auth.MAX_ATTEMPTS):
        auth.record_failed_attempt(ip)
    # Force lockout expiry
    auth._attempts[ip] = (auth.MAX_ATTEMPTS, time.time() - auth.LOCKOUT_SECONDS - 1)
    assert auth.check_rate_limit(ip)


def test_get_lockout_remaining():
    """get_lockout_remaining 返回剩余锁定秒数。"""
    _reset_attempts()
    ip = "test_remaining"
    for _ in range(auth.MAX_ATTEMPTS):
        auth.record_failed_attempt(ip)
    remaining = auth.get_lockout_remaining(ip)
    assert 0 < remaining <= auth.LOCKOUT_SECONDS


def test_get_lockout_remaining_no_lockout():
    """未锁定时 get_lockout_remaining 返回 0。"""
    _reset_attempts()
    assert auth.get_lockout_remaining("no_lock") == 0


def test_distinct_ips_independent():
    """不同 IP 的失败计数互不影响。"""
    _reset_attempts()
    for _ in range(auth.MAX_ATTEMPTS):
        auth.record_failed_attempt("evil_ip")
    assert auth.check_rate_limit("good_ip")
    assert not auth.check_rate_limit("evil_ip")
