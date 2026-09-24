from types import SimpleNamespace
from unittest.mock import MagicMock

from organizations.db_models import OrganizationStatus
from organizations.manager import OrganizationsServiceManager


def _organization(*, status: str = OrganizationStatus.ACTIVE.value) -> SimpleNamespace:
    return SimpleNamespace(
        id="org-1",
        name="Acme",
        slug="acme",
        logo_url=None,
        domain="acme.test",
        settings={},
        status=status,
        requested_by_user_id=None,
        created_at=None,
        updated_at=None,
    )


def test_create_organization_provisions_default_file_types() -> None:
    organizations = MagicMock()
    organizations.create.return_value = _organization()
    filehandler = MagicMock()
    manager = OrganizationsServiceManager(
        organizations,
        filehandler_service_manager=filehandler,
    )

    manager.create_organization(MagicMock(), name="Acme")

    filehandler.seed_file_types.assert_called_once_with("org-1")


def test_approve_organization_provisions_default_file_types() -> None:
    organizations = MagicMock()
    organizations.get_by_id.return_value = _organization(
        status=OrganizationStatus.PENDING.value,
    )
    organizations.approve_org.return_value = _organization()
    filehandler = MagicMock()
    manager = OrganizationsServiceManager(
        organizations,
        filehandler_service_manager=filehandler,
    )

    manager.approve_organization(MagicMock(), "org-1")

    filehandler.seed_file_types.assert_called_once_with("org-1")
