"""Tests for system management: backup, restore, status, reset, patches, logs."""
import os
import sqlite3
import tempfile
import pytest
from backend.database import DB_PATH, BACKUP_DIR, DatabaseManager
from backend.services.crypto_service import decrypt_backup, detect_enc_type


def _patch_paths(tmp_path):
    """Monkeypatch DB_PATH/BACKUP_DIR to temp paths; return (orig_db, orig_bu)."""
    import backend.database as db_mod
    db_file = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    orig = (db_mod.DB_PATH, db_mod.BACKUP_DIR, db_mod.engine, db_mod.async_session)
    db_mod.DB_PATH = str(db_file)
    db_mod.BACKUP_DIR = str(backup_dir)
    return orig, db_file, backup_dir


def _restore_paths(orig):
    import backend.database as db_mod
    db_mod.DB_PATH = orig[0]
    db_mod.BACKUP_DIR = orig[1]
    db_mod.engine = orig[2]
    db_mod.async_session = orig[3]


def test_backup_creates_file(tmp_path):
    """创建备份会在备份目录生成文件，且 list_backups 能查到。"""
    orig, _db_file, backup_dir = _patch_paths(tmp_path)
    try:
        _db_file.write_text("")
        result = DatabaseManager.create_backup()
        assert os.path.exists(result["backup_path"])
        assert "size_display" in result
        assert backup_dir.samefile(os.path.dirname(result["backup_path"]))

        backups = DatabaseManager.list_backups()
        assert len(backups) == 1
        assert backups[0]["path"] == result["backup_path"]
    finally:
        _restore_paths(orig)


@pytest.mark.asyncio
async def test_restore_replaces_db_content(tmp_path):
    """从备份恢复后，数据库文件内容与备份一致。"""
    orig, db_file, _backup_dir = _patch_paths(tmp_path)
    try:
        # Create a SQLite DB with a table and data
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        conn.commit()
        conn.close()

        # Backup it
        bk = DatabaseManager.create_backup()

        # Modify original
        conn = sqlite3.connect(str(db_file))
        conn.execute("INSERT INTO t VALUES (99)")
        conn.commit()
        conn.close()

        # Verify modified
        conn = sqlite3.connect(str(db_file))
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2
        conn.close()

        # Restore from backup
        await DatabaseManager.restore_backup(bk["backup_path"])

        # Verify restored to original state
        conn = sqlite3.connect(str(db_file))
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
        assert conn.execute("SELECT v FROM t").fetchone()[0] == 42
        conn.close()
    finally:
        _restore_paths(orig)


@pytest.mark.asyncio
async def test_status_returns_table_counts(tmp_path):
    """status 返回信息含表计数，且表计数为 dict。"""
    orig, db_file, _backup_dir = _patch_paths(tmp_path)
    try:
        # Create a proper SQLite DB with schema
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from backend.database import Base
        from backend import models  # ensure all models registered on metadata

        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

        status = DatabaseManager.get_status()
        assert status["exists"] is True
        assert status["size_bytes"] > 0
        assert "size_display" in status
        assert "db_path" in status

        counts = await DatabaseManager.get_table_counts()
        assert isinstance(counts, dict)
        assert "raw_settlements" in counts
    finally:
        _restore_paths(orig)


@pytest.mark.asyncio
async def test_reset_clears_all_data(tmp_path):
    """reset 后所有表记录数为 0，且备份先被创建。"""
    orig, db_file, backup_dir = _patch_paths(tmp_path)
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from backend.database import Base
        from backend import models

        # Create a temp engine + session for this test DB
        test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        test_async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Insert some data
        async with test_async_session() as s:
            s.add(models.Game(game_id="G001", game_name="Test", discount_rate=1))
            await s.commit()

        # Patch engine + async_session on the module so DatabaseManager uses them
        import backend.database as db_mod
        db_mod.engine = test_engine
        db_mod.async_session = test_async_session

        result = await DatabaseManager.reset_database()
        assert result["success"] is True
        assert os.path.exists(result["backup"]["backup_path"])

        # Verify tables are empty using get_table_counts
        counts = await DatabaseManager.get_table_counts()
        for name, cnt in counts.items():
            assert cnt == 0, f"{name} should be 0, got {cnt}"
    finally:
        await test_engine.dispose()
        _restore_paths(orig)


