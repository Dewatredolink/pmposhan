from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import UUIDAuditMixin


class StockLoan(Base, UUIDAuditMixin):
    __tablename__ = "stock_loans"
    __table_args__ = (UniqueConstraint("school_id", "loan_no", name="uq_stock_loan_school_no"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    loan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    loan_no: Mapped[str] = mapped_column(String(80), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # RECEIVED / GIVEN
    counterparty_name: Mapped[str] = mapped_column(String(250), nullable=False)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    entered_by_username: Mapped[str] = mapped_column(String(120), nullable=False)

    school = relationship("School")
    ingredient = relationship("Ingredient")


class BmiRecord(Base, UUIDAuditMixin):
    __tablename__ = "bmi_records"

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    measurement_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    student_identifier: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    student_name: Mapped[str] = mapped_column(String(250), nullable=False)
    class_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    bmi: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    entered_by_username: Mapped[str] = mapped_column(String(120), nullable=False)

    school = relationship("School")
