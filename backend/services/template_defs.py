# -*- coding: utf-8 -*-
"""Template definitions and column synonym dictionary for Excel import."""
import os as _os
import json as _json
from decimal import Decimal

from .. import models
from .field_definitions import FIELD_DEFS, get_synonym_map, infer_mapping

TEMPLATE_DEFS = {
    "games": {
        "label": "游戏信息",
        "columns": ["game_id", "game_name", "game_backend_name", "discount_rate"],
        "required": [True, True, False, True],
        "types": [str, str, str, Decimal],
        "model": models.Game,
        "unique_fields": ["game_id"],
        "fk_resolves": [],
    },
    "companies": {
        "label": "我方公司",
        "columns": ["company_name"],
        "required": [True],
        "types": [str],
        "model": models.Company,
        "unique_fields": ["company_name"],
        "fk_resolves": [],
    },
    "publishers": {
        "label": "研发商户",
        "columns": ["publisher_name"],
        "required": [True],
        "types": [str],
        "model": models.Publisher,
        "unique_fields": ["publisher_name"],
        "fk_resolves": [],
    },
    "channels": {
        "label": "渠道层级",
        "columns": ["channel_name", "backend_channel_name", "sub_channel_name"],
        "required": [True, True, True],
        "types": [str, str, str],
        "model": None,
        "unique_fields": None,
        "batch_key_fields": ["channel_name", "backend_channel_name", "sub_channel_name"],
        "fk_resolves": [],
    },
    "income_split": {
        "label": "收入分成配置",
        "columns": ["channel_name", "game_id", "split_rate", "channel_fee_rate", "tax_rate", "effective_from"],
        "required": [True, True, True, True, True, True],
        "types": [str, str, Decimal, Decimal, Decimal, str],
        "model": models.IncomeSplitConfig,
        "unique_fields": ["channel_id", "game_id"],
        "batch_key_fields": ["channel_name", "game_id"],
        "fk_resolves": [{
            "name_field": "channel_name",
            "fk_model": models.ChannelCategory, "name_col": "channel_name",
            "cache_key": "channel_categories", "target_field": "channel_id",
            "error_msg": "Channel category not found",
        }],
        "date_fields": ["effective_from", "effective_to"],
    },
    "payment_split": {
        "label": "付款分成配置",
        "columns": ["publisher_name", "game_id", "split_rate", "channel_fee_rate", "tax_rate", "fixed_fee", "effective_from"],
        "required": [True, True, True, True, True, False, True],
        "types": [str, str, Decimal, Decimal, Decimal, Decimal, str],
        "model": models.PaymentSplitConfig,
        "unique_fields": ["publisher_id", "game_id"],
        "batch_key_fields": ["publisher_name", "game_id"],
        "fk_resolves": [{
            "name_field": "publisher_name",
            "fk_model": models.Publisher, "name_col": "publisher_name",
            "cache_key": "publishers", "target_field": "publisher_id",
            "error_msg": "Publisher not found",
        }],
        "date_fields": ["effective_from", "effective_to"],
    },
    "company_game": {
        "label": "公司-游戏映射",
        "columns": ["company_name", "game_id"],
        "required": [True, True],
        "types": [str, str],
        "model": models.CompanyGameMapping,
        "unique_fields": ["company_id", "game_id"],
        "batch_key_fields": ["company_name", "game_id"],
        "fk_resolves": [{
            "name_field": "company_name",
            "fk_model": models.Company, "name_col": "company_name",
            "cache_key": "companies", "target_field": "company_id",
            "error_msg": "Company not found",
        }],
    },
    "publisher_game": {
        "label": "研发商户-游戏映射",
        "columns": ["publisher_name", "game_id", "project_code", "project_name"],
        "required": [True, True, False, False],
        "types": [str, str, str, str],
        "model": models.PublisherGameMapping,
        "unique_fields": ["publisher_id", "game_id"],
        "batch_key_fields": ["publisher_name", "game_id"],
        "fk_resolves": [{
            "name_field": "publisher_name",
            "fk_model": models.Publisher, "name_col": "publisher_name",
            "cache_key": "publishers", "target_field": "publisher_id",
            "error_msg": "Publisher not found",
        }],
    },
    "raw_transactions": {
        "label": "原始流水",
        "columns": ["backend_channel_name", "sub_channel_name", "game_id", "amount", "record_date"],
        "required": [True, True, True, True, True],
        "types": [str, str, str, Decimal, str],
        "model": models.RawSettlement,  # 聚合表 2026-06
        "unique_fields": None,
        "fk_resolves": [{
            "name_field": "backend_channel_name",
            "fk_model": models.BackendChannel, "name_col": "backend_channel_name",
            "cache_key": "backend_channels", "target_field": "backend_channel_id",
            "error_msg": "Backend channel not found",
        }],
        "raw_txn": True,
    },
    "deductions": {
        "label": "扣除项目",
        "columns": ["channel_name", "game_id", "month", "vouchers", "test", "welfare", "bad_debt"],
        "required": [True, True, True, True, True, True, True],
        "types": [str, str, str, Decimal, Decimal, Decimal, Decimal],
        "model": models.Deduction,
        "unique_fields": ["channel_id", "game_id", "month"],
        "batch_key_fields": ["channel_name", "game_id", "month"],
        "fk_resolves": [{
            "name_field": "channel_name",
            "fk_model": models.ChannelCategory, "name_col": "channel_name",
            "cache_key": "channel_categories", "target_field": "channel_id",
            "error_msg": "Channel category not found",
        }],
    },
}

FLEXIBLE_FIELD_DEFS = [(f["key"], f["label"], f["is_money"], f["is_pct"]) for f in FIELD_DEFS]

_SYNONYM_DICT_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "data", "column_synonyms.json")
_default_synonyms = get_synonym_map()
_COLUMN_SYNONYMS: dict[str, list[str]] = {}
# Always start with defaults; user dictionary overrides/adds specific fields
_COLUMN_SYNONYMS.update(_default_synonyms)
if _os.path.exists(_SYNONYM_DICT_PATH):
    try:
        with open(_SYNONYM_DICT_PATH, "r", encoding="utf-8") as _f:
            _COLUMN_SYNONYMS.update(_json.load(_f))
    except Exception:
        pass


def infer_column_mapping(headers):
    """Column inference using persisted synonym dictionary (user-editable)."""
    return infer_mapping(headers, synonyms=_COLUMN_SYNONYMS)