@pytest.mark.asyncio
async def test_audit_log_query_via_api(db_session):
    """GET /api/system/logs 返回审计日志。"""
    from backend import models
    from backend.database import get_db
    from backend.main import app
    from fastapi.testclient import TestClient
    from datetime import datetime

    # Insert a log entry directly
    log = models.AuditLog(
        action="backup", detail="测试备份", user="tester",
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db_session.add(log)
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/system/logs?limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) >= 1
        assert body["data"][0]["action"] == "backup"
        assert body["data"][0]["detail"] == "测试备份"
        assert body["total"] >= 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_audit_log_empty_when_no_logs(db_session):
    """GET /api/system/logs 无日志时返回空数组。"""
    from backend.database import get_db
    from backend.main import app
    from fastapi.testclient import TestClient

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/system/logs?limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["total"] == 0
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────
# Slice A: create_backup with password encryption
# ──────────────────────────────────────────────────────

def test_backup_with_password_encryption(tmp_path):
    """create_backup(password=…) produces a password-encrypted backup
    that can be decrypted with the same password."""
    orig, db_file, _backup_dir = _patch_paths(tmp_path)
    try:
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        conn.commit()
        conn.close()

        pwd = "test123"
        result = DatabaseManager.create_backup(password=pwd)

        assert os.path.exists(result["backup_path"]), "backup file must exist"
        assert result["encrypted"] is True
        assert result["enc_type"] == "password", (
            f"expected 'password', got {result['enc_type']!r}"
        )

        # Decrypt and verify content
        tmp_out = tmp_path / "restored.db"
        ok = decrypt_backup(result["backup_path"], str(tmp_out), password=pwd)
        assert ok, "decrypt with correct password must succeed"

        conn2 = sqlite3.connect(str(tmp_out))
        assert conn2.execute("SELECT v FROM t").fetchone()[0] == 42
        conn2.close()

        # Wrong password must fail
        ok_bad = decrypt_backup(result["backup_path"], str(tmp_out), password="wrong")
        assert not ok_bad, "wrong password must not decrypt"
    finally:
        _restore_paths(orig)


def test_backup_without_password_uses_auto_key(tmp_path):
    """create_backup() without password produces an auto-key encrypted backup."""
    orig, db_file, _backup_dir = _patch_paths(tmp_path)
    try:
        db_file.write_text("")

        result = DatabaseManager.create_backup()

        assert os.path.exists(result["backup_path"])
        assert result["encrypted"] is True
        assert result["enc_type"] == "auto", (
            f"expected 'auto', got {result['enc_type']!r}"
        )

        tmp_out = tmp_path / "restored_auto.db"
        ok = decrypt_backup(result["backup_path"], str(tmp_out))
        assert ok, "auto-key backup must decrypt without password"
    finally:
        _restore_paths(orig)


# ──────────────────────────────────────────────────────
# Slice B: reset_database with password backup
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_with_password_creates_password_backup(tmp_path):
    """reset_database(password=…) creates a password-encrypted backup
    before clearing all tables."""
    orig, db_file, backup_dir = _patch_paths(tmp_path)
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from backend.database import Base
        from backend import models

        test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Insert seed data
        async with test_session() as s:
            s.add(models.Game(game_id="G001", game_name="Test Game", discount_rate=1))
            await s.commit()

        # Patch engine on the module so DatabaseManager uses test DB
        import backend.database as db_mod
        db_mod.engine = test_engine
        db_mod.async_session = test_session

        pwd = "secret42"
        result = await DatabaseManager.reset_database(password=pwd)

        assert result["success"] is True
        assert result["was_empty"] is False, "DB had data, was_empty should be False"

        bk = result["backup"]
        assert bk is not None, "backup must be created"
        assert os.path.exists(bk["backup_path"])
        assert bk["enc_type"] == "password", (
            f"expected password enc, got {bk['enc_type']!r}"
        )

        # Verify backup decryptable with password
        tmp_out = tmp_path / "verify_restore.db"
        ok = decrypt_backup(bk["backup_path"], str(tmp_out), password=pwd)
        assert ok, "password backup must decrypt"
        conn = sqlite3.connect(str(tmp_out))
        assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
        conn.close()

        # After reset, live DB must be empty
        counts = await DatabaseManager.get_table_counts()
        for name, cnt in counts.items():
            assert cnt == 0, f"{name} should be 0 after reset, got {cnt}"
    finally:
        await test_engine.dispose()
        _restore_paths(orig)


