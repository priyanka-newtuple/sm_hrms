from __future__ import annotations

import uuid

from sqlalchemy import ARRAY, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hrms.authz.enums import Action, DataProfile, FeatureKey, PermissionKey, RecordScope
from hrms.database import Base
from hrms.models.base import TimestampMixin, UUIDPkMixin


class Role(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    feature_permissions: Mapped[list[RoleFeaturePermission]] = relationship(back_populates="role", cascade="all, delete-orphan")
    permission_keys: Mapped[list[RolePermissionKey]] = relationship(back_populates="role", cascade="all, delete-orphan")


class RoleFeaturePermission(UUIDPkMixin, Base):
    """
    One row per (role, feature) cell of the "Feature Permissions" sheet, translated
    through the "Permission Mapping" sheet into the Action/RecordScope/DataProfile model.
    """

    __tablename__ = "role_feature_permissions"
    __table_args__ = (UniqueConstraint("role_id", "feature_key", name="uq_role_feature"),)

    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"))
    feature_key: Mapped[FeatureKey] = mapped_column(Enum(FeatureKey, name="feature_key"))
    actions: Mapped[list[Action]] = mapped_column(ARRAY(Enum(Action, name="action")))
    record_scope: Mapped[RecordScope] = mapped_column(Enum(RecordScope, name="record_scope"))
    data_profile: Mapped[DataProfile] = mapped_column(Enum(DataProfile, name="data_profile"))

    role: Mapped[Role] = relationship(back_populates="feature_permissions")


class RolePermissionKey(UUIDPkMixin, Base):
    """From the "Permission Keys" sheet — granular sensitive-field flags per role."""

    __tablename__ = "role_permission_keys"
    __table_args__ = (UniqueConstraint("role_id", "permission_key", name="uq_role_permkey"),)

    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"))
    permission_key: Mapped[PermissionKey] = mapped_column(Enum(PermissionKey, name="permission_key"))

    role: Mapped[Role] = relationship(back_populates="permission_keys")
