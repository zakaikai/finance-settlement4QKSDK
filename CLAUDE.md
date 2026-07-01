# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Agent skills

### Issue tracker

Local-markdown — issues live under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles mapped to `Status:` line values in local issue files. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo — one `CONTEXT.md` + `docs/adr/` at the root. See `docs/agents/domain.md`.

## Project Overview

财务结算系统 (Financial Settlement System) — computes revenue splits between channels, publishers, and company entities for a mobile gaming / app distribution context. Data is imported via Excel templates, then settlement amounts are calculated per channel and per publisher.

## Module Architecture

Three decoupled modules sharing `settlement_formula.py` and `ChannelSettlement` as contracts:

```
[Base Layer]                    [Flexible Import]              [Lock System]
 models.py                      flexible_import.py             lock_service.py
 database.py                    template_import.py             ledger_service.py
 settlement_service.py          template_defs.py               snapshot_service.py
 field_definitions.py
     │                                │                              │
     └──────── settlement_formula.py ─┘──────────────────────────────┘
              (FormulaInput, compute(), hydrate_formula_input)

              ┌── ChannelSettlement (shared wide table) ──┐
              │   Deduction   ChannelLock   PublisherLock  │
              └────────────────────────────────────────────┘
```

**Rules:**
- **Flex import**: UPDATE-only on Deduction + ChannelSettlement; lock guard (read-only check); no writes to lock tables
- **Lock system**: Lock/unlock → sync ChannelSettlement → double-entry journal → AR/AP snapshot
- **Base**: `compute()` is the single formula authority; `hydrate_formula_input()` is the single DB→formula-input authority

Architecture Decision Records: `docs/adr/adr-001` through `adr-004`.

## Tech Stack

- **Backend**: Python 3.14+, FastAPI, SQLAlchemy 2.0 (async), aiosqlite, openpyxl, cryptography
- **Frontend**: Vue 3 (Composition API, `<script setup>`), Vue Router 4, Vite 5, AG Grid 32, Axios, ECharts, CSS Variables design system (dark mode via `.dark` class toggle)
- **Database**: SQLite (single file at `data/settlement.db`)
- **Packaging**: PyInstaller (one-folder, UPX compressed, ~67MB)
- **Linting**: ruff (Python), eslint (Vue/JS)

## Quick Start

```bash
# One-time setup
setup.bat

# Start production server (builds frontend + starts backend on :8770)
start.bat
```

- App: http://localhost:8770
- API Docs: http://localhost:8770/docs

## Commands

```bash
# Production: build frontend + start backend (single server)
start.bat

# Dev mode: start backend with auto-reload (separate terminal)
backend\.venv\Scripts\uvicorn backend.main:app --reload --port 8770

# Dev mode: start frontend with hot-reload (separate terminal, from frontend/)
npx vite --port 5173

# Frontend production build only
npx vite build

# Run import test (requires backend running)
python test_import.py

# Lint backend
ruff check .

# Lint frontend
cd frontend && npx eslint src/
```

## Project Structure

