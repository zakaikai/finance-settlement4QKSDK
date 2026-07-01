"""Company name resolution — 4-tier priority logic, shared by all settlement modules.

Deep module: two interfaces for the same resolution logic.
  build_company_name_subquery  — SQL scalar subquery (for inline use in queries)
  resolve_companies_batch      — Python batch dict (for snapshot/aggregation)
Both follow the same priority chain:
  1. (game_id, channel_id) exact match
  2. (game_id, channel_id IS NULL) fallback
  3. project_code fallback
  4. channel_company_mapping → PartyInfo (channel-side only, last resort)
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models


def build_company_name_subquery(game_table, channel_table=None):
    """Return a SQL scalar subquery resolving company_name for a game row.

    Priority 1: CompanyGameMapping (game_id, channel_id) exact match
    Priority 2: CompanyGameMapping (game_id, channel_id IS NULL) fallback
    Priority 3: project_code fallback
    Priority 4: channel_company_mapping → PartyInfo (channel-side only)

    Usage:
        company_subq = build_company_name_subquery(models.Game, models.RawSettlement)
        stmt = select(..., company_subq.label("company_name"), ...)
    """
    ch_col = channel_table.channel_id if channel_table is not None else None

    target_project = (
        select(models.PublisherGameMapping.project_code)
        .where(models.PublisherGameMapping.game_id == game_table.game_id)
        .limit(1)
        .correlate(game_table)
        .scalar_subquery()
    )

    # Priority 1: exact (game_id, channel_id) match
    pri1 = (
        select(models.Company.company_name)
        .select_from(models.CompanyGameMapping)
        .join(models.Company, models.CompanyGameMapping.company_id == models.Company.company_id)
        .where(models.CompanyGameMapping.game_id == game_table.game_id)
    )
    correlate_tables = [game_table]
    if ch_col is not None:
        pri1 = pri1.where(models.CompanyGameMapping.channel_id == ch_col)
        correlate_tables.append(channel_table)
    pri1 = pri1.limit(1).correlate(*correlate_tables).scalar_subquery()

    # Priority 2: (game_id, channel_id IS NULL) fallback
    pri2 = (
        select(models.Company.company_name)
        .select_from(models.CompanyGameMapping)
        .join(models.Company, models.CompanyGameMapping.company_id == models.Company.company_id)
        .where(
            models.CompanyGameMapping.game_id == game_table.game_id,
            models.CompanyGameMapping.channel_id.is_(None),
        )
        .limit(1)
        .correlate(game_table)
        .scalar_subquery()
    )

    # Priority 3: project fallback
    pri3 = (
        select(models.Company.company_name)
        .select_from(models.Company)
        .where(models.Company.company_id.in_(
            select(models.CompanyGameMapping.company_id)
            .select_from(models.CompanyGameMapping)
            .join(models.PublisherGameMapping,
                  models.CompanyGameMapping.game_id == models.PublisherGameMapping.game_id)
            .where(
                models.PublisherGameMapping.project_code == target_project,
                models.PublisherGameMapping.project_code.isnot(None),
                models.PublisherGameMapping.project_code != "",
            )
            .limit(1)
            .scalar_subquery()
        ))
        .limit(1)
        .scalar_subquery()
    )

    # Priority 4: channel_company_mapping → PartyInfo (last resort, channel-side only)
    pri4 = None
    if ch_col is not None:
        pri4 = (
            select(models.PartyInfo.name)
            .select_from(models.ChannelCompanyMapping)
            .join(models.PartyInfo,
                  models.ChannelCompanyMapping.party_info_id == models.PartyInfo.id)
            .where(models.ChannelCompanyMapping.channel_id == ch_col)
            .limit(1)
            .correlate(channel_table)
            .scalar_subquery()
        )

    coalesce_args = (pri1, pri2, pri3, pri4) if pri4 is not None else (pri1, pri2, pri3)
    return select(func.coalesce(*coalesce_args)).scalar_subquery()


async def resolve_companies_batch(
    db: AsyncSession,
    game_ids: list[str],
    channel_id: int | None = None,
) -> dict[str, tuple[int | None, str]]:
    """Return {game_id: (company_id, company_name)} with 4-tier priority.

    Priority chain (when channel_id provided):
      1. (game_id, channel_id) exact match  [CompanyGameMapping]
      2. (game_id, channel_id IS NULL) fallback  [CompanyGameMapping]
      3. project_code fallback  [PublisherGameMapping → CompanyGameMapping]
      4. channel_company_mapping → PartyInfo  [channel-side only, last resort]
    Without channel_id: NULL fallback and project fallback only.

    Used by snapshot_from_locks for ARAP aggregation.
    """
    comp_map: dict[str, tuple[int, str]] = {}
    if not game_ids:
        return comp_map

    # Priority 1: (game_id, channel_id) exact
    if channel_id is not None:
        exact_rows = (await db.execute(
            select(models.CompanyGameMapping.game_id,
                   models.CompanyGameMapping.company_id,
                   models.Company.company_name)
            .join(models.Company, models.CompanyGameMapping.company_id == models.Company.company_id)
            .where(models.CompanyGameMapping.game_id.in_(game_ids),
                   models.CompanyGameMapping.channel_id == channel_id)
        )).all()
        for r in exact_rows:
            if r.game_id not in comp_map:
                comp_map[r.game_id] = (r.company_id, r.company_name)

    # Priority 2: (game_id, channel_id IS NULL) fallback
    unmatched = [g for g in game_ids if g not in comp_map]
    if unmatched:
        fallback_rows = (await db.execute(
            select(models.CompanyGameMapping.game_id,
                   models.CompanyGameMapping.company_id,
                   models.Company.company_name)
            .join(models.Company, models.CompanyGameMapping.company_id == models.Company.company_id)
            .where(models.CompanyGameMapping.game_id.in_(unmatched),
                   models.CompanyGameMapping.channel_id.is_(None))
        )).all()
        for r in fallback_rows:
            if r.game_id not in comp_map:
                comp_map[r.game_id] = (r.company_id, r.company_name)

    # Priority 3: project_code fallback
    unmatched = [g for g in game_ids if g not in comp_map]
    if unmatched:
        proj_rows = (await db.execute(
            select(models.PublisherGameMapping.game_id,
                   models.PublisherGameMapping.project_code)
            .where(models.PublisherGameMapping.game_id.in_(unmatched),
                   models.PublisherGameMapping.project_code.isnot(None),
                   models.PublisherGameMapping.project_code != "")
        )).all()
        gid_to_project = {r.game_id: r.project_code for r in proj_rows}
        if gid_to_project:
            proj_set = set(gid_to_project.values())
            fb_rows = (await db.execute(
                select(models.PublisherGameMapping.project_code,
                       models.CompanyGameMapping.company_id,
                       models.Company.company_name)
                .select_from(models.PublisherGameMapping)
                .join(models.CompanyGameMapping,
                      models.PublisherGameMapping.game_id == models.CompanyGameMapping.game_id)
                .join(models.Company,
                      models.CompanyGameMapping.company_id == models.Company.company_id)
                .where(models.PublisherGameMapping.project_code.in_(proj_set),
                       models.PublisherGameMapping.project_code.isnot(None),
                       models.PublisherGameMapping.project_code != "")
            )).all()
            proj_to_company = {}
            for r in fb_rows:
                if r.project_code not in proj_to_company:
                    proj_to_company[r.project_code] = (r.company_id, r.company_name)
            for gid, proj in gid_to_project.items():
                if proj in proj_to_company and gid not in comp_map:
                    comp_map[gid] = proj_to_company[proj]

    # Priority 4: channel_company_mapping → PartyInfo (channel-side only)
    unmatched = [g for g in game_ids if g not in comp_map]
    if channel_id is not None and unmatched:
        party_row = (await db.execute(
            select(models.PartyInfo.name)
            .select_from(models.ChannelCompanyMapping)
            .join(models.PartyInfo,
                  models.ChannelCompanyMapping.party_info_id == models.PartyInfo.id)
            .where(models.ChannelCompanyMapping.channel_id == channel_id,
                   models.PartyInfo.party_type == 'our_company')
            .limit(1)
        )).scalar_one_or_none()
        if party_row:
            for gid in unmatched:
                comp_map[gid] = (None, party_row)

    return comp_map
