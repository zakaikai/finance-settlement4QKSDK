import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..database import get_db
from .. import models, schemas
from ..services.basic_data_service import (
    check_fk_deps, batch_save_channels, batch_save_company_games,
    save_company_game_override, delete_company_game_override,
)

logger = logging.getLogger("finance-settlement")

router = APIRouter(prefix="/api/basic", tags=["基础数据管理"])


# ── Games ──

@router.get("/games")
async def list_games(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.Game))).scalars().all()
    return {"data": [{"game_id": r.game_id, "game_name": r.game_name, "game_backend_name": r.game_backend_name, "discount_rate": float(r.discount_rate)} for r in rows]}


# ── Companies ──

@router.get("/companies")
async def list_companies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.Company))).scalars().all()
    return {"data": [{"company_id": r.company_id, "company_name": r.company_name} for r in rows]}


# ── Publishers ──

@router.get("/publishers")
async def list_publishers(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.Publisher))).scalars().all()
    return {"data": [{"publisher_id": r.publisher_id, "publisher_name": r.publisher_name} for r in rows]}


# ── Games CRUD ──

@router.post("/games")
async def create_game(body: schemas.GameCreate, db: AsyncSession = Depends(get_db)):
    game = models.Game(**body.model_dump())
    db.add(game)
    await db.commit()
    return {"data": {"game_id": game.game_id}}


@router.put("/games/{game_id}")
async def update_game(game_id: str, body: schemas.GameUpdate, db: AsyncSession = Depends(get_db)):
    game = (await db.execute(select(models.Game).where(models.Game.game_id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "游戏不存在")

    game.game_name = body.game_name
    game.game_backend_name = body.game_backend_name
    game.discount_rate = body.discount_rate
    await db.commit()
    return {"data": {"game_id": game_id}}


@router.delete("/games/{game_id}")
async def delete_game(game_id: str, db: AsyncSession = Depends(get_db)):
    await check_fk_deps(db, "Game", game_id, "游戏")
    await db.execute(delete(models.Game).where(models.Game.game_id == game_id))
    await db.commit()
    return {"data": {"game_id": game_id}}


@router.post("/games/batch")
async def batch_games(body: schemas.GameBatchRequest, db: AsyncSession = Depends(get_db)):
    for item in body.created:
        if not item.game_id or not item.game_id.strip():
            raise HTTPException(400, "游戏编号不能为空")
        db.add(models.Game(**item.model_dump()))
    for item in body.updated:
        game = (await db.execute(select(models.Game).where(models.Game.game_id == item.game_id))).scalar_one_or_none()
        if game:
            game.game_name = item.game_name
            game.game_backend_name = item.game_backend_name
            game.discount_rate = item.discount_rate
    for gid in body.deleted:
        await check_fk_deps(db, "Game", gid, "游戏")
        await db.execute(delete(models.Game).where(models.Game.game_id == gid))
    await db.commit()
    return {"success": True}


# ── Companies CRUD ──

@router.post("/companies")
async def create_company(body: schemas.CompanyCreate, db: AsyncSession = Depends(get_db)):
    company = models.Company(company_name=body.company_name)
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return {"data": {"company_id": company.company_id}}


@router.put("/companies/{company_id}")
async def update_company(company_id: int, body: schemas.CompanyUpdate, db: AsyncSession = Depends(get_db)):
    company = (await db.execute(select(models.Company).where(models.Company.company_id == company_id))).scalar_one_or_none()
    if not company:
        raise HTTPException(404, "公司不存在")
    company.company_name = body.company_name
    await db.commit()
    return {"data": {"company_id": company_id}}


@router.delete("/companies/{company_id}")
async def delete_company(company_id: int, db: AsyncSession = Depends(get_db)):
    await check_fk_deps(db, "Company", company_id, "公司")
    await db.execute(delete(models.Company).where(models.Company.company_id == company_id))
    await db.commit()
    return {"data": {"company_id": company_id}}


@router.post("/companies/batch")
async def batch_companies(body: schemas.CompanyBatchRequest, db: AsyncSession = Depends(get_db)):
    for item in body.created:
        db.add(models.Company(company_name=item.company_name))
    for item in body.updated:
        company = (await db.execute(select(models.Company).where(models.Company.company_id == item.company_id))).scalar_one_or_none()
        if company:
            company.company_name = item.company_name
    for cid in body.deleted:
        await check_fk_deps(db, "Company", cid, "公司")
        await db.execute(delete(models.Company).where(models.Company.company_id == cid))
    await db.commit()
    return {"success": True}


# ── Project Codes (for company-game mapping dropdown) ──

@router.get("/project-codes")
async def list_project_codes(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(
            models.PublisherGameMapping.project_code,
            models.PublisherGameMapping.project_name,
        ).where(
            models.PublisherGameMapping.project_code.isnot(None),
            models.PublisherGameMapping.project_code != "",
        ).distinct().order_by(models.PublisherGameMapping.project_code)
    )).all()
    return {"data": [{"project_code": r.project_code, "project_name": r.project_name or ""} for r in rows]}


# ── Company Game Mappings ──

@router.get("/companies/{company_id}/games")
async def list_company_games(company_id: int, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(
            models.CompanyGameMapping.id,
            models.CompanyGameMapping.game_id,
            models.CompanyGameMapping.channel_id,
            models.ChannelCategory.channel_name,
            models.Game.game_name,
            models.PublisherGameMapping.project_code,
            models.PublisherGameMapping.project_name,
        )
        .select_from(models.CompanyGameMapping)
        .outerjoin(models.Game, models.CompanyGameMapping.game_id == models.Game.game_id)
        .outerjoin(models.ChannelCategory,
                   models.CompanyGameMapping.channel_id == models.ChannelCategory.channel_id)
        .outerjoin(
            models.PublisherGameMapping,
            models.CompanyGameMapping.game_id == models.PublisherGameMapping.game_id,
        )
        .where(models.CompanyGameMapping.company_id == company_id)
    )).all()
    seen = set()
    result = []
    for r in rows:
        key = (r.game_id, r.channel_id or 0)
        if key not in seen:
            seen.add(key)
            result.append({
                "id": r.id,
                "company_id": company_id,
                "game_id": r.game_id,
                "game_name": r.game_name or "",
                "channel_id": r.channel_id,
                "channel_name": r.channel_name or "",
                "project_code": r.project_code or "",
                "project_name": r.project_name or "",
            })
    return {"data": result}


