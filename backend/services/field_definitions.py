"""Canonical financial field definitions — single source of truth.

Each field: {key, label, is_money, is_pct, synonyms}
Used by: template_defs, bill_service, column inference, frontend via API.
"""
from difflib import SequenceMatcher

FIELD_DEFS: list[dict] = [
    {"key": "game_id",          "label": "游戏编号",     "is_money": False, "is_pct": False,
     "synonyms": ["游戏编号", "游戏ID", "游戏代码", "编号", "代码", "ID", "产品编号", "项目编号"]},
    {"key": "game_name",        "label": "游戏名称",     "is_money": False, "is_pct": False,
     "synonyms": ["游戏名称", "游戏名", "游戏", "产品名称", "项目名称", "应用名称", "商品名称", "产品", "项目", "应用", "商品", "名称", "游戏名字"]},
    {"key": "raw_revenue",      "label": "原始流水",     "is_money": True,  "is_pct": False,
     "synonyms": ["充值金额", "充值全额", "充值总额", "流水金额", "总流水", "收入金额", "总收入", "月流水", "原始流水", "充值额", "金额合计", "总金额", "全额", "计费金额", "充值", "流水", "收入", "金额"]},
    {"key": "real_revenue",     "label": "真实流水",     "is_money": True,  "is_pct": False,
     "synonyms": ["真实流水", "实际收入", "实收金额", "实收", "净收入", "实际流水"]},
    {"key": "vouchers",         "label": "代金券",       "is_money": True,  "is_pct": False,
     "synonyms": ["代金券金额", "代金券", "安全券金额", "安全券全额", "安全券", "券金额", "代金券额", "优惠券"]},
    {"key": "test",             "label": "测试费",       "is_money": True,  "is_pct": False,
     "synonyms": ["测试费金额", "测试费", "测试金额", "测试", "测试费用"]},
    {"key": "welfare",          "label": "福利币",       "is_money": True,  "is_pct": False,
     "synonyms": ["福利币金额", "福利币", "福利币全额", "福利", "福利金额"]},
    {"key": "bad_debt",         "label": "坏账",         "is_money": True,  "is_pct": False,
     "synonyms": ["坏账金额", "坏账", "坏帐", "坏帐金额", "坏账准备", "坏账损失"]},
    {"key": "total_deductions", "label": "扣除合计",     "is_money": True,  "is_pct": False,
     "synonyms": ["扣除合计", "扣款合计", "扣除总额", "总扣除", "合计扣除", "扣款总额"]},
    {"key": "split_rate",       "label": "分成比例",     "is_money": False, "is_pct": True,
     "synonyms": ["分成比例", "分成", "分成比", "抽成比例", "分成率", "比例", "抽成"]},
    {"key": "channel_fee_rate", "label": "通道费率",     "is_money": False, "is_pct": True,
     "synonyms": ["通道费率", "渠道费率", "手续费率", "费率", "手续费", "通道费"]},
    {"key": "tax_rate",         "label": "税率",         "is_money": False, "is_pct": True,
     "synonyms": ["税率", "税", "税费", "税率比例", "税费比例", "税点", "增值税率"]},
    {"key": "fixed_fee",        "label": "固定费用",     "is_money": True,  "is_pct": False,
     "synonyms": ["固定费用", "固定费", "保底金", "保底金额", "保底", "固定金额"]},
    {"key": "settlement_amount","label": "结算金额",     "is_money": True,  "is_pct": False,
     "synonyms": ["结算金额", "实际结算金额", "实结金额", "结算款", "结算", "分成金额", "分成后金额", "实结", "应结金额", "结算总额"]},
    {"key": "month",            "label": "月份",         "is_money": False, "is_pct": False,
     "synonyms": ["月份", "月", "对账月份", "结算月份", "账单月份", "计费月份", "日期", "计费日期", "时间", "周期", "账期", "对账周期"]},
    {"key": "ignore",           "label": "忽略此列",     "is_money": False, "is_pct": False,
     "synonyms": []},
]

