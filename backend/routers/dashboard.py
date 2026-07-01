from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.dashboard_service import query_ranking, query_trend, query_level2_options, query_summary, query_init, query_available_months

router = APIRouter(prefix="/api/dashboard", tags=["首页看板"])


@router.get("/init")
async def dashboard_init(db: AsyncSession = Depends(get_db)):
    """首页看板初始化：汇总 + 三个默认排行 + 近6月趋势 + 一级下拉选项"""
    data = await query_init(db)
    return {"data": data}


@router.get("/available-months")
async def available_months(db: AsyncSession = Depends(get_db)):
    """返回所有有数据的月份列表，最新在前"""
    months = await query_available_months(db)
    return {"months": months}


@router.get("/ranking")
async def ranking(
    dimension: str = Query(..., description="channel|publisher|game|project"),
    metric: str = Query(..., description="real_revenue|settlement_amount"),
    count: int = Query(20, description="返回条数"),
    month: str = Query(None, description="YYYY-MM, 不传则默认最新月份"),
    db: AsyncSession = Depends(get_db),
):
    """排行数据：当月值、上月值、环比增长率"""
    data = await query_ranking(db, dimension, metric, count, month=month)
    return {"data": data}


@router.get("/trend")
async def trend(
    level1_type: str = Query(..., description="publisher|channel"),
    level1_value: str = Query(..., description="一级筛选值"),
    level2_value: str = Query(None, description="二级筛选值（游戏名/项目名）"),
    db: AsyncSession = Depends(get_db),
):
    """近6月趋势：真实流水 + 结算金额"""
    series = await query_trend(db, level1_type, level1_value, level2_value)
    return {"data": series}


@router.get("/level2-options")
async def level2_options(
    level1_type: str = Query(..., description="publisher|channel"),
    level1_value: str = Query(..., description="一级筛选值"),
    db: AsyncSession = Depends(get_db),
):
    """二级下拉选项"""
    options = await query_level2_options(db, level1_type, level1_value)
    return {"data": options}


@router.get("/trend-summary")
async def trend_summary(
    db: AsyncSession = Depends(get_db),
):
    """近6月汇总趋势（全渠道合计）"""
    from ..services.dashboard_service import query_trend_summary
    series = await query_trend_summary(db)
    return {"data": series}


@router.get("/level1-options")
async def level1_options(
    level1_type: str = Query(..., description="publisher|channel"),
    db: AsyncSession = Depends(get_db),
):
    """一级下拉选项（渠道名称列表或研发商列表）"""
    from ..services.dashboard_service import query_level1_options
    options = await query_level1_options(db, level1_type)
    return {"data": options}


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    """首页看板汇总：当月总流水、总结算、各维度数量、环比增长"""
    data = await query_summary(db)
    return {"data": data}
