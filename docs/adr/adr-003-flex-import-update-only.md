# ADR-003: Flex Import UPDATE-Only Rule

**Status:** Accepted (2026-06-01), Amended (2026-06-02)

## Context

Flexible import processes arbitrary channel billing statements. Users upload the same channel's data multiple times. Creating new rows on each import would cause duplicate accumulation and violate the principle that flex import corrects existing data, not creates new entities.

## Decision

Flexible import only UPDATEs existing rows. It never creates new rows in any table:

| Entity | Behavior |
|--------|----------|
| **Deduction** | UPDATE existing. Skip (with log + counter) if no row exists |
| **ChannelSettlement** | UPDATE existing. Skip (with log + counter) if no row exists |
| **IncomeSplitConfig** | UPSERT via `_save_income_split_config()` (date-range aware) |
| **ChannelLock** | Read-only — flex import never writes to lock tables |

## 2026-06-02 Amendment

Originally, `ChannelSettlement` allowed INSERT when no existing row was found. This violated the UPDATE-only rule. Fixed: ChannelSettlement now also skips non-existent rows. The return value includes `skipped_settlements` to report skipped rows.

## Consequences

**Positive:**
- Import is idempotent — re-importing the same file produces the same result
- No duplicate Deduction/ChannelSettlement rows
- Flex import cannot accidentally create data where none existed (template import handles initial data creation)

**Negative:**
- Channels missing a Deduction row must first populate it via template import or manual entry
- Users may be confused when deductions are silently skipped — mitigated by logging and return value counters

## References
- Memory: `fleximport-no-new-entries.md`
- `backend/services/flexible_import.py` — `import_flexible_data()`
- Memory: `settlement-lock-fleximport-fix.md`