```
backend/
  run.py               — PyInstaller entry point (replaces uvicorn CLI)
  main.py              — FastAPI app, CORS, auth middleware, router registration
  database.py          — SQLAlchemy async engine, session factory, DB init, backup/restore (encryption → crypto_service)
  models.py            — 21 ORM models (incl. LockMixin + SplitConfigMixin bases) (SQLAlchemy) incl. AuditLog, SchemaMigration, PartyInfo
  schemas.py           — Pydantic request/response models
  auth.py              — Password hashing (SHA256), session tokens, rate limiting
  updater.py           — Version check and zip-patch apply
  routers/
    auth.py            — GET /api/auth/status, POST login/setup/reset/logout
    basic_data.py      — Games, companies, publishers, channels CRUD + batch
    import_data.py     — Template download, preview, confirm import; flexible import (preview/confirm/import); synonym dictionary export/import
    ocr.py             — OCR parse, bridge start/stop, dictionary, fuzzy match
    settlement.py      — Channel/publisher settlement queries, bill export, split-config batch
    dashboard.py       — Ranking, trend, level1/level2 options
    party_info.py      — Party info CRUD (our_company / channel / publisher)
    system.py          — Status, backup, restore, reset, patches, logs, version, update
  services/
    template_defs.py   — TEMPLATE_DEFS descriptor dict (11 template types), FLEXIBLE_FIELD_DEFS, synonym dictionary, infer_column_mapping
    template_import.py — Template-based import pipeline: parse_excel, resolve_foreign_keys, validate_values, check_conflicts, import_data
    flexible_import.py — Flexible import: parse_flexible_excel, resolve_flexible_game_names, import_flexible_data (lock guard + UPDATE-only rule)
    settlement_service.py — Settlement queries + write-path ops + compare_imported_rows (flexible diff) + _save_income_split_config
    settlement_formula.py — FormulaInput + compute() (pure formula) + hydrate_formula_input (single-row DB→FormulaInput). Shared by all three modules.
    basic_data_service.py — FK_DEPENDENCIES registry, check_fk_deps, batch_save_channels (3-level hierarchy), batch_save_company_games (project expansion)
    lock_service.py    — Lock/unlock with _LockCfg registry; delegates formula hydration to settlement_service.hydrate_formula_input()
    ledger_service.py  — 5-account double-entry journal (ar/bank/revenue/cost/ap); FIFO payment matching
    fk_resolver.py     — FKResolver class (isolated cache) + context manager + module-level default for backward compat
    crypto_service.py — AES-256-CBC backup encryption (auto-key + PBKDF2), format detection
    field_definitions.py — Canonical financial field defs; bill columns generated from this source
    dashboard_service.py — Ranking/trend aggregation queries
    bill_service.py    — Bill export logic, columns built from field_definitions.get_bill_columns()
    ocr_service.py     — difflib-based fuzzy game name matching (multi-pass: name → amount → ratio → settlement)
    ocr/
      engine.py        — HTTP client to PaddleOCR bridge (port 8771), bridge lifecycle
      bridge.py        — Standalone PaddleOCR microservice (FastAPI on :8771), auto-idle-shutdown
  data/
    column_synonyms.json — Persisted column synonym dictionary (user-editable)
  templates/           — Blank Excel templates for download
  tests/
    conftest.py        — Async test fixtures, in-memory SQLite
    test_dashboard.py  — Dashboard service tests
    test_ocr.py        — OCR matching and validation tests

frontend/
  src/
    main.js            — Vue app entry, CSS imports, global component registration
    App.vue            — Root layout with nav header, dark mode toggle, keyboard shortcuts
    router/index.js    — Routes + navigation guard (redirect to /login if not authenticated)
    styles/
      variables.css    — Three-layer design tokens (palette → semantic → sizing/type/shadow)
      reset.css        — Global reset + app shell (header, nav, card-panel, page-title)
      dark.css         — :root.dark overrides + .dark .ag-theme-quartz AG Grid theme
      card.css         — .card / .card-padded / .card-compact / .card-elevated (WIP)
      form.css         — .form-input / .form-select / .form-textarea / .form-checkbox / .form-label / .form-error
      grid.css         — AG Grid shared :deep() overrides (row-number, cell-negative, cell-locked)
      tabs.css         — .tabs / .tab-item / .tab-active button group
    components/
      AppButton/       — <AppButton variant size disabled loading> — 6 variants × 3 sizes
      AppModal/        — <AppModal v-model title width> — Teleport, ESC close, body scroll lock
      AppToast/        — <AppToast> + useToast() — 4 types (success/error/warning/info), stacked notifications
      BillTemplateManager.vue — Self-contained bill template CRUD (upload/edit/delete/download), shared by BasicData + System
    composables/
      useEditableGrid.js — Shared change-tracking for AG Grid inline editing (dirty/add/delete/save/discard)
      gridColumns.js   — Column definition factories: rowNoCol, rateCol, dateCol, deleteCol, copyDeleteCol
      useSharedData.js — Module-level singleton cache for shared data (useGames with gamesMap)
      useShortcuts.js  — Global Alt+wheel horizontal scroll + Ctrl+S save callback
    views/
      Login.vue        — Login / password setup page (first-run)
      Home.vue         — Dashboard with summary cards, ranking blocks, ECharts trend
      BasicData.vue    — Tabbed view (8 tabs: games, companies, publishers, channels, party-info, income/payment split, bill templates)
      DataImport.vue   — Template download, upload, preview, confirm import
      FlexImport.vue   — Flexible import: upload → column mapping → review → import (3-step wizard)
      OcrImport.vue    — OCR image import (5-step wizard, Beta)
      Settlement.vue   — Channel/publisher settlement query + inline deduction editing + lock/unlock (real_revenue/settlement_amount) + CSV export (respects grid filters, exports locked values when cells are locked) + 全量导出 (row-level full export with channel hierarchy) + bill export. Search preserves AG Grid column filter model across re-queries — only month range triggers backend fetch; column filters apply client-side on reloaded data.
      Memo.vue         — Memos/notes management with reminders and file attachments
      System.vue       — System management: status, backups, logs, patches, bill templates, about/update
    api/index.js       — Axios client with 401 interceptor + token management
```

