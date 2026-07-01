# Game Channel Settlement Engine / 游戏渠道分账结算引擎

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)
[![Vue 3](https://img.shields.io/badge/Vue-3.5%2B-4FC08D)](https://vuejs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A full-stack revenue-split settlement engine for multi-party game publishing — computes income distributions across channels, publishers, and operating entities. Built with Python (FastAPI + SQLAlchemy async) backend and Vue 3 (Composition API) frontend.

全栈游戏联运收入分账结算引擎，处理渠道方 / 发行商 / 运营主体三方月度分成计算。涵盖流水导入、分账计算、对账锁定、应收应付快照、复式记账全链路。

---

## Highlights / 亮点

- **纯函数公式引擎** — `compute()` 单一权威，结算/锁定/快照三模块统一调用
- **弹性导入** — 同义词词典 + difflib 模糊匹配列名和游戏名，适配任意格式对账单
- **锁定系统** — 已核金额冻结保护，独立锁表存储，解锁自动重算
- **复式记账** — 5 账户双分录（应收/银行/收入/成本/应付），FIFO 付款匹配
- **AR/AP 快照** — 增量累积，按月关账路由
- **设计系统** — CSS 三层 token（palette → semantic → component），暗色模式
- **备份加密** — AES-256-CBC (PBKDF2 100K 迭代)，三种加密模式

---

## Tech Stack / 技术栈

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), aiosqlite |
| Frontend | Vue 3 (Composition API), Vite 5, AG Grid 32, ECharts 6 |
| Database | SQLite (single file, zero config) |
| Excel | openpyxl — read/write templates and bills |
| OCR (opt) | PaddleOCR — isolated venv, idle auto-shutdown |
| Auth | SHA256 password hashing, token sessions, IP rate limiting |
| Encryption | AES-256-CBC + PBKDF2-HMAC-SHA256 (100K iterations) |
| Packaging | PyInstaller one-folder (Windows executable) |

---

## Quick Start / 快速开始

### Prerequisites

- Python 3.12+
- Node.js 18+ / npm 9+

### Setup

```bash
git clone https://github.com/YOUR_USER/finance-settlement.git
cd finance-settlement

# Backend
python -m venv backend/.venv
backend/.venv/Scripts/pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

### Development

```bash
# Terminal 1: Backend
backend/.venv/Scripts/uvicorn backend.main:app --reload --port 8770

# Terminal 2: Frontend
cd frontend && npx vite --port 5173
```

- App: http://localhost:5173
- API Docs: http://localhost:8770/docs

### Production

```bash
setup.bat    # One-time setup
start.bat    # Build frontend + start server on :8770
```

---

## Settlement Formula / 分账公式

```
real_revenue  = locked_real_revenue ?? (raw_revenue × discount_rate)
net_revenue   = real_revenue − total_deductions
settlement    = net_revenue × split_rate × (1 − channel_fee_rate) × (1 − tax_rate)
```

- **Income (渠道侧):** `settlement = net_revenue × split_rate × (1 − channel_fee_rate) × (1 − tax_rate)`
- **Payment (研发侧):** `settlement = net_revenue × split_rate × (1 − channel_fee_rate) × (1 − tax_rate) + fixed_fee`
- Locked values override computed values; unlocking restores formula output.
- 锁定值覆盖公式计算结果，解锁后自动重算。

---

## Architecture / 架构

```
[Excel Import / OCR] ──→ raw_settlements (canonical source)
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   settlement_formula   flexible_import      lock_service
   (compute / hydrate)  (UPDATE-only)        (Lock/Unlock)
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                    ChannelSettlement
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
             AR/AP Snapshots    Double-Entry Ledger
```

Three decoupled modules share `settlement_formula.py` and `ChannelSettlement` as contracts. All channel-side entities use `(channel_id, game_id, month)` 3D unique keys.

---

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app, CORS, auth middleware
│   ├── database.py          # Async SQLAlchemy engine, backup/restore
│   ├── models.py            # 20+ ORM models (LockMixin, SplitConfigMixin)
│   ├── schemas.py           # Pydantic request/response models
│   ├── auth.py              # Password hashing, token sessions, rate limiting
│   ├── updater.py           # Version check + zip-patch hot update
│   ├── routers/             # 10 API route modules
│   ├── services/            # Business logic (formula, lock, ledger, snapshot…)
│   │   └── ocr/             # PaddleOCR bridge (isolated microservice)
│   ├── tests/               # 40+ pytest files (async, in-memory SQLite)
│   └── templates/           # Blank Excel import templates
├── frontend/
│   └── src/
│       ├── views/           # 11 page components (Login, Settlement, ARAP…)
│       ├── components/      # AppButton, AppModal, AppToast, dashboard widgets
│       ├── composables/     # useEditableGrid, useSharedData, useShortcuts…
│       ├── styles/          # CSS design system (variables, dark mode, form, grid)
│       └── api/             # Axios client with 401 interceptor
├── docs/                    # ADR records, domain model, project intro
├── tools/                   # DB encryption/decryption utilities
└── config.env.example       # Configuration template
```

---

## API Endpoints

| Group | Prefix | Description |
|-------|--------|-------------|
| Auth | `/api/auth/*` | Login, setup, reset, logout |
| Basic Data | `/api/basic/*` | Games, companies, publishers, channels CRUD |
| Import | `/api/import/*` | Template download, preview, confirm; flexible import |
| Settlement | `/api/settlement/*` | Settlement queries, lock/unlock, full/bill export |
| Dashboard | `/api/dashboard/*` | Rankings, trends, drill-down |
| ARAP | `/api/arap/*` | AR/AP snapshots, monthly close, profit |
| Party Info | `/api/party-info/*` | Bank/tax info management |
| System | `/api/system/*` | Status, backup, restore, patches, logs, update |

---

## Testing

```bash
pip install -r backend/requirements-dev.txt
pytest backend/tests/        # 40+ test files, async in-memory SQLite
ruff check backend/          # Python lint
cd frontend && npx eslint src/  # Vue/JS lint
```

---

## License

[MIT](LICENSE)
