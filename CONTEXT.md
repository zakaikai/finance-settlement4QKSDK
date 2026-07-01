# CONTEXT — 财务结算系统

## 业务背景

游戏发行商（我方）与以下三方进行收入分账：

- **渠道方 (Channel)** — 应用商店/推广平台（如华为、OPPO、小米），提供分发和支付通道
- **研发商 (Publisher)** — 游戏开发商/研发团队
- **我方公司 (Company)** — 我方对接的不同公司主体

每月从渠道获取原始流水，按合同约定比例计算出各方应得结算金额。

## 核心角色

| 角色 | 英文 | 说明 |
|------|------|------|
| 我方公司 | Company | 我方签约公司主体，一个游戏可能属于不同公司 |
| 渠道分类 | ChannelCategory | 渠道的一级分类，如"应用商店" |
| 后台渠道 | BackendChannel | 渠道的二级分类，如"华为"属于"应用商店" |
| 二级渠道 | SubChannel | 具体的数据源，如"华为-游戏中心" |
| 研发商 | Publisher | 游戏研发商户 |
| 游戏 | Game | 游戏产品，有关联公司和研发商 |

## 数据结构链路

```
Excel 导入 (模板/弹性)
  ├── 三级渠道解析 (sub→backend→channel)  ← 仅导入时，运行时零解析
  │       ↓
  └──→ raw_settlements (原始流水表)  ← 结算查询唯一数据源
          ├── channel_id + channel_name (导入时冗余存储)
          ├── game_id + game_name
          ├── month
          └── raw_revenue (预聚合)

结算查询 ← raw_settlements + deductions + income_split_config + channel_locks
弹性导入 ← deductions (UPDATE) + income_split_config (UPSERT) + channel_locks (INSERT)
ARAP快照 ← channel_locks 增量快照 → arap_records (confirmed_month≠month)
```

**raw_settlements** (原始流水表) 是结算查询的唯一数据源。
channel_categories/sub_channels/backend_channels 仅用于 Excel 导入时做一次性渠道解析，运行时零查询。
raw_transactions (行级存储) 和 channel_settlements (宽表缓存) 均已废止。

## 模块架构

系统由三个解耦的模块组成：

| 模块 | 核心文件 | 职责 |
|------|---------|------|
| **底层 (Base)** | `models.py`, `database.py`, `settlement_formula.py`, `settlement_service.py`, `field_definitions.py` | ORM 模型、数据库管理、纯公式计算、结算查询、字段定义 |
| **弹性导入 (Flexible Import)** | `flexible_import.py`, `template_import.py`, `template_defs.py` | 任意格式 Excel 导入、模板导入、列推断 |
| **锁系统 (Lock System)** | `lock_service.py`, `ledger_service.py`, `snapshot_service.py` | 锁定/解锁、复式记账、AR/AP 快照、月结 |

**共享契约：**
- `settlement_formula.py` — `FormulaInput` dataclass + `compute()` 纯函数 + `hydrate_formula_input()` 数据库查询。被所有三个模块导入。
- `ChannelSettlement` — 共享宽表，三个模块均可读可写（各自同步）。

## 锁定系统

用户可在结算界面手动锁定 `real_revenue` 或 `settlement_amount`，锁定值覆盖公式计算结果。

- **锁定表**：`channel_locks` (渠道侧) 和 `publisher_locks` (研发商侧)，共享 `LockMixin` 列
- **锁定守卫**：弹性导入写入前检查 ChannelLock，任意目标键存在锁定值则拒绝整批导入
- **复式记账**：锁定 `settlement_amount` 时创建借贷分录（渠道：Dr AR / Cr 收入；研发商：Dr 成本 / Cr AP）
- **月结路由**：已关闭月份的锁定路由到当前工作月份（下一个未关闭月）
- **诊断查询**：`GET /api/system/status` 返回 `lock_consistency` 字段，检测 ChannelSettlement 与 ChannelLock 数据不一致

## 分账公式

结算公式统一实现在 `backend/services/settlement_formula.py` 的 `compute()` 函数中。

### 锁定优先 (Lock Override)
计算结果可被锁定值覆盖：
- `locked_real_revenue` 非空时，跳过 real_revenue 公式计算
- `locked_settlement_amount` 非空时，跳过 settlement_amount 公式计算
- 渠道结算和研发商结算均支持锁定

### 渠道结算 (Channel Settlement)
```
real_revenue = locked_real_revenue ?? (raw_revenue * discount_rate)
net_revenue = real_revenue - deductions
settlement_amount = locked_settlement_amount ?? (net_revenue * split_rate * (1 - channel_fee_rate) * (1 - tax_rate))
```

### 研发商结算 (Publisher Settlement)
```
real_revenue = locked_real_revenue ?? (raw_revenue * discount_rate)
net_revenue = real_revenue - total_deductions
settlement_amount = locked_settlement_amount ?? (net_revenue * split_rate * (1 - channel_fee_rate - tax_rate) + fixed_fee)
```