- **Model mixins** (`models.py`): `LockMixin` (shared by ChannelLock/PublisherLock) and `SplitConfigMixin` (shared by IncomeSplitConfig/PaymentSplitConfig). Changing a shared field only needs one edit.
- **Formula hydration** (`settlement_formula.hydrate_formula_input()`): Single-row DB→FormulaInput dataclass. Used by lock_service unlock recomputation. Channel vs publisher paths share 90% of the logic.
- **原始流水表** (`raw_settlements`): `(channel_id+channel_name, game_id+game_name, month, raw_revenue)` — 导入时聚合写入，渠道名称冗余存储。结算查询 + ChannelPicker + 弹性导入全从此表取渠道数据。
- **Lock system** (`lock_service.py`): `_LockCfg` registry parameterizes Channel/Publisher differences. Lock/unlock writes ONLY to ChannelLock/PublisherLock tables — no ARAP side effects. Lock guard in flex import rejects import if any target key is locked.
- **Flex import** (`flexible_import.py`): Deduction (UPDATE only) + IncomeSplitConfig (UPSERT with date-range close+create) + ChannelLock (INSERT via `_write_lock_inline`). Game matching filters candidates to raw_settlements for the selected channel.
- **ARAP system** (`snapshot_service.py`): Decoupled. `POST /arap/snapshot` reads channel_locks WHERE confirmed_month IS NULL → aggregates by (entity_id, month) → writes `arap_records` with both `month`（流水月份）and `confirmed_month`（收款月份）. Pivot queries filter by confirmed_month, display/aggregate by month. Profit table follows the same pattern. Monthly close routes locked data to working month.
- **3D unique key**: All channel-side entities use `(channel_id, game_id, month)`. Channel hierarchy (sub→backend→channel) resolved ONLY at import time — zero runtime resolution.

## Database (20 user tables + system tables)

| Table | Purpose |
|---|---|
| `games` | Game master with discount rate |
| `companies` | Company (我方对接公司) |
| `company_game_mapping` | Many-to-many: company <-> game |
| `publishers` | Publisher/developer (研发商户) |
| `publisher_game_mapping` | Many-to-many: publisher <-> game |
| `channel_categories` | Channel category — FK reference only, no query JOIN |
| `backend_channels` | Backend channel — import-time only |
| `sub_channels` | Sub-channel — import-time only |
| `raw_settlements` | **原始流水表** — aggregation source for all settlement queries |
| `deductions` | Deductions per (channel, game, month) — 3D key |
| `income_split_config` | Channel split rates per (channel, game) with date-range |
| `payment_split_config` | Publisher split rates per (publisher, game) with date-range |
| `channel_locks` | Channel lock values per (channel, game, month) — 3D key |
| `publisher_locks` | Publisher lock values per (publisher, game, month) |
| `arap_records` | ARAP snapshots — `month` (流水月份) + `confirmed_month` (收款月份) |
| `monthly_closes` | Closed months (lock routing to working month) |
| `party_info` | Party bank/tax info |
| `profit_expenses` | Profit statement period expenses |
| `arap_company_overrides` | ARAP company overrides (publisher side) |
| `payment_records` | Payment/collection records |
| `payment_allocations` | FIFO payment-to-ARAP allocations |
| `channel_company_mappings` | Channel→PartyInfo 1:1 mapping |

## Architecture

