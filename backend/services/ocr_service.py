"""OCR result matching — fuzzy-match game names against DB using difflib (stdlib).

Multi-pass cascade:
  1. Game name fuzzy match → top-3 candidates
  2. Monthly amount consistency scoring
  3. Split ratio scoring
  4. Settlement amount as final tiebreaker
"""
from difflib import SequenceMatcher
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from .. import models


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100


# ── Similarity cache: key=(name_lower, db_name_lower) → score ──
_sim_cache: dict[tuple[str, str], float] = {}


def _cached_similarity(name: str, db_name: str) -> float:
    """Memoized difflib similarity — huge savings for large imports with repeated game names."""
    key = (name.lower().strip(), db_name.lower().strip())
    if key not in _sim_cache:
        _sim_cache[key] = SequenceMatcher(None, key[0], key[1]).ratio() * 100
    return _sim_cache[key]


async def get_game_dictionary(db: AsyncSession) -> list[dict]:
    """Return all game names for OCR dictionary / post-processing."""
    rows = (await db.execute(select(models.Game.game_id, models.Game.game_name))).all()
    return [{"game_id": r.game_id, "game_name": r.game_name} for r in rows]


async def match_game_names(
    db: AsyncSession,
    names: list[str],
    context: list[dict] | None = None,
) -> list[dict]:
    """Fuzzy-match each candidate name against games table.

    Args:
        names: Raw OCR game name candidates.
        context: Optional per-candidate context dicts with keys:
            amount, ratio, settlement_amount.
            Used for multi-pass disambiguation when name match is ambiguous.

    Returns [{candidate, candidates: [{game_id, game_name, score}],
             matched_game_id, matched_game_name, confidence, status}, …]
    status: "high" (≥90%), "medium" (≥70%), "low" (<70%), "none"
    """
    rows = (await db.execute(select(models.Game))).scalars().all()
    db_names = [(g.game_id, g.game_name) for g in rows]

    # ── Fetch historical amount stats per game for context scoring ──
    amount_stats = {}
    # raw_transactions 已废止，行级 amount stats 不再可用
    amount_stats = {}

    # ── Deduplicate names: only match each unique name once ──
    unique_names: list[str] = list(dict.fromkeys(names))  # preserve order, dedup
    name_to_result: dict[str, dict] = {}

    for name in unique_names:
        if not name or not name.strip():
            name_to_result[name or ""] = {
                "candidate": name or "",
                "candidates": [],
                "matched_game_id": None,
                "matched_game_name": None,
                "confidence": 0,
                "status": "none",
            }
            continue

        # ── Pass 1: game name similarity — get top-3 (using cached similarity) ──
        scored = [(_cached_similarity(name, dn), gid, dn) for gid, dn in db_names]
        scored.sort(key=lambda x: x[0], reverse=True)
        top3 = scored[:3]

        # Context scoring uses the first occurrence's context
        first_idx = names.index(name) if name in names else 0
        ctx = (context or [None] * len(names))[first_idx] if first_idx < len(context or []) else None

        # ── Pass 2-4: context scoring for ambiguous matches ──
        if ctx and len(top3) >= 2 and (top3[0][0] - top3[1][0]) < 15:
            top3 = _rescored_with_context(top3, ctx, amount_stats)

        best = top3[0]
        conf, gid, gname = best
        if conf >= 90:
            status = "high"
        elif conf >= 70:
            status = "medium"
        else:
            status = "low"

        name_to_result[name] = {
            "candidate": name.strip(),
            "candidates": [
                {"game_id": gid, "game_name": gname, "score": round(sc, 1)}
                for sc, gid, gname in top3
            ],
            "matched_game_id": gid,
            "matched_game_name": gname,
            "confidence": round(conf, 1),
            "status": status,
        }

    # ── Map results back to original names order ──
    results = [name_to_result.get(name, name_to_result.get("", {
        "candidate": name or "",
        "candidates": [],
        "matched_game_id": None,
        "matched_game_name": None,
        "confidence": 0,
        "status": "none",
    })) for name in names]

    return results


def _rescored_with_context(top3, ctx, amount_stats):
    """Multi-pass rescoring using amount → ratio → settlement.

    Adjusts name-similarity scores by up to ±10 based on context consistency.
    """
    ocr_amount = _parse_float(ctx.get("amount"))
    ocr_ratio = _parse_float(ctx.get("ratio"))
    ocr_settlement = _parse_float(ctx.get("settlement_amount"))

    rescored = []
    for score, gid, gname in top3:
        bonus = 0.0

        # Pass 2: amount consistency (max ±6)
        if ocr_amount and gid in amount_stats:
            expected = amount_stats[gid]
            if expected > 0:
                ratio_val = min(ocr_amount, expected) / max(ocr_amount, expected)
                bonus += ratio_val * 6.0

        # Pass 3: ratio plausibility (max ±3)
        if ocr_ratio is not None and 0 < ocr_ratio <= 1:
            bonus += 1.5  # having a valid ratio is a mild positive signal

        # Pass 4: settlement consistency (max ±1)
        if ocr_settlement is not None and ocr_amount:
            expected_stl = ocr_amount * (ocr_ratio or 0.3)
            if expected_stl > 0:
                stl_ratio = min(ocr_settlement, expected_stl) / max(ocr_settlement, expected_stl)
                bonus += stl_ratio * 1.0

        rescored.append((score + bonus, gid, gname))

    rescored.sort(key=lambda x: x[0], reverse=True)
    return rescored


def _parse_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None
