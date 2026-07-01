"""Tests for column inference engine: fuzzy_score, infer_mapping, get_synonym_map."""
import pytest
from backend.services.field_definitions import (
    fuzzy_score,
    infer_mapping,
    get_synonym_map,
    FIELD_DEFS,
)


# ═══════════════════════════════════════════════════════════════
# fuzzy_score
# ═══════════════════════════════════════════════════════════════

class TestFuzzyScore:
    """Tests for fuzzy_score — pure string similarity function."""

    def test_exact_match(self):
        assert fuzzy_score("游戏名称", "游戏名称") == 100.0

    def test_case_insensitive(self):
        assert fuzzy_score("GAME_NAME", "game_name") == 100.0

    def test_partial_match(self):
        score = fuzzy_score("游戏名称", "游戏")
        assert 0 < score < 100

    def test_no_match(self):
        score = fuzzy_score("abc", "xyz")
        assert score < 50  # very low similarity

    def test_returns_float(self):
        score = fuzzy_score("a", "b")
        assert isinstance(score, float)

    def test_symmetric(self):
        """Similarity should be symmetric."""
        assert fuzzy_score("abc", "abd") == fuzzy_score("abd", "abc")


# ═══════════════════════════════════════════════════════════════
# get_synonym_map
# ═══════════════════════════════════════════════════════════════

class TestGetSynonymMap:
    """Tests for get_synonym_map."""

    def test_returns_dict(self):
        result = get_synonym_map()
        assert isinstance(result, dict)

    def test_excludes_ignore(self):
        result = get_synonym_map()
        assert "ignore" not in result

    def test_includes_all_standard_fields(self):
        result = get_synonym_map()
        for f in FIELD_DEFS:
            if f["key"] != "ignore":
                assert f["key"] in result, f"Missing {f['key']} in synonym map"
                assert isinstance(result[f["key"]], list)

    def test_game_name_has_synonyms(self):
        result = get_synonym_map()
        assert "游戏名称" in result["game_name"]
        assert "游戏" in result["game_name"]

    def test_raw_revenue_has_money_synonyms(self):
        result = get_synonym_map()
        assert "充值金额" in result["raw_revenue"]
        assert "流水" in result["raw_revenue"]


# ═══════════════════════════════════════════════════════════════
# infer_mapping
# ═══════════════════════════════════════════════════════════════

class TestInferMapping:
    """Tests for infer_mapping — the column-to-field inference engine."""

    def test_exact_synonym_match(self):
        """A header that is an exact synonym maps with 100% confidence."""
        results = infer_mapping(["游戏名称"])
        assert results[0]["suggested_field"] == "game_name"
        assert results[0]["confidence"] == 100.0
        assert results[0]["col_index"] == 0

    def test_exact_synonym_alt(self):
        """Another exact synonym for a different field."""
        results = infer_mapping(["游戏ID"])
        assert results[0]["suggested_field"] == "game_id"
        assert results[0]["confidence"] == 100.0

    def test_exact_money_synonym(self):
        """Exact match for money field synonym."""
        results = infer_mapping(["充值金额"])
        assert results[0]["suggested_field"] == "raw_revenue"
        assert results[0]["confidence"] == 100.0

    def test_fuzzy_fallback(self):
        """When no exact synonym, fuzzy matching with keyword boost is used."""
        results = infer_mapping(["游戏名字"])  # "游戏名字" is NOT in synonyms for game_name
        # Should still map to game_name via fuzzy + keyword boost
        assert results[0]["suggested_field"] == "game_name"
        assert results[0]["confidence"] >= 35

    def test_empty_header(self):
        """Empty header maps to ignore with 0 confidence."""
        results = infer_mapping([""])
        assert results[0]["suggested_field"] == "ignore"
        assert results[0]["confidence"] == 0

    def test_whitespace_header(self):
        """Whitespace-only header maps to ignore."""
        results = infer_mapping(["   "])
        assert results[0]["suggested_field"] == "ignore"
        assert results[0]["confidence"] == 0

    def test_unknown_column_below_threshold(self):
        """Totally unknown column below fuzzy threshold maps to ignore."""
        results = infer_mapping(["xyzzy12345"])  # not matching anything
        assert results[0]["suggested_field"] == "ignore"

    def test_multiple_headers(self):
        """Multiple headers are all inferred."""
        results = infer_mapping(["游戏名称", "充值金额", "代金券金额"])
        assert len(results) == 3
        assert results[0]["suggested_field"] == "game_name"
        assert results[1]["suggested_field"] == "raw_revenue"
        assert results[2]["suggested_field"] == "vouchers"

    def test_candidates_include_top5(self):
        """Each result includes up to 5 candidates with scores."""
        results = infer_mapping(["流水金额"])
        assert len(results[0]["candidates"]) <= 5
        assert len(results[0]["candidates"]) >= 1
        assert "field" in results[0]["candidates"][0]
        assert "score" in results[0]["candidates"][0]

    def test_ignore_header_exact_match(self):
        """Header '忽略此列' is in the ignore synonyms? No — ignore has empty synonyms.
        But if it fuzzy-matches below threshold, it goes to ignore."""
        results = infer_mapping(["忽略此列"])
        # "忽略此列" is the label for "ignore" field, fuzzy matching should match it
        r = results[0]
        # With fuzzy matching, "忽略此列" is literally the field label for "ignore"
        # Since FIELD_DEFS includes "ignore" with label "忽略此列",
        # fuzzy_score("忽略此列", "忽略此列") = 100.0
        # But infer_mapping filters out "ignore" from std_fields list:
        #   std_fields = [(f["key"], f["label"]) for f in FIELD_DEFS if f["key"] != "ignore"]
        # So "ignore" is never suggested via fuzzy matching — it can only be the fallback
        assert r["suggested_field"] in ("game_name", "ignore")  # fuzzy may match game_name with low score

    def test_custom_synonyms_override(self):
        """Custom synonyms dict can override or extend the default."""
        custom = {"raw_revenue": ["我的自定义列名"], "game_name": ["游戏名称"]}
        results = infer_mapping(["我的自定义列名"], synonyms=custom)
        assert results[0]["suggested_field"] == "raw_revenue"
        assert results[0]["confidence"] == 100.0

    def test_keyword_boost_income(self):
        """Header containing '收入' keyword boosts raw_revenue score."""
        results = infer_mapping(["实际收入额"])
        # Should boost raw_revenue due to "收入" keyword
        assert results[0]["suggested_field"] == "raw_revenue"

    def test_keyword_boost_tax(self):
        """Header containing '税' keyword boosts tax_rate."""
        results = infer_mapping(["增值税"])
        assert results[0]["suggested_field"] == "tax_rate"

    def test_col_index_preserved(self):
        """col_index reflects the original position."""
        results = infer_mapping(["列A", "列B", "列C"])
        assert results[0]["col_index"] == 0
        assert results[1]["col_index"] == 1
        assert results[2]["col_index"] == 2

    def test_header_stripped(self):
        """Leading/trailing whitespace on headers is stripped."""
        results = infer_mapping(["  游戏名称  "])
        assert results[0]["header"] == "游戏名称"
        assert results[0]["suggested_field"] == "game_name"
