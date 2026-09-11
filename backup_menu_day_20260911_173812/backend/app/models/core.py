from datetime import date
from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import UUIDAuditMixin
from app.db.session import Base

class AcademicYear(Base, UUIDAuditMixin):
    __tablename__ = "academic_years"
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

class Translation(Base, UUIDAuditMixin):
    __tablename__ = "translations"
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    text_en: Mapped[str] = mapped_column(String(500), nullable=False)
    text_mr: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="ui", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class Menu(Base, UUIDAuditMixin):
    __tablename__ = "menus"
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_mr: Mapped[str] = mapped_column(String(200), nullable=False)
    week_pattern: Mapped[str] = mapped_column(String(10), nullable=False)  # W13/W24
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 Monday ... 6 Saturday
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class Ingredient(Base, UUIDAuditMixin):
    __tablename__ = "ingredients"
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_mr: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    reorder_level: Mapped[float] = mapped_column(Numeric(14,3), default=0, nullable=False)
    safety_stock: Mapped[float] = mapped_column(Numeric(14,3), default=0, nullable=False)
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class Recipe(Base, UUIDAuditMixin):
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("menu_id", "ingredient_id", "student_group", "effective_from", name="uq_recipe_version"),)
    menu_id: Mapped[str] = mapped_column(ForeignKey("menus.id", ondelete="RESTRICT"), nullable=False, index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True)
    student_group: Mapped[str] = mapped_column(String(20), nullable=False) # CLASS_1_5/CLASS_6_8/ALL
    qty_per_student: Mapped[float] = mapped_column(Numeric(14,6), nullable=False)
    measurement_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    menu = relationship("Menu")
    ingredient = relationship("Ingredient")
