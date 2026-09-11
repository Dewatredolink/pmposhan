from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import UUIDAuditMixin


class SchoolProfile(Base, UUIDAuditMixin):
    __tablename__ = "school_profiles"
    __table_args__ = (UniqueConstraint("school_id", name="uq_school_profile_school"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    kitchen_type: Mapped[str] = mapped_column(String(40), default="SCHOOL_KITCHEN", nullable=False)
    cooking_agency: Mapped[str | None] = mapped_column(String(200), nullable=True)
    headmaster_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meal_incharge_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    school = relationship("School")


class DailyAttendance(Base, UUIDAuditMixin):
    __tablename__ = "daily_attendance"
    __table_args__ = (UniqueConstraint("school_id", "meal_date", name="uq_daily_attendance_school_date"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    meal_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    class_1_5_enrolled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    class_1_5_present: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    class_6_8_enrolled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    class_6_8_present: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False, index=True)
    entered_by_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    entered_by_username: Mapped[str] = mapped_column(String(120), nullable=False)
    verified_by_subject: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_by_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    school = relationship("School")


class DailyMealEntry(Base, UUIDAuditMixin):
    __tablename__ = "daily_meal_entries"
    __table_args__ = (UniqueConstraint("school_id", "meal_date", name="uq_daily_meal_school_date"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    meal_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    menu_id: Mapped[str] = mapped_column(ForeignKey("menus.id", ondelete="RESTRICT"), nullable=False, index=True)
    meals_class_1_5: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meals_class_6_8: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_meals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasting_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hygiene_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False, index=True)
    entered_by_subject: Mapped[str] = mapped_column(String(64), nullable=False)
    entered_by_username: Mapped[str] = mapped_column(String(120), nullable=False)
    verified_by_subject: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_by_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    school = relationship("School")
    menu = relationship("Menu")