# Keyword hints for fuzzy matching (lowercase chars)
_FIELD_KEYWORDS: dict[str, str] = {
    "游戏": "game_name", "名称": "game_name", "产品": "game_name",
    "项目": "game_name", "应用": "game_name", "商品": "game_name",
    "编号": "game_id", "id": "game_id", "代码": "game_id",
    "流水": "raw_revenue", "充值": "raw_revenue", "总额": "raw_revenue",
    "全额": "raw_revenue", "总金额": "raw_revenue", "总收入": "raw_revenue",
    "收入": "raw_revenue", "实际收入": "real_revenue", "实收": "real_revenue",
    "金额": "raw_revenue",
    "代金券": "vouchers", "券": "vouchers", "安全券": "vouchers",
    "测试": "test", "测试费": "test",
    "福利": "welfare", "福利币": "welfare",
    "坏账": "bad_debt",
    "扣除": "total_deductions", "扣款": "total_deductions",
    "分成": "split_rate", "比例": "split_rate",
    "费率": "channel_fee_rate", "通道": "channel_fee_rate",
    "税": "tax_rate", "税率": "tax_rate",
    "结算": "settlement_amount", "结算金额": "settlement_amount",
    "实结": "settlement_amount", "分成后": "settlement_amount",
    "月份": "month", "月": "month", "日期": "month", "周期": "month",
}


def get_synonym_map() -> dict[str, list[str]]:
    """Build {field_key: [synonyms]} dict for column inference."""
    return {f["key"]: f["synonyms"] for f in FIELD_DEFS if f["key"] != "ignore"}


def get_bill_columns() -> list[tuple[str, str, bool, bool]]:
    """Bill-compatible column list: (label, key, is_money, is_pct)."""
    return [(f["label"], f["key"], f["is_money"], f["is_pct"])
            for f in FIELD_DEFS if f["key"] not in ("ignore", "month")]


def fuzzy_score(a: str, b: str) -> float:
    """0-100 fuzzy match between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100


def infer_mapping(headers: list[str], synonyms: dict[str, list[str]] | None = None) -> list[dict]:
    """Infer column mapping from header row. Returns [{col_index, header, suggested_field, confidence, candidates}].

    synonyms: optional override for get_synonym_map() (e.g., user-customized dictionary).
    """
    std_fields = [(f["key"], f["label"]) for f in FIELD_DEFS if f["key"] != "ignore"]
    if synonyms is None:
        synonyms = get_synonym_map()
    results = []

    for ci, header in enumerate(headers):
        if not header or not header.strip():
            results.append({"col_index": ci, "header": header or "", "suggested_field": "ignore", "confidence": 0, "candidates": []})
            continue

        h = header.strip()
        candidates = []

        # Pass 1: exact synonym match
        exact_field = None
        for field_key, syns in synonyms.items():
            if h in syns:
                exact_field = field_key
                break

        if exact_field:
            for field_key, label in std_fields:
                score = 100.0 if field_key == exact_field else fuzzy_score(h, label)
                candidates.append({"field": field_key, "score": round(score, 1)})
            candidates.sort(key=lambda x: x["score"], reverse=True)
            results.append({"col_index": ci, "header": h, "suggested_field": exact_field, "confidence": 100.0,
                            "candidates": [{"field": c["field"], "score": c["score"]} for c in candidates[:5]]})
            continue

        # Pass 2: fuzzy + keyword fallback
        for field_key, label in std_fields:
            score = fuzzy_score(h, label)
            candidates.append({"field": field_key, "score": round(score, 1)})

        matched_kw = set()
        for kw, field_key in _FIELD_KEYWORDS.items():
            if kw in h.lower():
                for c in candidates:
                    if c["field"] == field_key:
                        c["score"] = min(100, c["score"] + 20)
                        matched_kw.add(field_key)
        for c in candidates:
            if c["field"] in matched_kw and c["score"] < 55:
                c["score"] = max(c["score"], 55)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        best_field = best["field"] if best["score"] >= 35 else "ignore"
        results.append({"col_index": ci, "header": h, "suggested_field": best_field, "confidence": round(best["score"], 1),
                        "candidates": [{"field": c["field"], "score": c["score"]} for c in candidates[:5]]})

    return results