# ──────────────────────────────────────────────────────
# Slice C: reset on already-empty DB skips backup
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_on_empty_db_skips_backup(tmp_path):
    """reset_database() on a DB with no games skips creating a backup
    and returns was_empty=True."""
    orig, db_file, backup_dir = _patch_paths(tmp_path)
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from backend.database import Base
        from backend import models

        test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        # Create empty schema — no data inserted
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import backend.database as db_mod
        db_mod.engine = test_engine
        db_mod.async_session = test_session

        result = await DatabaseManager.reset_database()

        assert result["success"] is True
        assert result["was_empty"] is True, (
            f"DB had no data, was_empty should be True, got {result['was_empty']}"
        )
        assert result["backup"] is None, (
            "backup should be None when DB is already empty"
        )

        # DB should still be empty after reset
        counts = await DatabaseManager.get_table_counts()
        for name, cnt in counts.items():
            assert cnt == 0, f"{name} should be 0, got {cnt}"
    finally:
        await test_engine.dispose()
        _restore_paths(orig)


# ──────────────────────────────────────────────────────
# Slice D: restore_backup rejects empty settlement backup
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restore_rejects_empty_settlement_backup(tmp_path):
    """restore_backup() raises RuntimeError when the backup file
    contains a games table with zero rows (indicating it was
    created from an already-reset database)."""
    orig, db_file, _backup_dir = _patch_paths(tmp_path)
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from backend.database import Base
        from backend import models

        test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        # Create full settlement schema with games table (but empty)
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create a backup of the empty schema
        empty_bk = DatabaseManager.create_backup()
        assert os.path.exists(empty_bk["backup_path"])

        # Restoring this empty backup must raise RuntimeError
        with pytest.raises(RuntimeError, match="games 表为空"):
            await DatabaseManager.restore_backup(empty_bk["backup_path"])
    finally:
        await test_engine.dispose()
        _restore_paths(orig)


# ──────────────────────────────────────────────────────
# Slice E: create_backup uses PASSIVE checkpoint, not VACUUM
# ──────────────────────────────────────────────────────

def test_backup_uses_passive_checkpoint_not_vacuum(tmp_path):
    """create_backup() must use PRAGMA wal_checkpoint(PASSIVE)
    and must NOT call VACUUM (which can corrupt the DB on Windows)."""
    from unittest.mock import patch
    import backend.database as db_mod

    orig, db_file, _backup_dir = _patch_paths(tmp_path)
    try:
        db_file.write_text("")

        # Patch sqlite3.connect AT the database module's import site.
        # database.py does `import sqlite3` inside create_backup(), which
        # resolves through sys.modules — patching there affects it.
        executed = []
        _real_connect = sqlite3.connect

        class _Tracker:
            def __init__(self, c):
                object.__setattr__(self, '_c', c)
            def execute(self, sql, *a, **kw):
                executed.append(sql)
                return self._c.execute(sql, *a, **kw)
            def close(self):
                return self._c.close()
            def __getattr__(self, n):
                return getattr(self._c, n)

        def _patched_connect(*a, **kw):
            return _Tracker(_real_connect(*a, **kw))

        with patch.object(sqlite3, "connect", side_effect=_patched_connect):
            DatabaseManager.create_backup()

        # Must have called wal_checkpoint(PASSIVE)
        checkpoints = [s for s in executed if "WAL_CHECKPOINT" in s.upper()]
        assert len(checkpoints) > 0, (
            f"must checkpoint WAL before backup, executed: {executed}"
        )
        assert any("PASSIVE" in s.upper() for s in checkpoints), (
            f"expected PASSIVE checkpoint, got: {checkpoints}"
        )

        # Must NOT have called VACUUM
        vacuums = [s for s in executed if "VACUUM" in s.upper()]
        assert len(vacuums) == 0, (
            f"VACUUM must not be called during backup, got: {vacuums}"
        )
    finally:
        _restore_paths(orig)
