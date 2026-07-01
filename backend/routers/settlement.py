import csv
import io
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from urllib.parse import quote

from ..database import get_db
from .. import models, schemas
from ..services.settlement_service import (
    query_income_settlement, query_payment_settlement,
    query_channel_settlements, query_settlement_channels,
    batch_upsert, upsert_split_configs, lock_settlement,
)

# Alias for export-full
query_full_income_export = query_income_settlement
query_full_payment_export = query_payment_settlement
from ..services.bill_service import generate_settlement_bill
from ..services.bill_template_service import render_template
from ..services.snapshot_service import (
    get_pivot, close_month, get_closed_months, get_snapshot_balances,
    get_working_month, get_pending_count, reopen_month, snapshot_from_locks,
    upsert_arap_company_override, delete_arap_company_override,
    get_breakdown,
)
from ..services.profit_service import get_profit_table, save_expense, get_profit_summary
from ..services.payment_service import get_open_items, register_payment, get_payment_history, delete_payment
from ..models import BillTemplate

router = APIRouter(prefix="/api/settlement", tags=["结算查询"])


@router.get("/income")
async def income_settlement(
    start_month: str = Query(None, description="开始月份 YYYY-MM"),
    end_month: str = Query(None, description="结束月份 YYYY-MM"),
    channel_name: str = Query(None, description="渠道/授权方名称"),
    game_id: str = Query(None, description="游戏编号"),
    db: AsyncSession = Depends(get_db),
):
    """查询收入结算 (渠道/授权方 × 游戏编号 × 月份)"""
    results = await query_income_settlement(db, start_month, end_month, channel_name, game_id)
    return {"data": results, "total": len(results)}


@router.get("/channel-settlements")
async def channel_settlements(
    start_month: str = Query(None, description="开始月份 YYYY-MM"),
    end_month: str = Query(None, description="结束月份 YYYY-MM"),
    channel_name: str = Query(None, description="渠道/授权方名称"),
    game_id: str = Query(None, description="游戏编号"),
    db: AsyncSession = Depends(get_db),
):
    """原始流水表: ChannelSettlement 简化视图 (渠道×游戏×月份 聚合流水)。"""
    results = await query_channel_settlements(db, start_month, end_month, channel_name, game_id)
    return {"data": results, "total": len(results)}


@router.get("/settlement-channels")
async def settlement_channels(db: AsyncSession = Depends(get_db)):
    """返回原始流水表中出现的渠道列表（弹性导入渠道选择器数据源）。"""
    return {"data": await query_settlement_channels(db)}


@router.get("/payment")
async def payment_settlement(
    start_month: str = Query(None, description="开始月份 YYYY-MM"),
    end_month: str = Query(None, description="结束月份 YYYY-MM"),
    publisher_name: str = Query(None, description="研发商户/渠道名称"),
    game_id: str = Query(None, description="游戏编号"),
    db: AsyncSession = Depends(get_db),
):
    """查询付款结算 (研发商户/渠道 × 游戏编号 × 月份)"""
    results = await query_payment_settlement(db, start_month, end_month, publisher_name, game_id)
    return {"data": results, "total": len(results)}


