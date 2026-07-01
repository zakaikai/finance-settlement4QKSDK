from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import sqlalchemy as sa
import os
import shutil
from datetime import datetime
from .services.crypto_service import encrypt_backup, decrypt_backup, detect_enc_type

# ── Config ──

def get_db_path() -> str:
    """Return the database file path from env or default.

    Priority: 1) DB_PATH env var  2) .env file  3) default data/settlement.db
    """
    root = os.path.dirname(os.path.dirname(__file__))

    env_path = os.environ.get("DB_PATH", "").strip()
    if env_path:
        if not os.path.isabs(env_path):
            env_path = os.path.join(root, env_path)
        _ensure_dir(os.path.dirname(env_path))
        return env_path

    from dotenv import load_dotenv
    load_dotenv(os.path.join(root, ".env"))
    env_path = os.environ.get("DB_PATH", "").strip()
    if env_path:
        if not os.path.isabs(env_path):
            env_path = os.path.join(root, env_path)
        _ensure_dir(os.path.dirname(env_path))
        return env_path

    d = os.path.join(root, "data")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settlement.db")


def _ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


DB_PATH = get_db_path()
BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


def _sync_migrate(db_path: str):
    """Run schema migrations via a raw sync sqlite3 connection.

    Used after restore to ensure the DB has all current columns/tables
    without relying on the async engine (which may have stale state after
    engine.dispose() on Windows).

    Sets journal_mode=DELETE first to avoid stale WAL corruption.
    """
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA busy_timeout=5000")
        # Add columns that may be missing from older backups
        migrations = [
            "ALTER TABLE publisher_game_mapping ADD COLUMN project_code VARCHAR(100)",
            "ALTER TABLE publisher_game_mapping ADD COLUMN project_name VARCHAR(200)",
            "ALTER TABLE memos ADD COLUMN is_reminder INTEGER DEFAULT 0",
            "ALTER TABLE memos ADD COLUMN reminder_cycle VARCHAR(20) DEFAULT 'none'",
            "ALTER TABLE arap_records ADD COLUMN confirmed_month VARCHAR(7) NOT NULL DEFAULT ''",
            "ALTER TABLE channel_locks ADD COLUMN confirmed_month VARCHAR(7)",
            "ALTER TABLE publisher_locks ADD COLUMN confirmed_month VARCHAR(7)",
            "ALTER TABLE company_game_mapping ADD COLUMN channel_id INTEGER REFERENCES channel_categories(channel_id)",
            "ALTER TABLE profit_expenses ADD COLUMN other_income DECIMAL(16,2) NOT NULL DEFAULT 0",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()


async def init_db():
    async with engine.begin() as conn:
        # WAL mode for better concurrent read performance
        await conn.execute(sa.text("PRAGMA journal_mode=WAL"))
        await conn.execute(sa.text("PRAGMA busy_timeout=5000"))
        from . import models
        await conn.run_sync(Base.metadata.create_all)
        # Migrate: add project_code and project_name to publisher_game_mapping if missing
        for col in ["project_code VARCHAR(100)", "project_name VARCHAR(200)"]:
            try:
                await conn.execute(sa.text(f"ALTER TABLE publisher_game_mapping ADD COLUMN {col}"))
            except Exception:
                pass
        # Migrate: add is_reminder and reminder_cycle to memos if missing
        for col in ["is_reminder INTEGER DEFAULT 0", "reminder_cycle VARCHAR(20) DEFAULT 'none'"]:
            try:
                await conn.execute(sa.text(f"ALTER TABLE memos ADD COLUMN {col}"))
            except Exception:
                pass
        # Migrate: create arap_records table if missing
        try:
            await conn.run_sync(lambda c: models.ArapRecord.__table__.create(c, checkfirst=True))
        except Exception:
            pass
        # Migrate: create monthly_closes table if missing
        try:
            await conn.run_sync(lambda c: models.MonthlyClose.__table__.create(c, checkfirst=True))
        except Exception:
            pass
        # Migrate: create profit_expenses table if missing
        try:
            await conn.run_sync(lambda c: models.ProfitExpense.__table__.create(c, checkfirst=True))
        except Exception:
            pass
        # Migrate: add other_income to profit_expenses
        try:
            await conn.execute(sa.text("ALTER TABLE profit_expenses ADD COLUMN other_income DECIMAL(16,2) NOT NULL DEFAULT 0"))
        except Exception:
            pass
        # raw_settlements 原始流水表（聚合存储）
        try:
            await conn.run_sync(lambda c: models.RawSettlement.__table__.create(c, checkfirst=True))
        except Exception:
            pass
        # Migrate: add confirmed_month to arap_records
        try:
            await conn.execute(sa.text("ALTER TABLE arap_records ADD COLUMN confirmed_month VARCHAR(7) NOT NULL DEFAULT ''"))
        except Exception:
            pass
        # Migrate: add confirmed_month to channel_locks
        try:
            await conn.execute(sa.text("ALTER TABLE channel_locks ADD COLUMN confirmed_month VARCHAR(7)"))
        except Exception:
            pass
        # Migrate: add confirmed_month to publisher_locks
        try:
            await conn.execute(sa.text("ALTER TABLE publisher_locks ADD COLUMN confirmed_month VARCHAR(7)"))
        except Exception:
            pass
        # Migrate: create payment_records + payment_allocations tables
        try:
            await conn.run_sync(lambda c: models.PaymentRecord.__table__.create(c, checkfirst=True))
        except Exception:
            pass
        try:
            await conn.run_sync(lambda c: models.PaymentAllocation.__table__.create(c, checkfirst=True))
        except Exception:
            pass
        # Migrate: add channel_id to company_game_mapping
        try:
            await conn.execute(sa.text(
                "ALTER TABLE company_game_mapping ADD COLUMN channel_id INTEGER REFERENCES channel_categories(channel_id)"
            ))
        except Exception:
            pass
        # Migrate: channel_company_mappings — recreate with party_info_id (replaces old company_id version)
        try:
            await conn.run_sync(lambda c: models.ChannelCompanyMapping.__table__.drop(c, checkfirst=True))
            await conn.run_sync(lambda c: models.ChannelCompanyMapping.__table__.create(c))
        except Exception:
            pass


# ── DatabaseManager ──

class DatabaseManager:
    """Encapsulated database operations: status, backup, restore, reset."""

    @staticmethod
    def get_status() -> dict:
        """Return database file status."""
        exists = os.path.exists(DB_PATH)
        size = os.path.getsize(DB_PATH) if exists else 0
        mtime = os.path.getmtime(DB_PATH) if exists else 0
        return {
            "db_path": DB_PATH,
            "exists": exists,
            "size_bytes": size,
            "size_display": _format_size(size),
            "modified_at": datetime.fromtimestamp(mtime).isoformat() if mtime else None,
        }

    @staticmethod
    def create_backup(encrypted: bool = True, password: str | None = None) -> dict:
        """Create a timestamped backup.

        encrypted=True + no password → AES-256-CBC with machine-derived key.
        encrypted=True + password    → AES-256-CBC with PBKDF2-derived key (portable).
        encrypted=False             → plain SQLite copy.
        """
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = ".enc.db" if encrypted else ".db"
        backup_path = os.path.join(BACKUP_DIR, f"settlement_{ts}{ext}")

        # Flush WAL to main database file before copying.
        # Use PASSIVE checkpoint (safe, non-blocking) — VACUUM is risky:
        # it requires exclusive lock + free disk space, and can corrupt the DB
        # if it fails mid-operation on Windows.
        try:
            import sqlite3
            _raw = sqlite3.connect(DB_PATH)
            _raw.execute("PRAGMA wal_checkpoint(PASSIVE)")
            _raw.close()
        except Exception:
            pass

        if encrypted:
            encrypt_backup(DB_PATH, backup_path, password=password)
        else:
            shutil.copy2(DB_PATH, backup_path)

        size = os.path.getsize(backup_path)
        return {
            "backup_path": backup_path,
            "encrypted": encrypted,
            "enc_type": detect_enc_type(backup_path) if encrypted else "plain",
            "size_bytes": size,
            "size_display": _format_size(size),
            "created_at": datetime.now().isoformat(),
        }

    @staticmethod
    def list_backups() -> list[dict]:
        """List all backup files sorted newest first."""
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backups = []
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("settlement_") and (f.endswith(".db") or f.endswith(".enc.db")):
                fp = os.path.join(BACKUP_DIR, f)
                backups.append({
                    "filename": f,
                    "path": fp,
                    "encrypted": f.endswith(".enc.db"),
                    "enc_type": detect_enc_type(fp),
                    "size_bytes": os.path.getsize(fp),
                    "size_display": _format_size(os.path.getsize(fp)),
                    "created_at": datetime.fromtimestamp(os.path.getmtime(fp)).isoformat(),
                })
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    @staticmethod
    async def restore_backup(backup_path: str, password: str | None = None) -> dict:
        """Restore database from a backup file.

        For password-key encrypted backups, password is required.
        Returns {"success": True} or raises HTTPException with detail.
        """
        await engine.dispose()

        if backup_path.endswith(".enc.db"):
            temp_path = backup_path + ".tmp"
            try:
                ok = decrypt_backup(backup_path, temp_path, password=password)
                if not ok:
                    enc_type = detect_enc_type(backup_path)
                    if enc_type == "password":
                        raise RuntimeError("密码错误，无法解密备份文件")
                    raise RuntimeError("解密失败，密钥不匹配或文件已损坏")
                shutil.copy2(temp_path, DB_PATH)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            shutil.copy2(backup_path, DB_PATH)

        # CRITICAL: Stale WAL/SHM files from the old database MUST be removed
        # before any new connection touches the restored file.  If SQLite opens
        # the new DB and finds an old WAL, it will apply stale journal data and
        # corrupt/empty the restored database.
        #
        # Strategy: delete if possible; if locked (Windows), rename to .bak so
        # SQLite ignores them.  Falls back to truncating the WAL via PRAGMA.
        import time
        for suffix in ("-wal", "-shm"):
            stale = DB_PATH + suffix
            if not os.path.exists(stale):
                continue
            removed = False
            for attempt in range(10):
                try:
                    os.unlink(stale)
                    removed = True
                    break
                except PermissionError:
                    time.sleep(0.2)
            if not removed:
                # File still locked — rename out of the way so SQLite ignores it
                try:
                    os.rename(stale, stale + ".bak." + str(int(time.time())))
                except OSError:
                    pass

        # Run schema migrations via a fresh sync connection (bypasses the
        # disposed async engine which may have stale state on Windows).
        _sync_migrate(DB_PATH)

        # Verify restore succeeded by checking a core table has data.
        # Use a raw sqlite3 connection — NOT the async engine — to read the
        # restored file directly, bypassing any lingering engine state.
        #
        # If stale WAL/SHM files could not be cleaned (locked by another
        # process), SQLite may try to apply them to the restored DB and
        # corrupt it.  We run a quick integrity check first; if it fails,
        # the DB is still usable (the restored file itself is fine) but the
        # stale WAL is poison.  In that case we attempt a last-resort rename
        # of the WAL/SHM and retry.
        import sqlite3

        def _any_table_has_rows(conn: sqlite3.Connection) -> int:
            """Return total row count across all user tables, or -1 on error."""
            try:
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                total = 0
                for (tname,) in tables:
                    try:
                        total += conn.execute(
                            f'SELECT COUNT(*) FROM "{tname}"'
                        ).fetchone()[0]
                    except sqlite3.DatabaseError:
                        continue
                return total
            except sqlite3.DatabaseError:
                return -1

        has_data = False
        for verify_attempt in range(2):
            vfy = sqlite3.connect(DB_PATH)
            try:
                vfy.execute("PRAGMA busy_timeout=5000")
                ok_row = vfy.execute("PRAGMA integrity_check").fetchone()
                if ok_row and ok_row[0] == "ok":
                    total_rows = _any_table_has_rows(vfy)
                    has_data = total_rows > 0
            except sqlite3.DatabaseError:
                # Stale WAL corrupted the in-memory view — try once more
                pass
            finally:
                vfy.close()

            if has_data:
                break

            # Stale WAL still interfering — nuke it by rewriting the file
            # with journal_mode=DELETE
            if verify_attempt == 0:
                import time, shutil as _shutil
                tmp_db = DB_PATH + ".vfy_tmp"
                _shutil.copy2(DB_PATH, tmp_db)
                vfy2 = sqlite3.connect(tmp_db)
                try:
                    vfy2.execute("PRAGMA journal_mode=DELETE")
                    vfy2.execute("VACUUM")
                    has_data = _any_table_has_rows(vfy2) > 0
                except Exception:
                    pass
                finally:
                    vfy2.close()
                if has_data:
                    # Replace the original with the WAL-free copy
                    _shutil.copy2(tmp_db, DB_PATH)
                if os.path.exists(tmp_db):
                    os.unlink(tmp_db)

        # Only reject the restore if the backup was created from an already-emptied
        # settlement database (games table present but zero rows).  General-purpose
        # SQLite files (no games table at all) pass through.
        if not has_data:
            vfy3 = sqlite3.connect(DB_PATH)
            try:
                vfy3.execute("PRAGMA busy_timeout=5000")
                has_games_table = vfy3.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='games'"
                ).fetchone()[0] > 0
            except sqlite3.DatabaseError:
                has_games_table = False
            finally:
                vfy3.close()

            if has_games_table:
                raise RuntimeError(
                    "恢复后验证失败：games 表为空。"
                    "该备份可能是在数据库已被重置后创建的，请尝试恢复更早的备份文件。"
                )

        # Restore WAL journal mode — _sync_migrate switched to DELETE
        # to avoid stale WAL interference; now switch back for performance.
        import sqlite3 as _sql_restore
        _rf = _sql_restore.connect(DB_PATH)
        try:
            _rf.execute("PRAGMA journal_mode=WAL")
        finally:
            _rf.close()

        return {"success": True, "restored_from": backup_path}

    @staticmethod
    async def reset_database(password: str | None = None) -> dict:
        """Drop all tables and recreate. Creates a backup first.

        The backup is encrypted with *password* if provided, otherwise
        auto-key (machine-derived).  After reset, the full init_db()
        migration sequence runs so that all schema extensions (tables
        and columns added outside the ORM create_all) are present.

        If the database already appears empty (no games), the backup
        step is skipped — a backup of an empty DB is useless and
        confuses restore attempts.
        """
        import sqlite3

        # Check if DB is already empty — if so, skip the backup
        # (a backup of an empty DB is misleading noise in the backup list)
        db_empty = True
        if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
            try:
                chk = sqlite3.connect(DB_PATH)
                chk.execute("PRAGMA busy_timeout=2000")
                cnt = chk.execute("SELECT COUNT(*) FROM games").fetchone()[0]
                chk.close()
                db_empty = (cnt == 0)
            except Exception:
                db_empty = True

        if db_empty:
            backup = None
        else:
            backup = DatabaseManager.create_backup(password=password)

        # Dispose the async engine pool so no connection holds a lock
        # on the DB file while we drop/recreate tables.
        await engine.dispose()

        async with engine.begin() as conn:
            from . import models
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        # Run the same migration / late-schema additions as normal startup
        await init_db()

        return {"success": True, "backup": backup, "was_empty": db_empty}

    @staticmethod
    async def get_table_counts() -> dict:
        """Return row counts for all tables."""
        from . import models
        counts = {}
        async with async_session() as session:
            tables = [
                ("games", models.Game),
                ("companies", models.Company),
                ("company_game_mapping", models.CompanyGameMapping),
                ("publishers", models.Publisher),
                ("publisher_game_mapping", models.PublisherGameMapping),
                ("channel_categories", models.ChannelCategory),
                ("backend_channels", models.BackendChannel),
                ("sub_channels", models.SubChannel),
                ("income_split_config", models.IncomeSplitConfig),
                ("payment_split_config", models.PaymentSplitConfig),
                ("raw_settlements", models.RawSettlement),
                ("deductions", models.Deduction),
                ("channel_locks", models.ChannelLock),
                ("publisher_locks", models.PublisherLock),
                #("channel_settlements", models.ChannelSettlement),  # 废止 2026-06
                #("raw_transactions", models.RawTransaction),       # 废止 2026-06
                ("party_info", models.PartyInfo),
                ("arap_records", models.ArapRecord),
                ("monthly_closes", models.MonthlyClose),
                #("ar_ap_snapshots", models.ARAPSnapshot),  # 废止 2026-06
                ("profit_expenses", models.ProfitExpense),
            ]
            for name, model in tables:
                try:
                    result = await session.execute(sa.select(sa.func.count()).select_from(model))
                    counts[name] = result.scalar()
                except Exception:
                    counts[name] = 0
        return counts


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


