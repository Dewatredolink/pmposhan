from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import UUIDAuditMixin
from app.db.session import Base

class District(Base, UUIDAuditMixin):
    __tablename__ = "districts"
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_mr: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class Block(Base, UUIDAuditMixin):
    __tablename__ = "blocks"
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_mr: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    district = relationship("District")

class Cluster(Base, UUIDAuditMixin):
    __tablename__ = "clusters"
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    block_id: Mapped[str] = mapped_column(ForeignKey("blocks.id", ondelete="RESTRICT"), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_mr: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    block = relationship("Block")

class School(Base, UUIDAuditMixin):
    __tablename__ = "schools"
    __table_args__ = (UniqueConstraint("udise_code", name="uq_school_udise"),)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    udise_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("clusters.id", ondelete="RESTRICT"), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(250), nullable=False)
    name_mr: Mapped[str] = mapped_column(String(250), nullable=False)
    village: Mapped[str | None] = mapped_column(String(200), nullable=True)
    class_1_5_strength: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    class_6_8_strength: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cluster = relationship("Cluster")
