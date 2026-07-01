from pydantic import BaseModel, field_validator, Field
from typing import Optional, List
from datetime import date
from decimal import Decimal


# ── 基础数据 ──

class GameCreate(BaseModel):
    game_id: str
    game_name: str
    game_backend_name: Optional[str] = None
    discount_rate: Decimal

class GameResponse(GameCreate):
    class Config:
        from_attributes = True

class CompanyCreate(BaseModel):
    company_name: str
    game_ids: Optional[List[str]] = []

class CompanyResponse(BaseModel):
    company_id: int
    company_name: str
    class Config:
        from_attributes = True

class PublisherCreate(BaseModel):
    publisher_name: str
    game_ids: Optional[List[str]] = []

class PublisherResponse(BaseModel):
    publisher_id: int
    publisher_name: str
    class Config:
        from_attributes = True

class ChannelCategoryCreate(BaseModel):
    channel_name: str

class ChannelCategoryResponse(ChannelCategoryCreate):
    channel_id: int
    class Config:
        from_attributes = True

class BackendChannelCreate(BaseModel):
    backend_channel_name: str
    channel_name: str

class BackendChannelResponse(BaseModel):
    backend_channel_id: int
    backend_channel_name: str
    channel_id: int
    class Config:
        from_attributes = True

class SubChannelCreate(BaseModel):
    sub_channel_name: str
    backend_channel_name: str

class SubChannelResponse(BaseModel):
    sub_channel_id: int
    sub_channel_name: str
    backend_channel_id: int
    class Config:
        from_attributes = True


# ── 导入校验结果 ──

class ImportPreview(BaseModel):
    template_type: str
    total_rows: int
    preview_rows: List[dict]
    errors: List[dict]
    has_conflict: bool
    conflict_count: int


class ImportConfirm(BaseModel):
    template_type: str
    overwrite: bool = False


# ── 批量更新 ──

class GameUpdate(BaseModel):
    game_id: str
    game_name: str
    game_backend_name: Optional[str] = None
    discount_rate: Decimal

class GameBatchRequest(BaseModel):
    created: List[GameCreate] = []
    updated: List[GameUpdate] = []
    deleted: List[str] = []

class CompanyUpdate(BaseModel):
    company_id: int
    company_name: str

class CompanyBatchRequest(BaseModel):
    created: List[CompanyCreate] = []
    updated: List[CompanyUpdate] = []
    deleted: List[int] = []

class PublisherUpdate(BaseModel):
    publisher_id: int
    publisher_name: str

class PublisherBatchRequest(BaseModel):
    created: List[PublisherCreate] = []
    updated: List[PublisherUpdate] = []
    deleted: List[int] = []


class PublisherGameProjectUpdate(BaseModel):
    publisher_id: int
    game_id: str
    project_code: Optional[str] = None
    project_name: Optional[str] = None


class PublisherGameDelete(BaseModel):
    publisher_id: int
    game_id: str


class CompanyGameByProject(BaseModel):
    company_id: int
    project_code: str
    channel_id: Optional[int] = None


class CompanyGameDelete(BaseModel):
    company_id: int
    game_id: str
    channel_id: Optional[int] = None


class CompanyGameOverride(BaseModel):
    """游戏级公司覆盖 — 单行 UPSERT."""
    company_id: int
    game_id: str
    channel_id: Optional[int] = None


class CompanyGameOverrideDelete(BaseModel):
    """删除游戏级公司覆盖，恢复项目级继承."""
    company_id: int
    game_id: str
    channel_id: Optional[int] = None


class ArapCompanyOverrideUpdate(BaseModel):
    """ARAP 应付侧公司覆盖 — UPSERT."""
    entity_id: int
    original_company_id: int
    override_company_id: int


class ArapCompanyOverrideDelete(BaseModel):
    """ARAP 应付侧公司覆盖 — 删除."""
    entity_id: int
    original_company_id: int


class ChannelRowUpdate(BaseModel):
    row_key: str
    action: str = "update"  # create | update | delete
    channel_name: str
    backend_channel_name: str
    sub_channel_name: str
    # For identifying the original row on update/delete
    orig_channel_name: str = None
    orig_backend_channel_name: str = None
    orig_sub_channel_name: str = None