```
Browser (Vue 3 SPA) — :5173 (dev) / :8770 (prod)
    │ Axios (JSON), X-Auth-Token header
    ▼
FastAPI (uvicorn :8770)
  ├─ Auth middleware → validates X-Auth-Token (excludes /api/auth/*, /api/health)
  ├─ /api/auth/*          → routers/auth.py (login, setup, reset, logout)
  ├─ /api/basic/*         → routers/basic_data.py
  ├─ /api/import/*
  │     /templates        → list/download blank templates
  │     /preview, /confirm → template-based import
  │     /flexible/*       → flexible import (preview/confirm/import/dictionary)
  ├─ /api/settlement/*    → routers/settlement.py → settlement_service.py
  ├─ /api/dashboard/*     → routers/dashboard.py → dashboard_service.py
  ├─ /api/ocr/*           → routers/ocr.py (parse, match, bridge start/stop)
  ├─ /api/party-info/*    → routers/party_info.py
  ├─ /api/system/*        → routers/system.py (status, backup, restore, patches, logs, version)
  ├─ /api/health          → main.py
  └─ SPA fallback         → frontend/dist/index.html
    │ SQLAlchemy (async, aiosqlite)
    ▼
SQLite (data/settlement.db)

PaddleOCR Bridge (optional, isolated env):
  backend/ocr_venv/        — Separate Python 3.12 venv with PaddlePaddle CPU + PaddleOCR 3.5
  backend/services/ocr/bridge.py → uvicorn :8771 → PaddleOCR(lang="ch").predict()
  Idle timeout: 10 min auto-shutdown to free ~1GB RAM
  Main backend communicates via HTTP (httpx), not direct import
```

## Key Design Notes

- **Import flow (template)**: Upload Excel → parse → resolve FKs → validate → detect conflicts → preview → user confirms → upsert into DB
- **Import flow (flexible)**: Upload Excel → infer column mapping (synonym dict + fuzzy) → user adjusts mapping → parse → fuzzy game name match → review differences (with duplicate game detection) → confirm import. Duplicate (game_id, month) rows are detected in comparison and rejected at import time. Lock values use explicit `is None` checks (not `or`) to handle zero-value Decimal correctly.
- **Column inference**: Exact match against synonym dictionary (`_COLUMN_SYNONYMS`) first → fallback to difflib fuzzy matching + keyword hints. Dictionary is user-editable via export/import JSON endpoints, persisted to `backend/data/column_synonyms.json`
- **Game name matching**: Multi-pass cascade using difflib `SequenceMatcher` — name similarity → top-3 candidates → amount consistency → ratio plausibility → settlement tiebreaker. Confidence: high (≥90%), medium (≥70%), low (<70%). Duplicate (game_id, month) matches detected in comparison table; import rejects duplicates with explicit row references.
- **Settlement formula** (`services/settlement_formula.py`): Single pure-function authority `compute()`. Accepts (raw_revenue, discount_rate, total_deductions, split_rate, channel_fee_rate, tax_rate, fixed_fee, locked_*, direction) → (real_revenue, settlement_amount). Locked values override formula when present. Both income and payment directions support locking. Precision: `.quantize(Decimal("0.01"))` for amounts.
  - **Locking UI**: `real_revenue` / `settlement_amount` cells editable. Edit → calls `POST /api/settlement/lock`. Clear cell → unlocks, restores formula value. Locked cells show blue left border (`cell-locked` class). Locks stored in dedicated `channel_locks` / `publisher_locks` tables (not legacy `Deduction` columns — those have been removed).
  - **CSV export**: Generated on frontend from AG Grid's `forEachNodeAfterFilterAndSort()` — column filters and sort order are honored. BOM-prefixed UTF-8 for Excel compatibility. No backend call.
  - **全量导出** (`GET /api/settlement/export-full`): Row-level full export at RawTransaction granularity. Exports every transaction individually with full 3-level channel hierarchy (一级/二级/三级渠道), prorated deductions, and per-row settlement amounts. Supports `mode` (income/payment), optional `start_month`/`end_month`. Implemented in `query_full_income_export()` / `query_full_payment_export()` in `settlement_service.py`.
  - Income: `(net_revenue) * split_rate * (1 - channel_fee_rate) * (1 - tax_rate)`
  - Payment: `(net_revenue) * split_rate * (1 - channel_fee_rate) * (1 - tax_rate) + fixed_fee`
  - Where `net_revenue = locked_real_revenue ?? (raw_revenue * discount_rate) - total_deductions`
