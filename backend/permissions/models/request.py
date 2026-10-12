"""Generic tenant-owned permission registration; no product-specific catalog entries."""
from pydantic import BaseModel, ConfigDict, Field


class PermissionRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    namespace: str = Field(pattern=r"^[a-z][a-z0-9_]{0,15}$")
    resource: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    description: str = Field(min_length=1, max_length=500)
