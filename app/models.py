import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReceiptStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    paid = "paid"


class UnitStatus(str, enum.Enum):
    unpaid = "unpaid"
    partial = "partial"
    paid = "paid"


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[ReceiptStatus] = mapped_column(Enum(ReceiptStatus), default=ReceiptStatus.draft, nullable=False)
    image_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="selectin"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="selectin"
    )


class ReceiptItem(Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    qty_total: Mapped[int] = mapped_column(nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    amount_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    receipt: Mapped["Receipt"] = relationship(back_populates="items", lazy="joined")
    units: Mapped[list["ItemUnit"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", lazy="selectin", order_by="ItemUnit.unit_index"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("qty_total > 0", name="ck_items_qty_positive"),)


class ItemUnit(Base):
    __tablename__ = "item_units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    unit_index: Mapped[int] = mapped_column(nullable=False)
    amount_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    amount_paid: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    status: Mapped[UnitStatus] = mapped_column(Enum(UnitStatus), default=UnitStatus.unpaid, nullable=False)

    item: Mapped["ReceiptItem"] = relationship(back_populates="units", lazy="joined")
    payments: Mapped[list["Payment"]] = relationship(back_populates="unit", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("item_id", "unit_index", name="uq_item_unit_index"),
        CheckConstraint("amount_paid >= 0", name="ck_unit_amount_paid_non_negative"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item_units.id", ondelete="CASCADE"))
    payer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    receipt: Mapped["Receipt"] = relationship(back_populates="payments", lazy="joined")
    item: Mapped["ReceiptItem"] = relationship(back_populates="payments", lazy="joined")
    unit: Mapped["ItemUnit"] = relationship(back_populates="payments", lazy="joined")

