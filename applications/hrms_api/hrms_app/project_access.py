"""Tenant project access configuration, separate from native workflow definitions."""
from pydantic import BaseModel, ConfigDict, Field
from .errors import AppError
from .policy import PROJECT_CAPABILITIES


class ProjectAccessRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    roles: dict[str, list[str]]


def validate_project_access(roles, known_roles):
    if set(roles) - known_roles:
        raise AppError(422, 'Unknown or internal role in project policy')
    for name, grants in roles.items():
        caps = set(grants)
        if caps - PROJECT_CAPABILITIES:
            raise AppError(422, 'Only project and allocation capabilities can be changed here')
        if caps and 'project:view' not in caps:
            raise AppError(422, f'{name}: enable Projects access before adding permissions')
        if 'allocation:request' in caps and not caps.intersection({'project:manage_all', 'project:manage_assigned'}):
            raise AppError(422, f'{name}: allocation requests require assigned-project or all-project management')
