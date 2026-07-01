# ADR-002: 3D Unique Key Rule

**Status:** Accepted (2026-06-01)

## Context

`Deduction`, `ChannelLock`, `PublisherLock`, `ChannelSettlement` all needed unique identification. The project initially used `(game_id, month)` 2D keys in some query contexts, which leaked into channel-level queries when patterns were copied — causing cross-channel data contamination.

## Decision

All channel-side settlement entities use `(channel_id, game_id, month)` as their unique key. Publisher-side entities use `(publisher_id, game_id, month)`. Enforced via `UniqueConstraint` in SQLAlchemy models and verified in all query WHERE clauses.

| Table | Unique Key |
|-------|-----------|
| `deductions` | `(channel_id, game_id, month)` |
| `channel_locks` | `(channel_id, game_id, month)` |
| `publisher_locks` | `(publisher_id, game_id, month)` |
| `channel_settlements` | `(channel_id, game_id, month)` |

## Consequences

**Positive:**
- Consistent lookup pattern: `WHERE channel_id=? AND game_id=? AND month=?`
- No cross-channel data leaks in queries
- `hydrate_formula_input()` uses the same key pattern for both channel and publisher paths

**Negative:**
- Changing `game_id` requires cascade updates across all tables
- `RawTransaction` uses `(sub_channel_id, game_id, record_date)` — not naturally covered, requiring aggregation into `ChannelSettlement`

## Known Exception

Payment (publisher-side) queries intentionally use `(game_id, month)` 2D keys for Deduction aggregation — this is legal cross-channel aggregation for publisher settlement, not a bug. These queries are clearly marked as publisher-context-only.

## References
- Memory: `dedup-key-dimension.md`
- `backend/models.py` — `UniqueConstraint` definitions
- `backend/services/settlement_service.py` — `query_payment_settlement()` publisher-path 2D key
