from sqlalchemy import (
    Column, Integer, String, Date, ForeignKey, UniqueConstraint, DECIMAL
)
from sqlalchemy.orm import relationship
from .database import Base


class LockMixin:
    """Shared columns for ChannelLock / PublisherLock."""
    locked_real_revenue = Column(DECIMAL(16, 2), nullable=True, comment="锁定真实流水，NULL=公式计算")
    locked_settlement_amount = Column(DECIMAL(16, 2), nullable=True, comment="锁定结算金额，NULL=公式计算")
    confirmed_month = Column(String(7), nullable=True, index=True, comment="已快照的确认月，NULL=未快照")
    created_at = Column(String(30), nullable=False, comment="创建时间")
    updated_at = Column(String(30), nullable=False, comment="更新时间")


class SplitConfigMixin:
    """Shared columns for IncomeSplitConfig / PaymentSplitConfig (date-range effective configs)."""
    split_rate = Column(DECIMAL(10, 4), nullable=False, comment="分成比例")
    channel_fee_rate = Column(DECIMAL(10, 4), nullable=False, comment="通道费率")
    tax_rate = Column(DECIMAL(10, 4), nullable=False, comment="税率")
    effective_from = Column(Date, nullable=False, comment="生效日期")
    effective_to = Column(Date, nullable=True, comment="失效日期, null=永久有效")


class Game(Base):
    __tablename__ = "games"

    game_id = Column(String(50), primary_key=True, comment="游戏编号")
    game_name = Column(String(200), nullable=False, comment="游戏名称")
    game_backend_name = Column(String(200), nullable=True, comment="游戏后台名称")
    discount_rate = Column(DECIMAL(10, 4), nullable=False, comment="折扣率")


class Company(Base):
    __tablename__ = "companies"

    company_id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(200), nullable=False, unique=True, comment="我方对接公司名称")


