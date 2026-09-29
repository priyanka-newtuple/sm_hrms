from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "changes_requested", "reject"]
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=4000)


class ProjectVersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
