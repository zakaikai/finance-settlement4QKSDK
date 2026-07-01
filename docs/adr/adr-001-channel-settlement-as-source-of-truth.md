# ADR-001: ChannelSettlement as Single Source of Truth

**Status:** Accepted (2026-06-01)

## Context

Previously, settlement queries aggregated `RawTransaction` rows on-the-fly with GROUP BY (channel, game, month). `SettlementSnapshot` stored lock-time formula inputs separately. This caused:

- **Inconsistency**: RawTransaction edits required re-aggregation that could drift from snapshot data.
- **N+1 reads**: Each settlement query scanned RawTransaction rows rather than a precomputed table.
- **Dual truth**: Formula inputs lived in both RawTransaction (raw_revenue) and SettlementSnapshot (discount_rate, split_rate at lock time), making reconciliation difficult.

## Decision

Created `ChannelSettlement` wide table at `(channel_id, game_id, month)` granularity. All formula inputs and outputs are stored in one row:

| Column | Source |
|--------|--------|
| `raw_revenue` | Aggregated from RawTransaction (template import) or flex import |
| `discount_rate` | Game table |
| `total_deductions` | Deduction table (vouchers+test+welfare+bad_debt) |
| `split_rate`, `channel_fee_rate`, `tax_rate` | IncomeSplitConfig (date-range effective) |
| `real_revenue`, `settlement_amount` | Formula output (with lock override) |
| `locked_real_revenue`, `locked_settlement_amount` | ChannelLock table (redundant copy for query perf) |

All write paths (template import, flexible import, lock/unlock) sync this table. All settlement queries read from this single table.

## Consequences

**Positive:**
- O(1) reads per (channel, game, month) — no RawTransaction aggregation at query time
- Lock values visible without JOINing lock tables
- `SettlementSnapshot` fully deprecated and removed

**Negative:**
- Write amplification: every import/config-change/lock writes to ChannelSettlement
- Sync logic must be consistent across all write paths
- Trade-off: redundant lock columns stored in both ChannelLock and ChannelSettlement

## References
- `backend/models.py` — `ChannelSettlement` class
- `backend/database.py` — `init_db()` migration populating CS from RawTransaction
- `backend/services/settlement_formula.py` — `compute()` pure function