class CompanyGameMapping(Base):
    """公司-游戏映射表。支持按渠道粒度绑定。

    channel_id=NULL 表示默认兜底（适用所有未指定渠道的游戏）。
    channel_id 非 NULL 表示仅该渠道使用此公司。
    解析优先级: (game_id, channel_id) 精确 → (game_id, NULL) 兜底 → project回退。
    """

    __tablename__ = "company_game_mapping"
    __table_args__ = (
        UniqueConstraint("company_id", "game_id", "channel_id", name="uq_company_game_channel"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.company_id"), nullable=False)
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False)
    channel_id = Column(Integer, ForeignKey("channel_categories.channel_id"), nullable=True,
                       comment="渠道ID，NULL=默认兜底")

    company = relationship("Company")
    game = relationship("Game")
    channel = relationship("ChannelCategory")


class ChannelCompanyMapping(Base):
    """渠道→主体信息映射表。1:1 对应，全量导出时从 PartyInfo 标注每行的公司/渠道主体。"""

    __tablename__ = "channel_company_mappings"

    channel_id = Column(Integer, ForeignKey("channel_categories.channel_id"), primary_key=True, comment="渠道ID")
    party_info_id = Column(Integer, ForeignKey("party_info.id"), nullable=False, comment="主体信息ID")

    channel = relationship("ChannelCategory")
    party_info = relationship("PartyInfo")


class Publisher(Base):
    __tablename__ = "publishers"

    publisher_id = Column(Integer, primary_key=True, autoincrement=True)
    publisher_name = Column(String(200), nullable=False, unique=True, comment="研发商户名称")


class PublisherGameMapping(Base):
    __tablename__ = "publisher_game_mapping"
    __table_args__ = (
        UniqueConstraint("publisher_id", "game_id", name="uq_publisher_game"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    publisher_id = Column(Integer, ForeignKey("publishers.publisher_id"), nullable=False)
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False, index=True)
    project_code = Column(String(100), nullable=True, comment="项目编号")
    project_name = Column(String(200), nullable=True, comment="项目名称")

    publisher = relationship("Publisher")
    game = relationship("Game")


class ChannelCategory(Base):
    __tablename__ = "channel_categories"

    channel_id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String(200), nullable=False, unique=True, comment="渠道名称")


class BackendChannel(Base):
    __tablename__ = "backend_channels"
    __table_args__ = (
        UniqueConstraint("backend_channel_name", "channel_id", name="uq_backend_channel_name_per_category"),
    )

    backend_channel_id = Column(Integer, primary_key=True, autoincrement=True)
    backend_channel_name = Column(String(200), nullable=False, comment="后台渠道名称")
    channel_id = Column(Integer, ForeignKey("channel_categories.channel_id"), nullable=False, index=True)

    channel = relationship("ChannelCategory")


class SubChannel(Base):
    __tablename__ = "sub_channels"
    __table_args__ = (
        UniqueConstraint("sub_channel_name", "backend_channel_id", name="uq_sub_channel_name_per_backend"),
    )

    sub_channel_id = Column(Integer, primary_key=True, autoincrement=True)
    sub_channel_name = Column(String(200), nullable=False, comment="二级渠道名称")
    backend_channel_id = Column(Integer, ForeignKey("backend_channels.backend_channel_id"), nullable=False, index=True)

    backend_channel = relationship("BackendChannel")


class IncomeSplitConfig(Base, SplitConfigMixin):
    __tablename__ = "income_split_config"
    __table_args__ = (
        UniqueConstraint("channel_id", "game_id", "effective_from", name="uq_income_split"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey("channel_categories.channel_id"), nullable=False, index=True)
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False, index=True)

    channel = relationship("ChannelCategory")
    game = relationship("Game")


class PaymentSplitConfig(Base, SplitConfigMixin):
    __tablename__ = "payment_split_config"
    __table_args__ = (
        UniqueConstraint("publisher_id", "game_id", "effective_from", name="uq_payment_split"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    publisher_id = Column(Integer, ForeignKey("publishers.publisher_id"), nullable=False, index=True)
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False, index=True)
    fixed_fee = Column(DECIMAL(16, 2), nullable=False, default=0, comment="固定费用")

    publisher = relationship("Publisher")
    game = relationship("Game")


class RawSettlement(Base):
    """原始流水表 — (channel_id, game_id, month) 聚合粒度。

    Excel 导入时直接聚合写入，消除行级存储和三级渠道 JOIN。
    channel_id/channel_name 在导入时已解析到一级渠道。
    """
    __tablename__ = "raw_settlements"
    __table_args__ = (
        UniqueConstraint("channel_id", "game_id", "month", name="uq_raw_settlement"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey("channel_categories.channel_id"), nullable=False, index=True, comment="一级渠道ID")
    channel_name = Column(String(200), nullable=False, default="", comment="渠道名称 (从ChannelCategory冗余，导入时写入)")
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False, index=True)
    game_name = Column(String(100), nullable=False, default="", comment="游戏名称 (从Game表冗余)")
    month = Column(String(7), nullable=False, index=True, comment="所属月份 YYYY-MM")
    raw_revenue = Column(DECIMAL(16, 2), nullable=False, default=0, comment="聚合原始流水")
    created_at = Column(String(19), nullable=False, comment="创建时间")
    updated_at = Column(String(19), nullable=False, comment="更新时间")

    channel = relationship("ChannelCategory")
    game = relationship("Game")


class Deduction(Base):
    __tablename__ = "deductions"
    __table_args__ = (
        UniqueConstraint("channel_id", "game_id", "month", name="uq_deduction"),
    )

    deduction_id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey("channel_categories.channel_id"), nullable=False, index=True)
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False, index=True)
    month = Column(String(7), nullable=False, comment="所属月份 YYYY-MM", index=True)
    vouchers = Column(DECIMAL(16, 2), nullable=False, default=0, comment="代金券")
    test = Column(DECIMAL(16, 2), nullable=False, default=0, comment="测试")
    welfare = Column(DECIMAL(16, 2), nullable=False, default=0, comment="福利币")
    bad_debt = Column(DECIMAL(16, 2), nullable=False, default=0, comment="坏账")

    channel = relationship("ChannelCategory")
    game = relationship("Game")


