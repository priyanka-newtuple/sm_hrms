from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin


class _ReferenceValue(UUIDPkMixin, TimestampMixin):
    """Shared columns for administrator-maintained workforce reference values."""

    __abstract__ = True

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class Department(_ReferenceValue, Base):
    __tablename__ = "departments"


class Designation(_ReferenceValue, Base):
    __tablename__ = "designations"


class ProjectRole(_ReferenceValue, Base):
    __tablename__ = "project_roles"
