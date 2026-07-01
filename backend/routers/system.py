"""System management router: status, backup, restore, reset, patches, logs, updates."""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text as sa_text

from ..database import get_db, DatabaseManager, DB_PATH
from .. import models
from .. import updater
from .. import auth
from ..services.lock_service import diagnose_lock_cs_consistency

router = APIRouter(prefix="/api/system", tags=["系统管理"])


# ── LAN sharing toggle ──

@router.get("/lan-status")
async def get_lan_status():
    return {"data": {"lan_enabled": auth.get_lan_enabled()}}


@router.post("/lan-toggle")
async def toggle_lan(data: dict):
    enabled = bool(data.get("enabled", False))
    auth.set_lan_enabled(enabled)
    return {"data": {"lan_enabled": enabled}}


# ── Status ──

@router.get("/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    """数据库状态：路径、大小、表行数、锁一致性诊断。"""
    status = DatabaseManager.get_status()
    counts = await DatabaseManager.get_table_counts()
    status["table_counts"] = counts
    lock_diag = await diagnose_lock_cs_consistency(db)
    status["lock_consistency"] = {
        "mismatches": len(lock_diag),
        "details": lock_diag,
    }
    return {"data": status}


# ── Backup ──

@router.post("/backup")
async def create_backup(
    password: str | None = Query(None, description="加密密码（可选），设置后备份使用密码加密，可跨机器恢复"),
):
    """创建数据库备份。支持明文、自动密钥加密、密码加密三种模式。"""
    encrypted = True
    backup = DatabaseManager.create_backup(encrypted=encrypted, password=password)
    detail = f"创建备份: {backup['backup_path']}"
    if backup.get("enc_type") == "password":
        detail += " (密码加密)"
    elif backup.get("enc_type") == "auto":
        detail += " (本机加密)"
    await _add_log("backup", detail)
    return {"data": backup}


@router.get("/backups")
async def list_backups():
    """列出所有备份文件。"""
    return {"data": DatabaseManager.list_backups()}


@router.post("/restore")
async def restore_backup(
    backup_path: str = Query(..., description="备份文件路径"),
    password: str | None = Query(None, description="解密密码（密码加密的备份需要提供）"),
):
    """从备份文件恢复数据库。密码加密的备份需提供对应密码。"""
    if not os.path.exists(backup_path):
        raise HTTPException(400, "备份文件不存在，请尝试上传文件恢复")
    try:
        result = await DatabaseManager.restore_backup(backup_path, password=password)
        await _add_log("restore", f"从备份恢复: {backup_path}")
        return {"data": result}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/restore-file")
async def restore_backup_from_file(
    file: UploadFile = File(...),
    password: str | None = Query(None, description="解密密码（可选）"),
):
    """从上传的备份文件恢复数据库。支持 .db（明文）和 .enc.db（加密）文件。"""
    import tempfile

    suffix = ".enc.db" if (file.filename or "").endswith(".enc.db") else ".db"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if not os.path.exists(tmp_path):
            raise HTTPException(400, "文件上传失败")
        result = await DatabaseManager.restore_backup(tmp_path, password=password)
        await _add_log("restore", f"从上传文件恢复: {file.filename}")
        return {"data": result}
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Reset ──

@router.post("/reset")
async def reset_database(
    confirm: str = Query(..., description="确认码: RESET"),
    password: str | None = Query(None, description="备份加密密码（可选），留空使用本机自动密钥"),
):
    """重置数据库：清除所有表并重建。需传入确认码 RESET。

    重置前自动创建备份。可传入 password 参数使用密码加密备份（可跨机器恢复），
    留空则使用本机自动密钥加密。
    """
    if confirm != "RESET":
        raise HTTPException(400, "确认码不正确，需传入 RESET")
    result = await DatabaseManager.reset_database(password=password)
    await _add_log("reset", "数据库已重置" + (" (密码加密备份)" if password else " (自动密钥备份)"))
    return {"data": result}


# ── Patches / Migrations ──

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")


@router.get("/patches")
async def list_patches(db: AsyncSession = Depends(get_db)):
    """列出所有迁移文件和已应用状态。"""
    applied = set()
    try:
        rows = await db.execute(select(models.SchemaMigration.version))
        applied = {r[0] for r in rows}
    except Exception:
        pass  # table might not exist yet

    os.makedirs(MIGRATIONS_DIR, exist_ok=True)
    patches = []
    for f in sorted(os.listdir(MIGRATIONS_DIR)):
        if f.endswith(".sql") and not f.startswith("_"):
            fp = os.path.join(MIGRATIONS_DIR, f)
            version = f.replace(".sql", "")
            patches.append({
                "filename": f,
                "version": version,
                "applied": version in applied,
                "size_bytes": os.path.getsize(fp),
            })
    return {"data": patches}


@router.post("/patches/run")
async def run_patches(db: AsyncSession = Depends(get_db)):
    """运行所有未应用的迁移文件。"""
    # Get applied versions
    applied = set()
    try:
        rows = await db.execute(select(models.SchemaMigration.version))
        applied = {r[0] for r in rows}
    except Exception:
        pass

    os.makedirs(MIGRATIONS_DIR, exist_ok=True)
    results = []
    for f in sorted(os.listdir(MIGRATIONS_DIR)):
        if not f.endswith(".sql") or f.startswith("_"):
            continue
        version = f.replace(".sql", "")
        if version in applied:
            continue

        fp = os.path.join(MIGRATIONS_DIR, f)
        with open(fp, encoding="utf-8") as fh:
            sql = fh.read().strip()
        if not sql:
            continue

        try:
            async with db.connection() as conn:
                # Split by semicolons and execute each statement
                for stmt in sql.split(";"):
                    s = stmt.strip()
                    if s:
                        await conn.execute(text(s))
            # Record migration
            mig = models.SchemaMigration(
                version=version,
                description=f,
                applied_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            db.add(mig)
            await db.commit()
            results.append({"version": version, "status": "applied"})
            await _add_log("patch", f"应用迁移: {version}")
        except Exception as e:
            results.append({"version": version, "status": "error", "error": str(e)})

    return {"data": {"results": results, "total": len(results)}}


# ── Audit Logs ──

@router.get("/logs")
async def get_logs(
    limit: int = Query(50, description="返回条数"),
    offset: int = Query(0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
):
    """查询审计日志。"""
    try:
        rows = await db.execute(
            select(models.AuditLog).order_by(models.AuditLog.id.desc()).offset(offset).limit(limit)
        )
        logs = [{
            "id": r.id,
            "action": r.action,
            "detail": r.detail,
            "user": r.user,
            "created_at": r.created_at,
        } for r in rows.scalars()]
        total = (await db.execute(select(func.count()).select_from(models.AuditLog))).scalar()
        return {"data": logs, "total": total}
    except Exception:
        return {"data": [], "total": 0}


# ── Update / Version ──


@router.get("/version")
async def get_version():
    """返回当前版本信息。"""
    return {"data": updater.read_local_version()}


@router.get("/check-update")
async def check_update():
    """检查是否有新版本可用。"""
    result = await updater.check_update()
    return {"data": result}


@router.post("/apply-patch")
async def apply_patch(file: UploadFile = File(...)):
    """应用补丁文件 (zip 格式)。"""
    import tempfile

    suffix = ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = updater.apply_patch(tmp_path)
        return {"data": result}
    finally:
        os.unlink(tmp_path)


# ── Helper ──

async def _add_log(action: str, detail: str = None, user: str = None):
    """Internal helper to write an audit log entry."""
    from ..database import async_session
    try:
        async with async_session() as session:
            log = models.AuditLog(
                action=action,
                detail=detail,
                user=user,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            session.add(log)
            await session.commit()
    except Exception:
        pass  # don't let logging failure break the main operation


# ── ARAP data maintenance ──


@router.get("/arap-months")
async def arap_months(db: AsyncSession = Depends(get_db)):
    """Return confirmed_months (收款月份) with ARAP data, excluding closed months."""
    arap_rows = (await db.execute(
        select(models.ArapRecord.confirmed_month)
        .distinct()
        .order_by(models.ArapRecord.confirmed_month)
    )).scalars().all()

    closed_rows = (await db.execute(
        select(models.MonthlyClose.month)
    )).scalars().all()
    closed_set = set(closed_rows)

    clearable = [m for m in arap_rows if m not in closed_set]
    return {"data": {
        "all_months": list(arap_rows),
        "closed_months": list(closed_rows),
        "clearable_months": clearable,
    }}


@router.post("/arap-clear")
async def arap_clear(
    month: str = Query(..., description="收款月份 (confirmed_month) YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """Clear arap_records for the given confirmed_month (收款月份).
    Also resets confirmed_month on channel_locks + publisher_locks
    so those locks can be re-snapshotted."""
    closed = (await db.execute(
        select(models.MonthlyClose).where(models.MonthlyClose.month == month)
    )).scalar_one_or_none()
    if closed:
        raise HTTPException(400, f"月份 {month} 已月结关闭，请先反月结后再操作")

    # Delete arap_records by confirmed_month (收款月份)
    result = await db.execute(
        models.ArapRecord.__table__.delete()
        .where(models.ArapRecord.confirmed_month == month)
    )
    deleted = result.rowcount

    # Reset confirmed_month on locks so they can be re-snapshotted
    ch_reset = await db.execute(
        models.ChannelLock.__table__.update()
        .where(models.ChannelLock.confirmed_month == month)
        .values(confirmed_month=None)
    )
    pub_reset = await db.execute(
        models.PublisherLock.__table__.update()
        .where(models.PublisherLock.confirmed_month == month)
        .values(confirmed_month=None)
    )

    await db.commit()
    await _add_log(
        "arap_clear",
        f"清除 ARAP 数据: {month}, {deleted} 条, "
        f"重置渠道锁 {ch_reset.rowcount} + 研发商锁 {pub_reset.rowcount}",
    )
    return {"data": {
        "month": month,
        "deleted": deleted,
        "channel_locks_reset": ch_reset.rowcount,
        "publisher_locks_reset": pub_reset.rowcount,
    }}