class ChannelLock(Base, LockMixin):
    __tablename__ = "channel_locks"
    __table_args__ = (
        UniqueConstraint("channel_id", "game_id", "month", name="uq_channel_lock"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey("channel_categories.channel_id"), nullable=False, index=True)
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False, index=True)
    month = Column(String(7), nullable=False, comment="所属月份 YYYY-MM", index=True)

    channel = relationship("ChannelCategory")
    game = relationship("Game")


class PublisherLock(Base, LockMixin):
    __tablename__ = "publisher_locks"
    __table_args__ = (
        UniqueConstraint("publisher_id", "game_id", "month", name="uq_publisher_lock"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    publisher_id = Column(Integer, ForeignKey("publishers.publisher_id"), nullable=False, index=True)
    game_id = Column(String(50), ForeignKey("games.game_id"), nullable=False, index=True)
    month = Column(String(7), nullable=False, comment="所属月份 YYYY-MM", index=True)

    publisher = relationship("Publisher")
    game = relationship("Game")


class PartyInfo(Base):
    __tablename__ = "party_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    party_type = Column(String(20), nullable=False, comment="类型: our_company / channel / publisher")
    name = Column(String(200), nullable=False, comment="主体名称")
    address = Column(String(500), nullable=False, comment="地址")
    phone = Column(String(50), nullable=True, comment="联系电话")
    bank_name = Column(String(200), nullable=False, comment="开户银行")
    bank_account = Column(String(100), nullable=False, comment="银行账号")
    tax_id = Column(String(50), nullable=False, comment="税号")
    notes = Column(String(500), nullable=True, comment="备注")


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, unique=True, comment="版本号 e.g. 20260430_001")
    description = Column(String(200), nullable=True, comment="描述")
    applied_at = Column(String(30), nullable=False, comment="应用时间")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(50), nullable=False, comment="操作类型")
    detail = Column(String(500), nullable=True, comment="详情")
    user = Column(String(100), nullable=True, comment="操作人")
    created_at = Column(String(30), nullable=False, comment="操作时间")


class BillTemplate(Base):
    __tablename__ = "bill_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="模板名称")
    description = Column(String(500), nullable=True, comment="描述")
    bill_type = Column(String(20), nullable=False, comment="适用类型: income / payment / all")
    file_path = Column(String(500), nullable=False, comment="模板文件存储路径")
    is_default = Column(Integer, default=0, comment="是否默认(0/1)")
    created_at = Column(String(30), nullable=False, comment="创建时间")
    updated_at = Column(String(30), nullable=False, comment="更新时间")


class Memo(Base):
    __tablename__ = "memos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="标题")
    content = Column(String(2000), nullable=True, comment="备忘内容")
    party_type = Column(String(20), nullable=True, comment="关联类型: channel/publisher")
    party_name = Column(String(200), nullable=True, comment="关联商户名称")
    attachment_name = Column(String(200), nullable=True, comment="附件原始文件名")
    attachment_path = Column(String(500), nullable=True, comment="附件存储路径")
    is_reminder = Column(Integer, default=0, comment="是否提醒(0/1)")
    reminder_cycle = Column(String(20), default="none", comment="提醒周期: none/daily/weekly/monthly/yearly")
    created_at = Column(String(30), nullable=False, comment="创建时间")
    updated_at = Column(String(30), nullable=False, comment="更新时间")


class MonthlyClose(Base):
    """月结记录——关闭月份后，新锁定自动路由到当前工作月"""

    __tablename__ = "monthly_closes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String(7), nullable=False, unique=True, index=True, comment="已关闭月份 YYYY-MM")
    closed_at = Column(String(30), nullable=False, comment="关闭时间")


