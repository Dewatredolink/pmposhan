from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import UUIDAuditMixin
from app.db.session import Base


class UserSchoolAccess(Base, UUIDAuditMixin):
    __tablename__ = "user_school_access"
    __table_args__ = (
        UniqueConstraint("keycloak_subject", "school_id", "role", name="uq_user_school_role"),
    )

    keycloak_subject: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    school_id: Mapped[str | None] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    preferred_language: Mapped[str] = mapped_column(String(2), default="mr", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    school = relationship("School")