class DeductionUpdate(BaseModel):
    channel_name: str
    game_id: str
    month: str
    vouchers: Decimal = Decimal("0")
    test: Decimal = Decimal("0")
    welfare: Decimal = Decimal("0")
    bad_debt: Decimal = Decimal("0")


class IncomeSplitConfigUpdate(BaseModel):
    id: Optional[int] = None
    action: Optional[str] = None  # "delete" | None (upsert)
    channel_name: str = ""
    game_id: str = ""
    split_rate: Optional[Decimal] = None
    channel_fee_rate: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class PaymentSplitConfigUpdate(BaseModel):
    id: Optional[int] = None
    action: Optional[str] = None  # "delete" | None (upsert)
    publisher_name: str = ""
    game_id: str = ""
    split_rate: Optional[Decimal] = None
    channel_fee_rate: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    fixed_fee: Optional[Decimal] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


# ── 结算查询 ──

class PartyInfoCreate(BaseModel):
    party_type: str
    name: str
    address: str
    phone: Optional[str] = ""
    bank_name: str
    bank_account: str
    tax_id: str
    notes: Optional[str] = ""

class PartyInfoUpdate(PartyInfoCreate):
    id: int

class ChannelSettlementQuery(BaseModel):
    start_month: Optional[str] = None
    end_month: Optional[str] = None
    channel_name: Optional[str] = None
    game_id: Optional[str] = None

class PublisherSettlementQuery(BaseModel):
    start_month: Optional[str] = None
    end_month: Optional[str] = None
    publisher_name: Optional[str] = None
    game_id: Optional[str] = None


class BillRequest(BaseModel):
    mode: str  # "income" | "payment"
    party_id_a: int  # 甲方 party_info.id
    party_id_b: int  # 乙方 party_info.id
    start_month: Optional[str] = None
    end_month: Optional[str] = None
    rows: Optional[List[dict]] = None  # AG Grid 过滤后的行数据
    template_id: Optional[int] = None  # 对账模板ID, null=使用默认硬编码模板


# ── 对账模板 ──

class BillTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    bill_type: str  # "income" | "payment" | "all"
    is_default: Optional[bool] = False


class BillTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    bill_type: Optional[str] = None
    is_default: Optional[bool] = None


# ── 备忘录 ──

class MemoCreate(BaseModel):
    title: str
    content: Optional[str] = ""
    party_type: Optional[str] = None
    party_name: Optional[str] = None


class MemoUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    party_type: Optional[str] = None
    party_name: Optional[str] = None
    is_reminder: Optional[bool] = None
    reminder_cycle: Optional[str] = None


# ── 锁定 ──

class LockRequest(BaseModel):
    game_id: str
    channel_id: int = 0
    publisher_name: str = ""
    month: str
    field: str  # "real_revenue" | "settlement_amount"
    value: str | None = None  # null/""/"=" → unlock, number → lock


# ── Ledger ──

class LedgerEntryResponse(BaseModel):
    id: int
    transaction_no: str
    account: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    company_id: Optional[int] = None
    game_id: Optional[str] = None
    month: Optional[str] = None
    debit: float
    credit: float
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    created_at: str

    class Config:
        from_attributes = True


class PaymentRequest(BaseModel):
    entity_type: str  # "channel" | "publisher"
    entity_id: int
    company_id: int
    amount: float
    note: str | None = None


class OpenItemResponse(BaseModel):
    entity_type: str
    entity_id: int
    entity_name: str
    company_id: int
    company_name: str
    game_id: str
    month: str
    open_balance: float


class AccountBalanceResponse(BaseModel):
    ar_balance: float
    ap_balance: float
    monthly_revenue: float
    monthly_cost: float


class MonthlyCloseRequest(BaseModel):
    month: str = Field(..., description="YYYY-MM")


class ProfitExpenseRequest(BaseModel):
    month: str = Field(..., description="所属月份 YYYY-MM")
    company_id: int | None = None
    expense_amount: float = Field(0, description="期间费用")
    other_income: float = Field(0, description="其他业务收入")
