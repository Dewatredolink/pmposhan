from datetime import date
from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from app.models.base import UUIDAuditMixin

class SchoolCalendarDay(Base, UUIDAuditMixin):
    __tablename__ = 'school_calendar_days'
    __table_args__ = (UniqueConstraint('school_id','calendar_date',name='uq_school_calendar_day'),)
    school_id: Mapped[str] = mapped_column(ForeignKey('schools.id', ondelete='CASCADE'), nullable=False, index=True)
    calendar_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    day_type: Mapped[str] = mapped_column(String(30), default='WORKING', nullable=False, index=True)
    meal_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    title_en: Mapped[str|None] = mapped_column(String(200), nullable=True)
    title_mr: Mapped[str|None] = mapped_column(String(200), nullable=True)
    remarks: Mapped[str|None] = mapped_column(Text, nullable=True)
    school = relationship('School')