@router.post("/companies/games/batch")
async def batch_company_games(
    body: list[schemas.CompanyGameByProject],
    db: AsyncSession = Depends(get_db),
):
    """Expand project_code → all game_ids, upsert into company_game_mapping."""
    total = await batch_save_company_games(db, body)
    return {"success": True, "game_count": total}


@router.post("/companies/games/delete-by-project")
async def delete_company_games_by_project(
    body: schemas.CompanyGameByProject,
    db: AsyncSession = Depends(get_db),
):
    """Delete all company_game_mapping rows for games under a project_code."""
    rows = (await db.execute(
        select(models.PublisherGameMapping.game_id).where(
            models.PublisherGameMapping.project_code == body.project_code,
            models.PublisherGameMapping.project_code.isnot(None),
            models.PublisherGameMapping.project_code != "",
        )
    )).all()
    game_ids = [r.game_id for r in rows if r.game_id]
    if game_ids:
        delete_where = [
            models.CompanyGameMapping.game_id.in_(game_ids),
            models.CompanyGameMapping.company_id == body.company_id,
        ]
        if body.channel_id is not None:
            delete_where.append(models.CompanyGameMapping.channel_id == body.channel_id)
        else:
            delete_where.append(models.CompanyGameMapping.channel_id.is_(None))
        await db.execute(delete(models.CompanyGameMapping).where(*delete_where))
        await db.commit()
    return {"success": True}


@router.post("/companies/games/delete")
async def delete_company_games(
    body: list[schemas.CompanyGameDelete],
    db: AsyncSession = Depends(get_db),
):
    for item in body:
        stmt = delete(models.CompanyGameMapping).where(
            models.CompanyGameMapping.company_id == item.company_id,
            models.CompanyGameMapping.game_id == item.game_id,
        )
        if item.channel_id is not None:
            stmt = stmt.where(models.CompanyGameMapping.channel_id == item.channel_id)
        else:
            stmt = stmt.where(models.CompanyGameMapping.channel_id.is_(None))
        await db.execute(stmt)
    await db.commit()
    return {"success": True}


# ── Company Game Overrides (game-level) ──


