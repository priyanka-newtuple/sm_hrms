"""Explicit local initialization; never reads or migrates the legacy database."""
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from hrms.config import get_settings


def main():
    settings = get_settings()
    if settings.ENV != "development" or not settings.HRMS_ALLOW_DEV_LOGIN:
        raise RuntimeError("Demo bootstrap is only for explicitly enabled local development")
    command.upgrade(Config(str(Path(__file__).with_name("alembic.ini"))), "head")
    from hrms.seed.seed_data import main as seed
    asyncio.run(seed())


if __name__ == "__main__":
    main()
