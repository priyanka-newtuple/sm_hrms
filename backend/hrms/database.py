from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, with_loader_criteria

from hrms.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
class HrmsSession(Session):
    """Scoped session separate from the platform's other persistence modules."""


AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False, sync_session_class=HrmsSession)


class Base(DeclarativeBase):
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=lambda: settings.HRMS_ORGANIZATION_ID)


@event.listens_for(HrmsSession, "do_orm_execute")
def scope_query(execute_state):
    """Include aliases, relationship loads, aggregates, bulk updates and deletes."""
    org_id = settings.HRMS_ORGANIZATION_ID
    if execute_state.is_select or execute_state.is_update or execute_state.is_delete:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(Base, lambda model: model.organization_id == org_id, include_aliases=True)
        )


@event.listens_for(HrmsSession, "before_flush")
def scope_writes(session, flush_context, instances):
    for item in session.new | session.dirty | session.deleted:
        if isinstance(item, Base):
            if item.organization_id is None and item in session.new:
                item.organization_id = settings.HRMS_ORGANIZATION_ID
            if item.organization_id != settings.HRMS_ORGANIZATION_ID:
                raise ValueError("Cross-organization write rejected")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
