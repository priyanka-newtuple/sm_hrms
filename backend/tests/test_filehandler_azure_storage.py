"""Unit tests for Azure Blob Storage integration in FilehandlerServiceManager."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from filehandler.db_models import FilehandlerModelService
from filehandler.manager import FilehandlerServiceManager
from filehandler.models.request import (
    FileTypeCreateRequest,
    FileUploadRequest,
)

ORG = "org-azure-test"
USER = "u-test"

_AZURE_ACCOUNT_URL = "https://myaccount.blob.core.windows.net"
_AZURE_CONTAINER = "cases"
_AZURE_ACCOUNT_KEY = "dGVzdGtleWJhc2U2NA=="  # base64-like placeholder
_AZURE_CONN_STR = (
    "DefaultEndpointsProtocol=https;AccountName=myaccount;"
    f"AccountKey={_AZURE_ACCOUNT_KEY};EndpointSuffix=core.windows.net"
)


# ─── helpers ─────────────────────────────────────────────────────────────────


def _azure_creds(*, account_key: str | None = _AZURE_ACCOUNT_KEY, conn_str: str | None = None) -> dict[str, Any]:
    creds: dict[str, Any] = {"account_url": _AZURE_ACCOUNT_URL, "container": _AZURE_CONTAINER}
    if account_key:
        creds["account_key"] = account_key
    if conn_str:
        creds["connection_string"] = conn_str
    return creds


def _fake_integrations_mgr(provider: str | None, creds: dict[str, Any]) -> MagicMock:
    mgr = MagicMock()
    mgr.get_credentials_for_capability.return_value = (provider, creds)
    return mgr


def _build_manager(integrations_mgr=None) -> FilehandlerServiceManager:
    db = FilehandlerModelService(database_service_manager=None)
    mgr = FilehandlerServiceManager(
        db,
        None,
        None,
        integrations_service_manager=integrations_mgr,
    )
    mgr.start()
    return mgr


def _upload_req(*, type_id: str = "generic_text") -> FileUploadRequest:
    return FileUploadRequest(
        type_id=type_id,
        filename="test.txt",
        content_type="text/plain",
        content=base64.b64encode(b"hello azure").decode(),
    )


def _seed_azure_doc_type(mgr: FilehandlerServiceManager, *, storage_provider: str = "azure_blob") -> None:
    req = FileTypeCreateRequest(
        type_id="azure_doc",
        display_name="Azure Doc",
        description="",
        folder="files",
        allowed_extensions=[".txt"],
        max_size_mb=10,
        metadata={"storage_provider": storage_provider},
    )
    mgr.db_model_service.create_file_type(ORG, req)


# ─── _extract_account_key_from_conn_str ───────────────────────────────────────


class TestExtractAccountKeyFromConnStr:
    def test_extracts_key_from_valid_connection_string(self) -> None:
        result = FilehandlerServiceManager._extract_account_key_from_conn_str(_AZURE_CONN_STR)
        assert result == _AZURE_ACCOUNT_KEY

    def test_returns_none_when_account_key_segment_absent(self) -> None:
        conn_str = "DefaultEndpointsProtocol=https;AccountName=myaccount"
        assert FilehandlerServiceManager._extract_account_key_from_conn_str(conn_str) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert FilehandlerServiceManager._extract_account_key_from_conn_str("") is None


# ─── _get_azure_creds ─────────────────────────────────────────────────────────


class TestGetAzureCreds:
    def test_returns_none_when_no_integrations_manager(self) -> None:
        mgr = _build_manager()
        assert mgr._get_azure_creds(ORG) is None

    def test_returns_none_when_provider_is_not_azure_blob(self) -> None:
        fake = _fake_integrations_mgr("s3", _azure_creds())
        mgr = _build_manager(fake)
        assert mgr._get_azure_creds(ORG) is None

    def test_returns_none_when_account_url_missing(self) -> None:
        fake = _fake_integrations_mgr("azure_blob", {"container": _AZURE_CONTAINER, "account_key": _AZURE_ACCOUNT_KEY})
        mgr = _build_manager(fake)
        assert mgr._get_azure_creds(ORG) is None

    def test_returns_none_when_container_missing(self) -> None:
        fake = _fake_integrations_mgr("azure_blob", {"account_url": _AZURE_ACCOUNT_URL, "account_key": _AZURE_ACCOUNT_KEY})
        mgr = _build_manager(fake)
        assert mgr._get_azure_creds(ORG) is None

    def test_returns_none_when_both_secrets_missing(self) -> None:
        # account_url and container present, but no account_key or connection_string
        fake = _fake_integrations_mgr("azure_blob", {"account_url": _AZURE_ACCOUNT_URL, "container": _AZURE_CONTAINER})
        mgr = _build_manager(fake)
        assert mgr._get_azure_creds(ORG) is None

    def test_returns_creds_with_account_key(self) -> None:
        creds = _azure_creds()
        fake = _fake_integrations_mgr("azure_blob", creds)
        mgr = _build_manager(fake)
        assert mgr._get_azure_creds(ORG) == creds

    def test_returns_creds_with_connection_string_only(self) -> None:
        creds = _azure_creds(account_key=None, conn_str=_AZURE_CONN_STR)
        fake = _fake_integrations_mgr("azure_blob", creds)
        mgr = _build_manager(fake)
        assert mgr._get_azure_creds(ORG) == creds


# ─── upload_file — storage routing ────────────────────────────────────────────


class TestUploadFileStorageRouting:
    def test_stays_local_when_doc_type_has_no_storage_provider(self) -> None:
        mgr = _build_manager()
        mgr.db_model_service.seed_default_file_types(ORG)

        with patch.object(mgr, "_azure_upload") as mock_upload:
            result = mgr.upload_file(ORG, USER, _upload_req())

        mock_upload.assert_not_called()
        assert result.storage_provider == "local"

    def test_stays_local_when_doc_type_explicitly_local(self) -> None:
        fake = _fake_integrations_mgr("azure_blob", _azure_creds())
        mgr = _build_manager(fake)
        _seed_azure_doc_type(mgr, storage_provider="local")

        with patch.object(mgr, "_azure_upload") as mock_upload:
            result = mgr.upload_file(ORG, USER, _upload_req(type_id="azure_doc"))

        mock_upload.assert_not_called()
        assert result.storage_provider == "local"

    def test_routes_to_azure_when_doc_type_configured(self) -> None:
        fake = _fake_integrations_mgr("azure_blob", _azure_creds())
        mgr = _build_manager(fake)
        _seed_azure_doc_type(mgr)

        with patch.object(mgr, "_azure_upload") as mock_upload, \
             patch.object(mgr, "_discard_local_file") as mock_discard:
            result = mgr.upload_file(ORG, USER, _upload_req(type_id="azure_doc"))

        mock_upload.assert_called_once()
        mock_discard.assert_called_once()
        assert result.storage_provider == "azure"

    def test_falls_back_to_local_when_azure_upload_raises(self) -> None:
        fake = _fake_integrations_mgr("azure_blob", _azure_creds())
        mgr = _build_manager(fake)
        _seed_azure_doc_type(mgr)

        with patch.object(mgr, "_azure_upload", side_effect=RuntimeError("network error")):
            result = mgr.upload_file(ORG, USER, _upload_req(type_id="azure_doc"))

        assert result.storage_provider == "local"

    def test_stays_local_when_no_valid_azure_creds(self) -> None:
        # provider matches but secrets missing — _get_azure_creds returns None
        fake = _fake_integrations_mgr("azure_blob", {"account_url": _AZURE_ACCOUNT_URL, "container": _AZURE_CONTAINER})
        mgr = _build_manager(fake)
        _seed_azure_doc_type(mgr)

        with patch.object(mgr, "_azure_upload") as mock_upload:
            result = mgr.upload_file(ORG, USER, _upload_req(type_id="azure_doc"))

        mock_upload.assert_not_called()
        assert result.storage_provider == "local"


# ─── get_download_url ─────────────────────────────────────────────────────────


class TestGetDownloadUrl:
    def _upload_as_azure(self, mgr: FilehandlerServiceManager) -> str:
        """Upload a file via the local path then mark it as Azure-stored."""
        mgr.db_model_service.seed_default_file_types(ORG)
        result = mgr.upload_file(ORG, USER, _upload_req())
        mgr.db_model_service.set_file_storage_provider(ORG, result.file_id, "azure")
        return result.file_id

    def test_returns_sas_url_for_azure_file(self) -> None:
        fake_sas = f"{_AZURE_ACCOUNT_URL}/{_AZURE_CONTAINER}/key?sig=xxx"
        fake = _fake_integrations_mgr("azure_blob", _azure_creds())
        mgr = _build_manager(fake)
        file_id = self._upload_as_azure(mgr)

        with patch.object(mgr, "_azure_get_sas_url", return_value=fake_sas):
            resp = mgr.get_download_url(ORG, file_id)

        assert resp.provider == "azure"
        assert resp.url == fake_sas
        assert resp.expires_in == 15 * 60

    def test_falls_back_to_local_when_no_creds(self) -> None:
        mgr = _build_manager()  # no integrations manager → _get_azure_creds returns None
        file_id = self._upload_as_azure(mgr)

        resp = mgr.get_download_url(ORG, file_id)

        assert resp.provider == "local"
        assert f"/filehandler/{file_id}/download" in resp.url

    def test_falls_back_to_local_when_sas_generation_fails(self) -> None:
        from exceptions import ServiceError
        fake = _fake_integrations_mgr("azure_blob", _azure_creds())
        mgr = _build_manager(fake)
        file_id = self._upload_as_azure(mgr)

        with patch.object(mgr, "_azure_get_sas_url", side_effect=ServiceError("no key")):
            resp = mgr.get_download_url(ORG, file_id)

        assert resp.provider == "local"

    def test_returns_local_url_for_local_stored_file(self) -> None:
        mgr = _build_manager()
        mgr.db_model_service.seed_default_file_types(ORG)
        result = mgr.upload_file(ORG, USER, _upload_req())

        resp = mgr.get_download_url(ORG, result.file_id)

        assert resp.provider == "local"
        assert resp.expires_in is None
        assert f"/filehandler/{result.file_id}/download" in resp.url

    def test_raises_not_found_for_unknown_file_id(self) -> None:
        from exceptions import NotFoundError
        mgr = _build_manager()
        with pytest.raises(NotFoundError):
            mgr.get_download_url(ORG, "does-not-exist")


# ─── _get_file_bytes — Azure vs local ────────────────────────────────────────


class TestGetFileBytes:
    def _make_file_record(self, *, storage_provider: str, storage_key: str = "k"):
        record = MagicMock()
        record.storage_provider = storage_provider
        record.storage_key = storage_key
        return record

    def test_reads_from_azure_when_storage_provider_is_azure(self) -> None:
        fake = _fake_integrations_mgr("azure_blob", _azure_creds())
        mgr = _build_manager(fake)
        row = self._make_file_record(storage_provider="azure")

        with patch.object(mgr, "_azure_download", return_value=b"azure bytes") as mock_dl:
            result = mgr._get_file_bytes(ORG, row)

        mock_dl.assert_called_once_with(mgr._get_azure_creds(ORG), "k")
        assert result == b"azure bytes"

    def test_reads_from_local_when_storage_provider_is_local(self) -> None:
        mgr = _build_manager()
        mgr.db_model_service.seed_default_file_types(ORG)
        upload = mgr.upload_file(ORG, USER, _upload_req())
        row = mgr.db_model_service.get_file(ORG, upload.file_id)

        result = mgr._get_file_bytes(ORG, row)
        assert result == b"hello azure"

    def test_raises_when_azure_creds_missing_for_azure_file(self) -> None:
        from exceptions import ValidationError
        mgr = _build_manager()  # no integrations manager
        row = self._make_file_record(storage_provider="azure")

        with pytest.raises(ValidationError, match="Azure credentials not configured"):
            mgr._get_file_bytes(ORG, row)

    def test_raises_when_local_file_not_found_on_disk(self) -> None:
        from exceptions import ValidationError
        mgr = _build_manager()
        row = self._make_file_record(storage_provider="local", storage_key="missing-key")

        with patch.object(
            mgr.db_model_service, "get_filesystem_content_by_storage_key", return_value=None
        ):
            with pytest.raises(ValidationError, match="file content not found"):
                mgr._get_file_bytes(ORG, row)


# ─── read_document_source — reads bytes from correct backend ──────────────────


class TestReadDocumentSourceByteRetrieval:
    def test_fetches_bytes_from_azure_for_azure_file(self) -> None:
        fake = _fake_integrations_mgr("azure_blob", _azure_creds())
        mgr = _build_manager(fake)

        mgr.db_model_service.seed_default_file_types(ORG)
        result = mgr.upload_file(ORG, USER, _upload_req())
        mgr.db_model_service.set_file_storage_provider(ORG, result.file_id, "azure")

        with patch.object(mgr, "_azure_download", return_value=b"hello azure") as mock_dl:
            source = mgr.read_document_source(ORG, document_id=result.file_id)

        mock_dl.assert_called_once()
        assert source["file_bytes"] == b"hello azure"

    def test_raises_when_local_file_missing_from_disk(self) -> None:
        from exceptions import ValidationError

        mgr = _build_manager()
        mgr.db_model_service.seed_default_file_types(ORG)
        result = mgr.upload_file(ORG, USER, _upload_req())

        with patch.object(
            mgr.db_model_service, "get_filesystem_content_by_storage_key", return_value=None
        ):
            with pytest.raises(ValidationError):
                mgr.read_document_source(ORG, document_id=result.file_id)