@router.get("/companies/{company_id}/projects")
async def list_company_projects(
    company_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return project-level associations for a company (grouped by project_code + channel_id)."""
    rows = (await db.execute(
        select(
            models.CompanyGameMapping.id,
            models.CompanyGameMapping.game_id,
            models.CompanyGameMapping.channel_id,
            models.ChannelCategory.channel_name,
            models.PublisherGameMapping.project_code,
            models.PublisherGameMapping.project_name,
        )
        .select_from(models.CompanyGameMapping)
        .outerjoin(
            models.PublisherGameMapping,
            models.CompanyGameMapping.game_id == models.PublisherGameMapping.game_id,
        )
        .outerjoin(
            models.ChannelCategory,
            models.CompanyGameMapping.channel_id == models.ChannelCategory.channel_id,
        )
        .where(models.CompanyGameMapping.company_id == company_id)
        .order_by(
            models.PublisherGameMapping.project_code,
            models.CompanyGameMapping.channel_id,
        )
    )).all()

    # Group by (project_code, channel_id)
    groups = {}
    for r in rows:
        key = (r.project_code or "__none__", r.channel_id or 0)
        if key not in groups:
            groups[key] = {
                "project_code": r.project_code or "",
                "project_name": r.project_name or "",
                "channel_id": r.channel_id,
                "channel_name": r.channel_name or "",
                "game_count": 0,
                "_game_ids": set(),
            }
        if r.game_id:
            groups[key]["_game_ids"].add(r.game_id)
            groups[key]["game_count"] = len(groups[key]["_game_ids"])

    result = sorted(groups.values(), key=lambda g: (g["project_code"], g["channel_name"]))
    for g in result:
        del g["_game_ids"]
    return {"data": result}


@router.get("/companies/{company_id}/project-games")
async def list_project_games(
    company_id: int, project_code: str,
    channel_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return games under a project_code with their effective company.

    For each game: whether it inherits the project-level company or has a game-level override.
    """
    # 1. Get all games under this project_code
    game_rows = (await db.execute(
        select(
            models.PublisherGameMapping.game_id,
            models.Game.game_name,
            models.PublisherGameMapping.project_code,
            models.PublisherGameMapping.project_name,
        )
        .outerjoin(models.Game, models.PublisherGameMapping.game_id == models.Game.game_id)
        .where(
            models.PublisherGameMapping.project_code == project_code,
            models.PublisherGameMapping.project_code.isnot(None),
            models.PublisherGameMapping.project_code != "",
        )
        .order_by(models.PublisherGameMapping.game_id)
    )).all()

    if not game_rows:
        return {"data": []}

    game_ids = [r.game_id for r in game_rows]

    # 2. Get the project-level company_id (Priority 3 match — used as baseline)
    #    Find a CompanyGameMapping for ANY game under this project
    proj_where = [models.CompanyGameMapping.game_id.in_(game_ids)]
    if channel_id is not None:
        proj_where.append(models.CompanyGameMapping.channel_id == channel_id)
    else:
        proj_where.append(models.CompanyGameMapping.channel_id.is_(None))
    proj_cg = (await db.execute(
        select(models.CompanyGameMapping.company_id)
        .where(*proj_where)
        .limit(1)
    )).scalar_one_or_none()
    project_company_id = proj_cg

    # 3. Get project company name
    project_company_name = None
    if project_company_id:
        project_company_name = (await db.execute(
            select(models.Company.company_name).where(models.Company.company_id == project_company_id)
        )).scalar_one_or_none()

    # 4. Get game-level mappings for these games (ALL companies)
    cg_where = [models.CompanyGameMapping.game_id.in_(game_ids)]
    if channel_id is not None:
        cg_where.append(models.CompanyGameMapping.channel_id == channel_id)
    else:
        cg_where.append(models.CompanyGameMapping.channel_id.is_(None))
    cg_rows = (await db.execute(
        select(
            models.CompanyGameMapping.id,
            models.CompanyGameMapping.game_id,
            models.CompanyGameMapping.company_id,
            models.Company.company_name,
        )
        .outerjoin(models.Company, models.CompanyGameMapping.company_id == models.Company.company_id)
        .where(*cg_where)
    )).all()
    cg_map = {}
    for cg in cg_rows:
        cg_map[cg.game_id] = {
            "mapping_id": cg.id,
            "company_id": cg.company_id,
            "company_name": cg.company_name or "",
        }

    # 5. Build result
    result = []
    for gr in game_rows:
        cg = cg_map.get(gr.game_id)
        if cg:
            effective_company_id = cg["company_id"]
            effective_company_name = cg["company_name"]
            is_override = (project_company_id is None) or (effective_company_id != project_company_id)
        else:
            effective_company_id = project_company_id
            effective_company_name = project_company_name or ""
            is_override = False

        result.append({
            "game_id": gr.game_id,
            "game_name": gr.game_name or "",
            "project_code": gr.project_code or project_code,
            "project_name": gr.project_name or "",
            "effective_company_id": effective_company_id,
            "effective_company_name": effective_company_name,
            "project_company_id": project_company_id,
            "project_company_name": project_company_name or "",
            "is_override": is_override,
            "mapping_id": cg.get("mapping_id") if cg else None,
        })

    return {"data": result}


@router.post("/companies/games/override")
async def upsert_company_game_override(
    body: schemas.CompanyGameOverride,
    db: AsyncSession = Depends(get_db),
):
    """Create or update a game-level company override."""
    await save_company_game_override(
        db, body.company_id, body.game_id,
        channel_id=body.channel_id,
    )
    return {"success": True}


@router.delete("/companies/games/override")
async def remove_company_game_override(
    body: schemas.CompanyGameOverrideDelete,
    db: AsyncSession = Depends(get_db),
):
    """Remove a game-level company override, reverting to project-level inheritance."""
    deleted = await delete_company_game_override(
        db, body.company_id, body.game_id,
        channel_id=body.channel_id,
    )
    if not deleted:
        raise HTTPException(404, "未找到对应的游戏级覆盖")
    return {"success": True}


# ── Publishers CRUD ──

@router.post("/publishers")
async def create_publisher(body: schemas.PublisherCreate, db: AsyncSession = Depends(get_db)):
    publisher = models.Publisher(publisher_name=body.publisher_name)
    db.add(publisher)
    await db.commit()
    await db.refresh(publisher)
    return {"data": {"publisher_id": publisher.publisher_id}}


@router.put("/publishers/{publisher_id}")
async def update_publisher(publisher_id: int, body: schemas.PublisherUpdate, db: AsyncSession = Depends(get_db)):
    publisher = (await db.execute(select(models.Publisher).where(models.Publisher.publisher_id == publisher_id))).scalar_one_or_none()
    if not publisher:
        raise HTTPException(404, "研发商户不存在")
    publisher.publisher_name = body.publisher_name
    await db.commit()
    return {"data": {"publisher_id": publisher_id}}


@router.delete("/publishers/{publisher_id}")
async def delete_publisher(publisher_id: int, db: AsyncSession = Depends(get_db)):
    await check_fk_deps(db, "Publisher", publisher_id, "研发商")
    await db.execute(delete(models.Publisher).where(models.Publisher.publisher_id == publisher_id))
    await db.commit()
    return {"data": {"publisher_id": publisher_id}}


@router.post("/publishers/batch")
async def batch_publishers(body: schemas.PublisherBatchRequest, db: AsyncSession = Depends(get_db)):
    for item in body.created:
        db.add(models.Publisher(publisher_name=item.publisher_name))
    for item in body.updated:
        publisher = (await db.execute(select(models.Publisher).where(models.Publisher.publisher_id == item.publisher_id))).scalar_one_or_none()
        if publisher:
            publisher.publisher_name = item.publisher_name
    for pid in body.deleted:
        await check_fk_deps(db, "Publisher", pid, "研发商")
        await db.execute(delete(models.Publisher).where(models.Publisher.publisher_id == pid))
    await db.commit()
    return {"success": True}


# ── Publisher Game Mappings (project info) ──

@router.get("/publishers/{publisher_id}/games")
async def list_publisher_games(publisher_id: int, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(models.PublisherGameMapping).where(models.PublisherGameMapping.publisher_id == publisher_id)
    )).scalars().all()
    return {"data": [{
        "id": r.id, "publisher_id": r.publisher_id, "game_id": r.game_id,
        "project_code": r.project_code, "project_name": r.project_name,
    } for r in rows]}