精度规则：金额字段 `.quantize(Decimal("0.01"))`。

## 核心业务流程

1. **模板导入** — 下载标准模板 → 填入数据 → 上传 Excel → FK 校验 → 冲突检测 → 预览 → 确认写入
2. **弹性导入** — 上传任意渠道对账单 Excel → 自动推断列映射（同义词词典 + 模糊匹配）→ 用户确认列映射 → 模糊匹配游戏名 → 审核差异 → 一键导入。支持同义词词典导出/上传管理。
3. **OCR 识别（Beta）** — 上传账单截图 → PaddleOCR 识别 → 表格解析 → 列映射 → 游戏名匹配 → 导入。需先启动 OCR 桥接服务（PaddleOCR :8771），处理时间约 3 分钟/张（CPU）。
4. **分账计算** — 根据配置的分成比例（带生效时间）、通道费率、税率计算各方应得
5. **对账** — 按月汇总渠道和研发商的结算数据
6. **导出** — 生成标准化结算对账单 Excel；CSV 聚合导出（按渠道/游戏/月汇总）；全量 CSV 导出（原始流水行级，含完整三级渠道层级和分摊结算金额）

## 弹性导入设计

弹性导入解决各渠道对账单格式不一致的痛点：
- **列名同义词词典**：预置常见列名变体（如 "充值金额"/"充值全额"/"流水金额" 都映射到 `raw_revenue`），用户可通过导出→编辑→上传流程扩展
- **游戏名模糊匹配**：基于 difflib 的多轮匹配（名称相似度 → 金额一致性 → 分成比例 → 结算金额），置信度分高/中/低三档
- **三步向导**：上传配置 → 确认列映射 → 审核导入（含重复游戏匹配检测与防护，同游戏同月份重复行拒绝导入）

## 环境隔离

- **主后端**：Python 3.14, `.venv` 虚拟环境，FastAPI + SQLAlchemy + openpyxl
- **OCR 桥接**：Python 3.12, `ocr_venv` 虚拟环境，PaddleOCR 3.5 + PaddlePaddle CPU 版。独立进程（端口 8771），空闲 10 分钟自动关闭释放 ~1GB 内存。主后端通过 HTTP 通信，不直接 import。弹性导入不依赖 OCR 桥接。

## 应收应付（ARAP）双时间维度

ARAP 系统区分两个时间概念：

| 字段 | 含义 | 示例 |
|------|------|------|
| `month` | **流水月份** — 流水数据归属周期 | 2026-03（3月的流水） |
| `confirmed_month` | **收款月份** — 对账确认、快照生成的月份 | 2026-06（6月确认收款） |

一个收款月份可包含多个流水月份的数据。快照时取 `channel_locks WHERE confirmed_month IS NULL`，按流水月份聚合写入 `arap_records`。

- **ARAP 界面**：上层筛选器按 `confirmed_month`（收款月份），Grid 列头和数据按 `month`（流水月份）展示
- **利润表**：同样逻辑 — 筛选收款月份，展示流水月份

## 备份恢复系统

- **加密**：auto 密钥（COMPUTERNAME+路径→SHA256）用于本机备份；password（PBKDF2-SHA256，100K迭代）用于可跨机恢复的备份
- **备份前 WAL 处理**：`wal_checkpoint(PASSIVE)` 而非 VACUUM（VACUUM 在 Windows 上可能损坏数据库）
- **重置防护**：数据库已空时（games=0）跳过备份步骤，返回 `was_empty=True`
- **恢复验证**：先 `integrity_check`，失败则通过临时文件+VACUUM 重建绕过残留 WAL 干扰
- **恢复后**：自动切回 `journal_mode=WAL`
- **工具脚本**：`test_import.py` / `clean_arap.py` / `clear_company_games.py` 通过 `get_db_path()` 动态解析数据库路径

## 关键约束

### 三维唯一键铁律
所有渠道侧结算实体使用 `(channel_id, game_id, month)` 三维唯一键，研发商侧使用 `(publisher_id, game_id, month)`。详见 ADR-002。

### 弹性导入 UPDATE-only
弹性导入只更新已存在的 Deduction 和 ChannelSettlement 行，禁止创建新行。不存在则跳过（记录日志 + 计数）。分账配置通过 UPSERT 处理。详见 ADR-003。

### 其他约束
- `IncomeSplitConfig` / `PaymentSplitConfig` 通过 `effective_from`/`effective_to` 管理生效时段
- Deduction 按 `(channel_id, game_id, month)` 唯一
- 流水金额字段使用 DECIMAL(16, 2)，分账比例使用 DECIMAL(10, 4)
- 架构决策记录：`docs/adr/`
