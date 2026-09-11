from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import UUIDAuditMixin


class MonthlySchoolReturn(Base, UUIDAuditMixin):
    __tablename__ = "monthly_school_returns"
    __table_args__ = (
        UniqueConstraint("school_id", "year", "month", name="uq_monthly_return_school_period"),
    )

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    recorded_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incomplete_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attendance_class_1_5: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attendance_class_6_8: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meals_class_1_5: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meals_class_6_8: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_meals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasting_exception_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hygiene_exception_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False, index=True)
    generated_by_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by_username: Mapped[str] = mapped_column(String(120), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_by_subject: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_by_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cluster_reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cluster_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    block_approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    block_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    school = relationship("School")
    actions = relationship("MonthlyReturnAction", back_populates="monthly_return", cascade="all, delete-orphan")


class MonthlyReturnAction(Base, UUIDAuditMixin):
    __tablename__ = "monthly_return_actions"

    monthly_return_id: Mapped[str] = mapped_column(ForeignKey("monthly_school_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_username: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    monthly_return = relationship("MonthlySchoolReturn", back_populates="actions")
