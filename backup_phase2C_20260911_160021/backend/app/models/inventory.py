from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import UUIDAuditMixin


class StockReceipt(Base, UUIDAuditMixin):
    __tablename__ = "stock_receipts"
    __table_args__ = (UniqueConstraint("school_id", "receipt_no", name="uq_stock_receipt_school_no"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    receipt_no: Mapped[str] = mapped_column(String(80), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    entered_by_username: Mapped[str] = mapped_column(String(120), nullable=False)

    school = relationship("School")
    lines = relationship("StockReceiptLine", back_populates="receipt", cascade="all, delete-orphan")


class StockReceiptLine(Base, UUIDAuditMixin):
    __tablename__ = "stock_receipt_lines"

    receipt_id: Mapped[str] = mapped_column(ForeignKey("stock_receipts.id", ondelete="CASCADE"), nullable=False, index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    receipt = relationship("StockReceipt", back_populates="lines")
    ingredient = relationship("Ingredient")


class StockTransaction(Base, UUIDAuditMixin):
    __tablename__ = "stock_transactions"
    __table_args__ = (
        UniqueConstraint(
            "school_id", "ingredient_id", "reference_type", "reference_id", "transaction_type",
            name="uq_stock_transaction_reference"
        ),
    )

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)  # signed: in +, out -
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    entered_by_username: Mapped[str] = mapped_column(String(120), nullable=False)

    school = relationship("School")
    ingredient = relationship("Ingredient")
