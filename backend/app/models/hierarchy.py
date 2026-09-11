from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import UUIDAuditMixin


class UserOrgAccess(Base, UUIDAuditMixin):
    __tablename__ = "user_org_access"
    __table_args__ = (
        UniqueConstraint("keycloak_subject", "role", "scope_key", name="uq_user_org_scope"),
    )

    keycloak_subject: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    district_id: Mapped[str | None] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"), nullable=True, index=True)
    block_id: Mapped[str | None] = mapped_column(ForeignKey("blocks.id", ondelete="CASCADE"), nullable=True, index=True)
    cluster_id: Mapped[str | None] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    district = relationship("District")
    block = relationship("Block")
    cluster = relationship("Cluster")
