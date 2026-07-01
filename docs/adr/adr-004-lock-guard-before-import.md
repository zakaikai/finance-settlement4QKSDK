# ADR-004: Lock Guard Before Import

**Status:** Accepted (2026-06-01)

## Context

After the lock system was introduced, flexible import could potentially overwrite locked data. The import pipeline needed a mechanism to protect locked settlements from being modified by external data ingestion.

## Decision

Flexible import includes a **lock guard**: before any write operation, it queries `ChannelLock` for all target `(channel_id, game_id, month)` keys. If any key has a non-null `locked_real_revenue` or `locked_settlement_amount`, the **entire import is rejected** with a descriptive error message.

This is a **read-only check** — the import reads lock data for the guard but never writes to lock tables.

## Consequences

**Positive:**
- Locked values cannot be silently overwritten by flexible import
- Clear error message tells user exactly which (channel, game, month) keys are locked
- Clean separation: import module reads locks (guard) but doesn't write them

**Negative / Known Gaps:**
- **Race condition**: Guard check happens outside the write transaction. Between check and write, a lock could theoretically be created. Accepted risk — single-user system.
- **Template import**: Has no lock guard. Accepted — template import operates on RawTransaction (different data path) and its ChannelSettlement sync reads lock values correctly.

## References
- `backend/services/flexible_import.py` — lock guard query (lines ~158-192)
- `backend/services/lock_service.py` — `apply_lock()`, `remove_lock()`