class ArapRecord(Base):
    """ARAP 记录表——从 channel_locks 增量快照生成。

    快照逻辑：POST /api/settlement/arap/snapshot
    只取 channel_locks WHERE confirmed_month IS NULL → 聚合写入。
    每笔 ARAP 记录绑定一个 confirmed_month（确认月），同一锁不会重复快照。
    """

    __tablename__ = "arap_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(20), nullable=False, index=True, comment="channel / publisher")
    entity_id = Column(Integer, nullable=False, index=True)
    entity_name = Column(String(200), nullable=False, default="", comment="渠道/研发商名称")
    company_id = Column(Integer, nullable=True, index=True)
    company_name = Column(String(200), nullable=False, default="", comment="我方公司名称")
    game_id = Column(String(50), nullable=False)
    game_name = Column(String(100), nullable=False, default="")
    month = Column(String(7), nullable=False, index=True, comment="归属月 YYYY-MM（流水所属周期）")
    confirmed_month = Column(String(7), nullable=False, index=True, comment="确认月 YYYY-MM（快照对账确认的月份）")
    settlement_amount = Column(DECIMAL(16, 2), nullable=False, default=0, comment="结算金额 (locked or formula)")
    locked_amount = Column(DECIMAL(16, 2), nullable=True, comment="锁定的结算金额")
    snapshot_at = Column(String(19), nullable=False, comment="快照时间")


class ArapCompanyOverride(Base):
    """ARAP 公司覆盖表——仅用于应付侧，允许用户修改已快照的公司分配。

    覆盖仅影响"应付"pivot 显示，不影响应收侧和原始 arap_records 数据。
    """

    __tablename__ = "arap_company_overrides"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "original_company_id",
                         name="uq_arap_override"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(20), nullable=False, index=True, comment="固定 'publisher'")
    entity_id = Column(Integer, nullable=False, index=True)
    original_company_id = Column(Integer, nullable=False, comment="快照时的 company_id")
    override_company_id = Column(Integer, nullable=False, comment="覆盖后的 company_id")
    override_company_name = Column(String(200), nullable=False, default="")
    created_at = Column(String(19), nullable=False)
    updated_at = Column(String(19), nullable=False)


class PaymentRecord(Base):
    """收付款登记表——记录实际收款/付款。

    每笔收付款通过 FIFO 分配到 arap_records 行（PaymentAllocation）。
    """

    __tablename__ = "payment_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_no = Column(String(30), nullable=False, unique=True, comment="凭证号 RCV-YYYYMMDD-NNN / PMT-YYYYMMDD-NNN")
    entity_type = Column(String(20), nullable=False, index=True, comment="channel / publisher")
    entity_id = Column(Integer, nullable=False, index=True)
    entity_name = Column(String(200), nullable=False, default="")
    company_id = Column(Integer, nullable=True, index=True)
    company_name = Column(String(200), nullable=False, default="")
    amount = Column(DECIMAL(16, 2), nullable=False, comment="收付款金额")
    collection_month = Column(String(7), nullable=False, index=True, comment="收款月 YYYY-MM（实际到账月份）")
    note = Column(String(500), nullable=True)
    created_at = Column(String(30), nullable=False, comment="登记时间")


class PaymentAllocation(Base):
    """收付款冲销明细——FIFO 分配结果，付款金额冲销到具体 ARAP 行。"""

    __tablename__ = "payment_allocations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(Integer, ForeignKey("payment_records.id"), nullable=False, index=True)
    arap_id = Column(Integer, ForeignKey("arap_records.id"), nullable=False)
    allocated_amount = Column(DECIMAL(16, 2), nullable=False, comment="本次冲销金额")


class ProfitExpense(Base):
    """利润表期间费用——(month, company_id) 粒度，用户手动填写"""

    __tablename__ = "profit_expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String(7), nullable=False, index=True, comment="所属月份 YYYY-MM")
    company_id = Column(Integer, ForeignKey("companies.company_id"), nullable=True, index=True, comment="我方主体，NULL=全部")
    expense_amount = Column(DECIMAL(16, 2), nullable=False, default=0, comment="期间费用")
    other_income = Column(DECIMAL(16, 2), nullable=False, default=0, comment="其他业务收入")
    updated_at = Column(String(30), nullable=False, comment="更新时间")