@router.post("/publishers/games/batch")
async def batch_publisher_games(
    body: list[schemas.PublisherGameProjectUpdate],
    db: AsyncSession = Depends(get_db),
):
    for item in body:
        mapping = (await db.execute(
            select(models.PublisherGameMapping).where(
                models.PublisherGameMapping.publisher_id == item.publisher_id,
                models.PublisherGameMapping.game_id == item.game_id,
            )
        )).scalar_one_or_none()
        if mapping:
            mapping.project_code = item.project_code
            mapping.project_name = item.project_name
        else:
            mapping = models.PublisherGameMapping(
                publisher_id=item.publisher_id,
                game_id=item.game_id,
                project_code=item.project_code,
                project_name=item.project_name,
            )
            db.add(mapping)
    await db.commit()
    return {"success": True}


@router.post("/publishers/games/delete")
async def delete_publisher_game(
    body: list[schemas.PublisherGameDelete],
    db: AsyncSession = Depends(get_db),
):
    """批量删除研发商户的游戏映射."""
    for item in body:
        await db.execute(
            delete(models.PublisherGameMapping).where(
                models.PublisherGameMapping.publisher_id == item.publisher_id,
                models.PublisherGameMapping.game_id == item.game_id,
            )
        )
    await db.commit()
    return {"success": True}