@router.get("/export-csv")
async def export_csv(
    mode: str = Query(..., description="income 或 payment"),
    start_month: str = Query(None, description="开始月份 YYYY-MM"),
    end_month: str = Query(None, description="结束月份 YYYY-MM"),
    channel_name: str = Query(None, description="渠道/授权方名称"),
    publisher_name: str = Query(None, description="研发商户/渠道名称"),
    game_id: str = Query(None, description="游戏编号"),
    db: AsyncSession = Depends(get_db),
):
    """导出结算数据为 CSV"""
    if mode not in ("income", "payment"):
        raise HTTPException(400, "mode 必须为 income 或 payment")

    if mode == "income":
        rows = await query_income_settlement(db, start_month, end_month, channel_name, game_id)
    else:
        rows = await query_payment_settlement(db, start_month, end_month, publisher_name, game_id)

    buf = io.StringIO(newline="")
    writer = csv.writer(buf)

    def _pct(v):
        if v is None:
            return ""
        return f"{float(v) * 100:.2f}%"

    def _num(v):
        if v is None:
            return ""
        return f"{v:.2f}"

    if mode == "income":
        writer.writerow(["收入方名称", "项目编号", "项目名称", "我方公司", "游戏编号", "游戏名称",
                          "月份", "原始流水", "真实流水", "代金券", "测试", "福利币", "坏账",
                          "扣除合计", "分成比例", "通道费率", "税率", "结算金额"])
        for r in rows:
            writer.writerow([
                r["channel_name"], r["project_code"], r["project_name"], r["company_name"],
                r["game_id"], r["game_name"], r["month"],
                _num(r["raw_revenue"]), _num(r["real_revenue"]),
                _num(r["vouchers"]), _num(r["test"]), _num(r["welfare"]), _num(r["bad_debt"]),
                _num(r["total_deductions"]),
                _pct(r["split_rate"]), _pct(r["channel_fee_rate"]), _pct(r["tax_rate"]),
                _num(r["settlement_amount"]),
            ])
    else:
        writer.writerow(["付款方名称", "项目编号", "项目名称", "我方公司", "游戏编号", "游戏名称",
                          "月份", "原始流水", "真实流水", "代金券", "测试", "福利币", "坏账",
                          "扣除合计", "固定费用", "分成比例", "通道费率", "税率", "结算金额"])
        for r in rows:
            writer.writerow([
                r["publisher_name"], r["project_code"], r["project_name"], r["company_name"],
                r["game_id"], r["game_name"], r["month"],
                _num(r["raw_revenue"]), _num(r["real_revenue"]),
                _num(r["vouchers"]), _num(r["test"]), _num(r["welfare"]), _num(r["bad_debt"]),
                _num(r["total_deductions"]), _num(r["fixed_fee"]),
                _pct(r["split_rate"]), _pct(r["channel_fee_rate"]), _pct(r["tax_rate"]),
                _num(r["settlement_amount"]),
            ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    filename = f"{mode}_settlement.csv"

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={quote(filename)}"},
    )


@router.get("/export-full")
async def export_full_csv(
    mode: str = Query(..., description="income 或 payment"),
    start_month: str = Query(None, description="开始月份 YYYY-MM"),
    end_month: str = Query(None, description="结束月份 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """全量导出: 渠道×游戏×月份 聚合粒度"""
    if mode not in ("income", "payment"):
        raise HTTPException(400, "mode 必须为 income 或 payment")

    rows = await query_income_settlement(db, start_month, end_month) if mode == "income" else await query_payment_settlement(db, start_month, end_month)

    buf = io.StringIO(newline="")
    writer = csv.writer(buf)

    def _pct(v): return "" if v is None else f"{float(v) * 100:.2f}%"
    def _num(v): return "" if v is None else f"{v:.2f}"

    if mode == "income":
        writer.writerow(["渠道名称", "渠道主体名称", "项目编号", "项目名称", "我方公司", "游戏编号", "游戏名称",
            "月份", "原始流水", "真实流水", "代金券", "测试", "福利币", "坏账",
            "扣除合计", "分成比例", "通道费率", "税率", "结算金额",
            "锁定真实流水", "锁定结算金额"])
        for r in rows:
            writer.writerow([
                r["channel_name"], r.get("party_name",""), r.get("project_code",""), r.get("project_name",""), r.get("company_name",""),
                r["game_id"], r["game_name"], r["month"],
                _num(r["raw_revenue"]), _num(r["real_revenue"]),
                _num(r["vouchers"]), _num(r["test"]), _num(r["welfare"]), _num(r["bad_debt"]),
                _num(r["total_deductions"]),
                _pct(r["split_rate"]), _pct(r["channel_fee_rate"]), _pct(r["tax_rate"]),
                _num(r["settlement_amount"]),
                _num(r["locked_real_revenue"]) if r.get("locked_real_revenue") is not None else "",
                _num(r["locked_settlement_amount"]) if r.get("locked_settlement_amount") is not None else "",
            ])
    else:
        writer.writerow(["付款方名称", "项目编号", "项目名称", "我方公司", "游戏编号", "游戏名称",
            "月份", "原始流水", "真实流水", "代金券", "测试", "福利币", "坏账",
            "扣除合计", "固定费用", "分成比例", "通道费率", "税率", "结算金额",
            "锁定真实流水", "锁定结算金额"])
        for r in rows:
            writer.writerow([
                r["publisher_name"], r.get("project_code",""), r.get("project_name",""), r.get("company_name",""),
                r["game_id"], r["game_name"], r["month"],
                _num(r["raw_revenue"]), _num(r["real_revenue"]),
                _num(r["vouchers"]), _num(r["test"]), _num(r["welfare"]), _num(r["bad_debt"]),
                _num(r["total_deductions"]), _num(r.get("fixed_fee")),
                _pct(r["split_rate"]), _pct(r["channel_fee_rate"]), _pct(r["tax_rate"]),
                _num(r["settlement_amount"]),
                _num(r["locked_real_revenue"]) if r.get("locked_real_revenue") is not None else "",
                _num(r["locked_settlement_amount"]) if r.get("locked_settlement_amount") is not None else "",
            ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    month_label = f"{start_month or 'all'}_{end_month or 'all'}"
    filename = f"全量导出_{mode}_{month_label}.csv"

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={quote(filename)}"},
    )


@router.post("/deductions/batch")
async def batch_deductions(
    body: list[schemas.DeductionUpdate],
    db: AsyncSession = Depends(get_db),
):
    """批量保存扣除项目 (按 channel_name + game_id + month 匹配 upsert)"""
    await batch_upsert(
        db, body,
        fk_model=models.ChannelCategory, fk_col_name="channel_name",
        fk_getter=lambda i: i.channel_name, fk_cache_key="channel_categories",
        model_cls=models.Deduction,
        match_keys=["channel_id", "game_id", "month"],
        set_fields=["vouchers", "test", "welfare", "bad_debt"],
    )
    return {"success": True}


@router.get("/income-split-configs")
async def list_income_split_configs(db: AsyncSession = Depends(get_db)):
    """返回收入分成配置列表（含渠道名称、游戏名称）。"""
    rows = (await db.execute(
        select(
            models.IncomeSplitConfig.id,
            models.ChannelCategory.channel_name,
            models.IncomeSplitConfig.game_id,
            models.Game.game_name,
            models.IncomeSplitConfig.split_rate,
            models.IncomeSplitConfig.channel_fee_rate,
            models.IncomeSplitConfig.tax_rate,
            models.IncomeSplitConfig.effective_from,
            models.IncomeSplitConfig.effective_to,
        )
        .select_from(models.IncomeSplitConfig)
        .join(models.ChannelCategory, models.IncomeSplitConfig.channel_id == models.ChannelCategory.channel_id)
        .join(models.Game, models.IncomeSplitConfig.game_id == models.Game.game_id)
        .order_by(models.IncomeSplitConfig.effective_from.desc(), models.ChannelCategory.channel_name, models.IncomeSplitConfig.game_id)
    )).all()
    return {"data": [
        {
            "id": r.id,
            "channel_name": r.channel_name,
            "game_id": r.game_id,
            "game_name": r.game_name,
            "split_rate": float(r.split_rate),
            "channel_fee_rate": float(r.channel_fee_rate),
            "tax_rate": float(r.tax_rate),
            "effective_from": r.effective_from.isoformat(),
            "effective_to": r.effective_to.isoformat() if r.effective_to else None,
        }
        for r in rows
    ]}


@router.get("/payment-split-configs")
async def list_payment_split_configs(db: AsyncSession = Depends(get_db)):
    """返回付款分成配置列表（含研发商名称、游戏名称）。"""
    rows = (await db.execute(
        select(
            models.PaymentSplitConfig.id,
            models.Publisher.publisher_name.label("publisher_name"),
            models.PaymentSplitConfig.game_id,
            models.Game.game_name,
            models.PaymentSplitConfig.split_rate,
            models.PaymentSplitConfig.channel_fee_rate,
            models.PaymentSplitConfig.tax_rate,
            models.PaymentSplitConfig.fixed_fee,
            models.PaymentSplitConfig.effective_from,
            models.PaymentSplitConfig.effective_to,
        )
        .select_from(models.PaymentSplitConfig)
        .join(models.Publisher, models.PaymentSplitConfig.publisher_id == models.Publisher.publisher_id)
        .join(models.Game, models.PaymentSplitConfig.game_id == models.Game.game_id)
        .order_by(models.PaymentSplitConfig.effective_from.desc(), models.Publisher.publisher_name, models.PaymentSplitConfig.game_id)
    )).all()
    return {"data": [
        {
            "id": r.id,
            "publisher_name": r.publisher_name,
            "game_id": r.game_id,
            "game_name": r.game_name,
            "split_rate": float(r.split_rate),
            "channel_fee_rate": float(r.channel_fee_rate),
            "tax_rate": float(r.tax_rate),
            "fixed_fee": float(r.fixed_fee),
            "effective_from": r.effective_from.isoformat(),
            "effective_to": r.effective_to.isoformat() if r.effective_to else None,
        }
        for r in rows
    ]}


@router.post("/income-split-config/batch")
async def batch_income_split_config(
    body: list[schemas.IncomeSplitConfigUpdate],
    db: AsyncSession = Depends(get_db),
):
    """批量保存收入分成配置 — 关旧建新"""
    await upsert_split_configs(
        db, body,
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig,
    )
    return {"success": True}


@router.post("/payment-split-config/batch")
async def batch_payment_split_config(
    body: list[schemas.PaymentSplitConfigUpdate],
    db: AsyncSession = Depends(get_db),
):
    """批量保存付款分成配置 — 关旧建新"""
    await upsert_split_configs(
        db, body,
        fk_model_cls=models.Publisher, fk_name_field="publisher_name",
        fk_cache_key="publishers", fk_col_name="publisher_id",
        config_cls=models.PaymentSplitConfig,
        extra_fields=("fixed_fee",),
    )
    return {"success": True}




@router.post("/bill")
async def download_bill(
    body: schemas.BillRequest,
    db: AsyncSession = Depends(get_db),
):
    """生成并下载结算对账单 Excel"""
    def _fmt_month(m):
        if not m or len(m) < 7: return m or ""
        y, mo = m[:4], m[5:7]
        return f"{y}年{int(mo)}月"
    if body.start_month and body.end_month and body.start_month != body.end_month:
        period = f"{_fmt_month(body.start_month)} ~ {_fmt_month(body.end_month)}"
    else:
        period = _fmt_month(body.start_month or body.end_month) or "全部"

    party_a = (await db.execute(
        select(models.PartyInfo).where(models.PartyInfo.id == body.party_id_a)
    )).scalar_one_or_none()
    if not party_a:
        raise HTTPException(400, "甲方主体信息不存在")
    party_b = (await db.execute(
        select(models.PartyInfo).where(models.PartyInfo.id == body.party_id_b)
    )).scalar_one_or_none()
    if not party_b:
        raise HTTPException(400, "乙方主体信息不存在")

    # If rows not provided, re-query from DB using the same date filters
    rows = body.rows
    if rows is None:
        if body.mode == "income":
            rows = await query_income_settlement(db, body.start_month, body.end_month)
        else:
            rows = await query_payment_settlement(db, body.start_month, body.end_month)

    # Template-based generation
    if body.template_id:
        tpl = (await db.execute(
            select(BillTemplate).where(BillTemplate.id == body.template_id)
        )).scalar_one_or_none()
        if not tpl or not tpl.file_path or not os.path.exists(tpl.file_path):
            raise HTTPException(404, "模板文件不存在")
        buf = render_template(tpl.file_path, party_a, party_b, period, rows, body.mode)
        filename = f"{tpl.name}_{period}.xlsx"
    else:
        title = "收 入 结 算 对 账 单" if body.mode == "income" else "付 款 结 算 对 账 单"
        buf = await generate_settlement_bill(party_a, period, party_b, rows, title, body.mode)
        filename = f"{'收入' if body.mode == 'income' else '付款'}结算对账单_{period}.xlsx"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={quote(filename)}"},
    )


# ── Lock mechanism ──


@router.post("/lock")
async def lock_settlement_value(
    body: schemas.LockRequest,
    db: AsyncSession = Depends(get_db),
):
    """Lock or unlock real_revenue / settlement_amount."""
    try:
        result = await lock_settlement(
            db, body.game_id, body.channel_id,
            body.publisher_name, body.month,
            body.field, body.value,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── ARAP Snapshot ──


@router.post("/arap/snapshot")
async def arap_snapshot(
    confirmed_month: str = Query(..., description="确认月 YYYY-MM，如 2026-06"),
    db: AsyncSession = Depends(get_db),
):
    """增量快照：从未快照的 channel_locks + publisher_locks 聚合写入 arap_records。

    每笔 ARAP 记录绑定 confirmed_month，同一锁不会重复快照。
    """
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = await snapshot_from_locks(db, now, confirmed_month)
    return {"data": result}


@router.get("/arap/records")
async def arap_records_query(
    entity_type: str = Query("channel"),
    month_from: str = Query(...),
    month_to: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """查询 arap_records 表。"""
    from ..models import ArapRecord
    stmt = select(ArapRecord).where(
        ArapRecord.entity_type == entity_type,
        ArapRecord.month >= month_from,
        ArapRecord.month <= month_to,
    ).order_by(ArapRecord.month, ArapRecord.entity_name)
    rows = (await db.execute(stmt)).scalars().all()
    return {"data": [
        {"id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id,
         "entity_name": r.entity_name, "company_id": r.company_id,
         "company_name": r.company_name, "game_id": r.game_id,
         "game_name": r.game_name, "month": r.month,
         "settlement_amount": float(r.settlement_amount),
         "locked_amount": float(r.locked_amount) if r.locked_amount else None,
         "snapshot_at": r.snapshot_at}
        for r in rows
    ]}


# ── AR/AP Pivot & Monthly Close ──

@router.get("/arap/pivot")
async def arap_pivot(
    entity_type: str = Query(..., description="channel or publisher"),
    month_from: str = Query(..., description="YYYY-MM"),
    month_to: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    return await get_pivot(db, entity_type, month_from, month_to)


@router.post("/arap/monthly-close")
async def arap_monthly_close(
    body: schemas.MonthlyCloseRequest,
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return await close_month(db, body.month, now)


@router.get("/arap/monthly-closes")
async def arap_monthly_closes(
    db: AsyncSession = Depends(get_db),
):
    return {"closed_months": await get_closed_months(db)}


@router.get("/arap/working-month")
async def arap_working_month(
    db: AsyncSession = Depends(get_db),
):
    return {"working_month": await get_working_month(db)}


@router.get("/arap/pending-count")
async def arap_pending_count(
    db: AsyncSession = Depends(get_db),
):
    """未锁定项目统计，按月份返回渠道/研发商未锁定数量。"""
    return {"pending": await get_pending_count(db)}


@router.delete("/arap/monthly-close/{month}")
async def arap_reopen_month(
    month: str,
    db: AsyncSession = Depends(get_db),
):
    """反月结：删除月结记录，恢复该月为可锁定状态。"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        return await reopen_month(db, month, now)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── ARAP Company Overrides (payment-side only) ──


@router.post("/arap/company-override")
async def arap_company_override(
    body: schemas.ArapCompanyOverrideUpdate,
    db: AsyncSession = Depends(get_db),
):
    """UPSERT 应付侧公司覆盖."""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        return await upsert_arap_company_override(
            db, body.entity_id, body.original_company_id,
            body.override_company_id, now,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/arap/company-override")
async def arap_company_override_delete(
    body: schemas.ArapCompanyOverrideDelete,
    db: AsyncSession = Depends(get_db),
):
    """删除应付侧公司覆盖，恢复快照默认."""
    deleted = await delete_arap_company_override(
        db, body.entity_id, body.original_company_id,
    )
    if not deleted:
        raise HTTPException(404, "未找到对应的覆盖记录")
    return {"success": True}


# ── Profit Statement ──

@router.get("/profit/table")
async def profit_table(
    company_id: int | None = Query(None),
    month_from: str = Query(..., description="YYYY-MM"),
    month_to: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """利润表：收入/成本/毛利/费用/净利润，按月汇总。"""
    return await get_profit_table(db, company_id, month_from, month_to)


@router.put("/profit/expense")
async def profit_expense(
    body: schemas.ProfitExpenseRequest,
    db: AsyncSession = Depends(get_db),
):
    """保存期间费用和其他业务收入。"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return await save_expense(db, body.month_from, body.month_to, body.company_id, body.expense_amount, now,
                              other_income=body.other_income)


@router.get("/profit/summary")
async def profit_summary(
    month: str = Query(..., description="YYYY-MM"),
    company_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """利润汇总：毛利 + 净利润。"""
    return await get_profit_summary(db, month, company_id)


# ── Ledger (收付款登记) ──


@router.get("/ledger/open-items")
async def ledger_open_items(
    entity_type: str | None = Query(None, description="channel or publisher"),
    db: AsyncSession = Depends(get_db),
):
    """返回未结应收/应付项（已扣减已冲销金额），按月份升序（FIFO）。"""
    items = await get_open_items(db, entity_type=entity_type)
    return {"data": items}


@router.post("/ledger/payment")
async def ledger_register_payment(
    body: schemas.PaymentRequest,
    collection_month: str = Query(..., description="收款月 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """登记收付款，FIFO 冲销未结项。"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        result = await register_payment(
            db,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            company_id=body.company_id,
            amount=body.amount,
            collection_month=collection_month,
            now=now,
            note=body.note,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/ledger/entries")
async def ledger_entries(
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    company_id: int | None = Query(None),
    month_from: str | None = Query(None),
    month_to: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """收付款历史记录。"""
    items = await get_payment_history(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        company_id=company_id,
        month_from=month_from,
        month_to=month_to,
    )
    return {"data": items}


@router.get("/ledger/balances")
async def ledger_balances(
    month: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """AR/AP 账户余额摘要。"""
    return await get_snapshot_balances(db, month)


@router.delete("/ledger/payment/{payment_id}")
async def ledger_delete_payment(
    payment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除付款记录，同时删除关联的冲销分配。"""
    try:
        result = await delete_payment(db, payment_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/arap/breakdown")
async def arap_breakdown(
    entity_type: str = Query(..., description="channel or publisher"),
    entity_id: int = Query(...),
    company_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """返回借方构成（按收款月）和收付记录，用于余额点击后的明细 Modal。"""
    return await get_breakdown(db, entity_type, entity_id, company_id)


# ── Dashboard ──

@router.get("/arap/dashboard-balances")
async def arap_dashboard_balances(
    month: str = Query(None, description="YYYY-MM, defaults to previous month"),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard 4 indicators: AR balance, AP balance, monthly revenue, monthly cost."""
    return await get_snapshot_balances(db, month)