- **FK resolution** (`services/fk_resolver.py`): `FKResolver` class with per-instance isolated cache + `__aenter__/__aexit__` context manager. Module-level `_default` instance + delegating functions for backward compat. Supports `resolve`, `resolve_raw`, `cache_set`, `cache_get`, `reset`.
- **Split config date ranges**: `IncomeSplitConfig` / `PaymentSplitConfig` have `effective_from` (Date, NOT NULL) and `effective_to` (Date, nullable). A config applies to a month if the month's range overlaps `[effective_from, effective_to]`. NULL `effective_to` = indefinite. Batch save closes previous config (sets effective_to = prev_month_end) and creates new.
- **Backup encryption** (`services/crypto_service.py`): 3 modes — plain (no encrypt), auto-key (machine-local AES-256-CBC via COMPUTERNAME+SHA256), password (PBKDF2-HMAC-SHA256 100K iterations + AES-256-CBC). v2 format: FSEB magic + type byte + salt + IV + ciphertext. Legacy format auto-detected. Backup WAL flush uses PASSIVE checkpoint (NOT VACUUM — corrupts on Windows). Restore verification: integrity_check → fallback to temp-file VACUUM if stale WAL present → restores journal_mode=WAL after. Reset on empty DB skips backup; reset with password creates password backup.
- **Bill columns** (`services/bill_service.py`): Income/payment column lists are built from `field_definitions.get_bill_columns()` + identity prefix columns (seq, entity name, project code/name). Adding a financial field to FIELD_DEFS automatically includes it in bills.
- **Environment isolation**: PaddleOCR runs in separate `ocr_venv` (Python 3.12) with its own PaddlePaddle CPU dependencies. Main backend uses Python 3.14 in `.venv`. Bridge is optional — flexible import works without it.
- **Auth**: First-run setup creates password (SHA256 hash in config.env). Login returns hex token (SHA256), validated via middleware. Rate limited: 5 attempts / 30s lockout per IP.
- **Packaging**: PyInstaller one-folder (FinanceSettlement.exe + _internal/). Auto-opens browser. Single-instance guard via port check. config.env at root for user config.
- **Update mechanism**: GET /api/system/check-update compares local version.json with remote. POST /api/system/apply-patch applies zip patches with SHA256 checksums and file backups.
- All DB operations use async SQLAlchemy; sessions obtained via `async with get_db() as db:`
- CORS configured via `CORS_ORIGINS` env var, defaults to `localhost:5173` and `127.0.0.1:5173`
- Linting: ruff (Python, configured in pyproject.toml), eslint (Vue/JS, configured in frontend/eslint.config.mjs)

## Frontend Design System

All colors, spacing, typography, shadows use CSS custom properties defined in `frontend/src/styles/variables.css`. Three-layer token architecture:

```
palette (raw hex) → semantic (--color-*, --bg-*, --text-*) → component (--shadow-*, --radius-*, --space-*)
```

### CSS variables pattern

Never hardcode hex/rgba/px values. Always reference `var(--*)`:

```css
/* Good */
color: var(--text-primary);
background: var(--bg-card);
border: 1px solid var(--border-default);
padding: var(--space-xl);
font-size: var(--text-base);
```

### Shared components (globally registered in main.js)

| Component | Usage | Props |
|-----------|-------|-------|
| `<AppButton>` | All buttons | `variant` (primary/success/danger/warning/info/default), `size` (sm/md/lg), `disabled`, `loading` |
| `<AppModal>` | All dialogs | `v-model`, `title`, `width` (default 400px), `closable` |
| `<AppToast>` | Mount once in App.vue | — (use `useToast()` composable in child components) |

### Toast notifications

```js
import { useToast } from '../components/AppToast/useToast'
const toast = useToast()
toast.success('保存成功')
toast.error('操作失败: ' + msg)
toast.warning('部分数据冲突')
toast.info('正在处理...')
```

### Dark mode

Manual toggle (☀/☾ button in header), persisted to `localStorage.finance_dark`. Toggles `.dark` class on `<html>`.

- All design tokens overridden in `dark.css` under `:root.dark { }`
- AG Grid theme overridden via `.dark .ag-theme-quartz { }` (higher specificity than AG Grid's built-in `.ag-theme-quartz`)
- New components must use CSS variables — they automatically adapt to dark mode

### Keyboard shortcuts

Centrally managed in `useShortcuts.js`:
- **Alt + wheel**: horizontal scroll on AG Grid viewports (global, auto-installed by App.vue)
- **Ctrl/Cmd + S**: save shortcut (opt-in per view via `useShortcuts({ onSave: callback })`)

### Tab component pattern

Use shared classes from `tabs.css`:

```html
<div class="tabs">
  <button :class="['tab-item', { 'tab-active': activeTab === 'key' }]" @click="activeTab = 'key'">Label</button>
</div>
```

### Card classes (WIP — subject to adjustment)

`card.css` provides `.card`, `.card-padded`, `.card-compact`, `.card-elevated`. These are CSS utility classes, not Vue components. Marked as work-in-progress; future changes must update this documentation.