# ── Channel Categories ──

@router.get("/channel-categories")
async def list_channel_categories(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.ChannelCategory))).scalars().all()
    return {"data": [{"channel_id": r.channel_id, "channel_name": r.channel_name} for r in rows]}


# ── Channels (hierarchy tree) ──

@router.post("/channels/batch")
async def batch_channels(
    body: list[schemas.ChannelRowUpdate],
    db: AsyncSession = Depends(get_db),
):
    """批量保存渠道层级：同名则更新，否则新建"""
    logger.warning("batch_channels request: %s", [item.model_dump() for item in body])
    await batch_save_channels(db, body)
    return {"success": True}


@router.get("/channels/tree")
async def get_channel_tree(db: AsyncSession = Depends(get_db)):
    """返回渠道层级树: 渠道名称 → 后台渠道 → 二级渠道"""
    categories = (await db.execute(select(models.ChannelCategory))).scalars().all()
    tree = []
    for cat in categories:
        backends = (await db.execute(
            select(models.BackendChannel).where(models.BackendChannel.channel_id == cat.channel_id)
        )).scalars().all()
        bk_list = []
        for bk in backends:
            subs = (await db.execute(
                select(models.SubChannel).where(models.SubChannel.backend_channel_id == bk.backend_channel_id)
            )).scalars().all()
            bk_list.append({
                "backend_channel_id": bk.backend_channel_id,
                "backend_channel_name": bk.backend_channel_name,
                "sub_channels": [{"sub_channel_id": s.sub_channel_id, "sub_channel_name": s.sub_channel_name} for s in subs]
            })
        tree.append({
            "channel_id": cat.channel_id,
            "channel_name": cat.channel_name,
            "backend_channels": bk_list
        })
    return {"data": tree}


# ── Channel-Company Mapping ──


@router.get("/channel-company-mappings")
async def list_channel_company_mappings(db: AsyncSession = Depends(get_db)):
    """返回所有渠道→主体信息映射。"""
    rows = (await db.execute(
        select(
            models.ChannelCompanyMapping.channel_id,
            models.ChannelCategory.channel_name,
            models.ChannelCompanyMapping.party_info_id,
            models.PartyInfo.name.label("party_name"),
        )
        .join(models.ChannelCategory,
              models.ChannelCompanyMapping.channel_id == models.ChannelCategory.channel_id)
        .join(models.PartyInfo,
              models.ChannelCompanyMapping.party_info_id == models.PartyInfo.id)
        .order_by(models.ChannelCategory.channel_name)
    )).all()
    return {
        "data": [
            {
                "channel_id": r.channel_id,
                "channel_name": r.channel_name,
                "party_info_id": r.party_info_id,
                "party_name": r.party_name,
            }
            for r in rows
        ],
    }


@router.post("/channel-company-mappings")
async def save_channel_company_mapping(
    body: dict,  # {channel_id, party_info_id}
    db: AsyncSession = Depends(get_db),
):
    """创建或更新渠道→主体信息映射。"""
    ch_id = body.get("channel_id")
    pi_id = body.get("party_info_id")
    if not ch_id:
        raise HTTPException(400, "channel_id 不能为空")
    if not pi_id:
        existing = (await db.execute(
            select(models.ChannelCompanyMapping).where(
                models.ChannelCompanyMapping.channel_id == ch_id
            )
        )).scalar_one_or_none()
        if existing:
            await db.delete(existing)
            await db.commit()
        return {"ok": True}

    existing = (await db.execute(
        select(models.ChannelCompanyMapping).where(
            models.ChannelCompanyMapping.channel_id == ch_id
        )
    )).scalar_one_or_none()
    if existing:
        existing.party_info_id = pi_id
    else:
        db.add(models.ChannelCompanyMapping(channel_id=ch_id, party_info_id=pi_id))
    await db.commit()
    return {"ok": True}


@router.delete("/channel-company-mappings/{channel_id}")
async def delete_channel_company_mapping(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除渠道→主体信息映射。"""
    existing = (await db.execute(
        select(models.ChannelCompanyMapping).where(
            models.ChannelCompanyMapping.channel_id == channel_id
        )
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return {"ok": True}
