"""Manager for filehandler orchestration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import re
import threading
import time
import zipfile
from typing import TYPE_CHECKING, Any

from common.enums import ModuleStatus
from common.logger import logger
from exceptions import NotFoundError, ServiceError, ValidationError
from filehandler.models.interface import AgentRunOutcome, FileRecordStatus
from filehandler.models.response import (
    DownloadUrlResponse,
    FilehandlerStatusResponse,
    FileListResponse,
    FileRecordResponse,
    FileTypeListResponse,
    FileTypeResponse,
    FileTypeSeedResponse,
)
from filehandler.models.request import (
    FileListRequest,
    FileTypeCreateRequest,
    FileTypeUpdateRequest,
    FileUploadRequest,
)

if TYPE_CHECKING:
    from filehandler.db_models import FileCreateResult, FilehandlerModelService, FileTypeRecord


# Bound how many background document-processing agent runs execute at once, so a burst of
# uploads cannot spawn unbounded threads / concurrent LLM calls. Excess runs queue on the
# semaphore (blocked threads are cheap) rather than all executing simultaneously.
# The storage_provider value stored on a file row for S3, and the integration
# provider name, deliberately the same string. Azure differs between the two
# ("azure" on the row, "azure_blob" as the integration); that split is
# pre-existing and not worth repeating.
S3_PROVIDER = "s3"

_MAX_CONCURRENT_PROCESSING = 4
# Soft observability threshold — a run exceeding this logs a warning so a hanging/slow
# agent run is visible in logs (a Python thread cannot be force-killed).
_PROCESSING_RUN_WARN_SECONDS = 300


class FilehandlerServiceManager:
    """Owns file metadata lifecycle and dispatch orchestration."""

    def __init__(
        self,
        filehandler_db_model_service: FilehandlerModelService,
        database_service_manager: Any,
        config: Any,
        *dependencies: object,
        integrations_service_manager: Any = None,
        entities_service_manager: Any = None,
    ) -> None:
        self.db_model_service = filehandler_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.integrations_service_manager = integrations_service_manager
        self.entities_service_manager = entities_service_manager
        # Late-bound in main.py (the agent manager is constructed after filehandler).
        # Used to auto-run an agent when a document with Agent Processing is uploaded.
        self.agent_service_manager: Any = None
        # Late-bound in main.py — used to notify the uploader about processing progress.
        self.notifications_service_manager: Any = None
        # Lifecycle tracking for background document-processing runs: bound how many run
        # concurrently and keep a live registry (file_id -> started_at) for observability.
        self._processing_slots = threading.BoundedSemaphore(_MAX_CONCURRENT_PROCESSING)
        self._active_processing: dict[str, float] = {}
        self._active_processing_lock = threading.Lock()
        self.dependencies = list(dependencies)
        self.module_name = "filehandler"
        self._started = False

    def _get_azure_creds(self, organization_id: str) -> dict[str, Any] | None:
        """Return Azure Blob credentials for the org, or None if not configured."""
        if self.integrations_service_manager is None:
            logger.debug("_get_azure_creds: no integrations_service_manager — skipping Azure")
            return None
        provider, creds = self.integrations_service_manager.get_credentials_for_capability(
            organization_id, "storage"
        )
        if provider != "azure_blob":
            logger.debug(
                "_get_azure_creds: storage provider is %r, not azure_blob — skipping Azure", provider
            )
            return None
        if not creds.get("account_url") or not creds.get("container"):
            logger.warning(
                "_get_azure_creds: azure_blob integration missing account_url or container for org %s",
                organization_id,
            )
            return None
        if not creds.get("connection_string") and not creds.get("account_key"):
            logger.warning(
                "_get_azure_creds: azure_blob integration has no connection_string or account_key for org %s — "
                "check that secrets were saved correctly in the integration settings",
                organization_id,
            )
            return None
        return creds

    def _azure_upload(self, creds: dict[str, Any], storage_key: str, content: bytes, content_type: str) -> None:
        from azure.storage.blob import BlobServiceClient, ContentSettings
        conn_str = creds.get("connection_string")
        account_key = creds.get("account_key")
        if conn_str:
            client = BlobServiceClient.from_connection_string(conn_str)
        elif account_key:
            client = BlobServiceClient(creds["account_url"], credential=account_key)
        else:
            raise ServiceError("Azure Blob Storage requires connection_string or account_key")
        client.get_blob_client(creds["container"], storage_key).upload_blob(
            content,
            overwrite=False,
            content_settings=ContentSettings(content_type=content_type),
        )

    def _azure_download(self, creds: dict[str, Any], storage_key: str) -> bytes:
        """Download blob bytes from Azure Blob Storage."""
        from azure.storage.blob import BlobServiceClient

        conn_str = creds.get("connection_string")
        account_key = creds.get("account_key")
        if conn_str:
            client = BlobServiceClient.from_connection_string(conn_str)
        elif account_key:
            client = BlobServiceClient(creds["account_url"], credential=account_key)
        else:
            raise ServiceError("Azure Blob Storage requires connection_string or account_key")
        return client.get_blob_client(creds["container"], storage_key).download_blob().readall()

    def _get_s3_creds(self, organization_id: str) -> dict[str, Any] | None:
        """Return S3 credentials for the org, or None if not configured.

        Mirrors `_get_azure_creds`. `endpoint_url` is optional, so an
        S3-compatible store can be pointed at without one; bucket and region are
        not, and neither is the key pair.
        """
        if self.integrations_service_manager is None:
            logger.debug("_get_s3_creds: no integrations_service_manager — skipping S3")
            return None
        provider, creds = self.integrations_service_manager.get_credentials_for_capability(
            organization_id, "storage"
        )
        if provider != S3_PROVIDER:
            logger.debug("_get_s3_creds: storage provider is %r, not s3 — skipping S3", provider)
            return None
        if not creds.get("bucket") or not creds.get("region"):
            logger.warning(
                "_get_s3_creds: s3 integration missing bucket or region for org %s",
                organization_id,
            )
            return None
        if not creds.get("access_key_id") or not creds.get("secret_access_key"):
            logger.warning(
                "_get_s3_creds: s3 integration has no access_key_id or secret_access_key for org %s — "
                "check that secrets were saved correctly in the integration settings",
                organization_id,
            )
            return None
        return creds

    @staticmethod
    def _s3_client(creds: dict[str, Any]):
        """Build a boto3 S3 client from stored credentials.

        Imported here, like the Azure client, so the dependency is only needed by
        organizations actually configured for S3.
        """
        import boto3

        return boto3.client(
            "s3",
            region_name=creds["region"],
            aws_access_key_id=creds["access_key_id"],
            aws_secret_access_key=creds["secret_access_key"],
            # None means "the real AWS endpoint"; a value points at an
            # S3-compatible store instead.
            endpoint_url=creds.get("endpoint_url") or None,
        )

    def _s3_upload(
        self, creds: dict[str, Any], storage_key: str, content: bytes, content_type: str
    ) -> None:
        """Upload bytes to S3 under the same storage key the row records."""
        self._s3_client(creds).put_object(
            Bucket=creds["bucket"],
            Key=storage_key,
            Body=content,
            ContentType=content_type,
        )

    def _s3_download(self, creds: dict[str, Any], storage_key: str) -> bytes:
        """Download object bytes from S3."""
        response = self._s3_client(creds).get_object(Bucket=creds["bucket"], Key=storage_key)
        return response["Body"].read()

    def _discard_local_file(self, storage_key: str) -> None:
        """Remove the local filesystem copy after a successful Azure upload."""
        try:
            db = self.db_model_service
            real_path = db._filesystem_root / storage_key
            if real_path.exists():
                real_path.unlink(missing_ok=True)
            else:
                db._legacy_filesystem_path(storage_key).unlink(missing_ok=True)
        except Exception as exc:
            logger.debug(
                "_discard_local_file: failed to remove local copy for storage_key=%r: %s",
                storage_key,
                exc,
            )

    def _sanitize_entity_type_slug(self, name: str) -> str:
        """Convert an entity type display name to a filesystem-safe slug."""
        max_length = self.config._configuration.filehandler_configuration.entity_type_slug_max_length
        slug = name.lower().replace(" ", "_")
        slug = re.sub(r"[^a-z0-9_-]", "", slug)
        return slug[:max_length]

    def _get_file_bytes(
        self,
        organization_id: str,
        row: object,
        error_type: type[Exception] = ValidationError,
    ) -> bytes:
        """Fetch raw file bytes from whichever storage backend the file lives in."""
        provider = getattr(row, "storage_provider", "local")
        storage_key = getattr(row, "storage_key", None)
        if provider == "azure":
            creds = self._get_azure_creds(organization_id)
            if creds is None:
                raise error_type("Azure credentials not configured for this organization")
            return self._azure_download(creds, storage_key)
        if provider == S3_PROVIDER:
            creds = self._get_s3_creds(organization_id)
            if creds is None:
                raise error_type("S3 credentials not configured for this organization")
            return self._s3_download(creds, storage_key)
        file_bytes = self.db_model_service.get_filesystem_content_by_storage_key(storage_key)
        if file_bytes is None:
            raise error_type("file content not found in filesystem storage")
        return file_bytes

    def get_file_bytes(self, organization_id: str, file_id: str) -> bytes | None:
        """Return raw bytes for a stored file from whichever backend it lives in
        (local filesystem or Azure Blob), or None if the file row is missing.

        Storage-aware counterpart to ``get_file_content`` — used by background
        workers (e.g. the fileprocessor worker) that must read files regardless
        of where they were uploaded.
        """
        row = self.db_model_service.get_file(organization_id, file_id)
        if row is None:
            return None
        return self._get_file_bytes(organization_id, row)

    @staticmethod
    def _extract_account_key_from_conn_str(conn_str: str) -> str | None:
        """Parse AccountKey= from an Azure Storage connection string."""
        for part in conn_str.split(";"):
            if part.startswith("AccountKey="):
                return part[len("AccountKey="):]
        return None

    def _azure_get_sas_url(self, creds: dict[str, Any], storage_key: str, expiry_minutes: int = 15) -> str:
        from datetime import datetime, timedelta, timezone
        from urllib.parse import urlparse

        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        account_key = creds.get("account_key") or None
        if not account_key and creds.get("connection_string"):
            account_key = self._extract_account_key_from_conn_str(str(creds["connection_string"]))
        if not account_key:
            raise ServiceError(
                "Azure SAS URL generation requires account_key or a connection_string containing AccountKey"
            )

        account_name = urlparse(creds["account_url"]).hostname.split(".")[0]
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=creds["container"],
            blob_name=storage_key,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes),
        )
        return f"{creds['account_url']}/{creds['container']}/{storage_key}?{sas}"

    def start(self) -> None:
        """Start filehandler lifecycle."""

        self._started = True

    def stop(self) -> None:
        """Stop filehandler lifecycle."""

        self._started = False

    def get_status(self) -> FilehandlerStatusResponse:
        """Return lifecycle status for filehandler."""

        return FilehandlerStatusResponse(
            module=self.module_name, status=ModuleStatus.READY.value, started=self._started
        )

    _IMAGE_EXTENSIONS: frozenset[str] = frozenset({
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg",
        ".tiff", ".tif", ".avif", ".heic", ".heif",
    })

    def _validate_thumbnail_extensions(self, allowed_extensions: list[str]) -> None:
        if not any(ext.lower() in self._IMAGE_EXTENSIONS for ext in allowed_extensions):
            raise ValidationError(
                "preview thumbnail file type must allow at least one image extension "
                "(jpg, jpeg, png, gif, webp, bmp, svg, tiff, avif, heic, heif)"
            )

    def create_file_type(
        self, organization_id: str, request: FileTypeCreateRequest
    ) -> FileTypeResponse:
        """Create one file type for actor organization."""
        if request.is_preview_thumbnail:
            self._validate_thumbnail_extensions(list(request.allowed_extensions or []))
        row = self.db_model_service.create_file_type(organization_id, request)
        return self._to_file_type_response(row)

    def list_file_types(
        self, organization_id: str, active_only: bool = True
    ) -> FileTypeListResponse:
        """List file types visible in actor organization."""
        rows = self.db_model_service.list_file_types(organization_id, active_only=active_only)
        return FileTypeListResponse(
            count=len(rows), items=[self._to_file_type_response(row) for row in rows]
        )

    def get_file_type(self, organization_id: str, type_id: str) -> FileTypeResponse:
        """Get one file type by id in actor org scope."""
        row = self.db_model_service.get_file_type(organization_id, type_id)
        if row is None:
            raise NotFoundError("file type not found")
        return self._to_file_type_response(row)

    def update_file_type(
        self, organization_id: str, type_id: str, request: FileTypeUpdateRequest
    ) -> FileTypeResponse:
        """Update one existing file type in actor org scope."""
        if request.is_preview_thumbnail:
            existing = self.db_model_service.get_file_type(organization_id, type_id)
            extensions = list(request.allowed_extensions or (existing.allowed_extensions if existing else []))
            self._validate_thumbnail_extensions(extensions)
        row = self.db_model_service.update_file_type(organization_id, type_id, request)
        return self._to_file_type_response(row)

    def delete_file_type(self, organization_id: str, type_id: str) -> bool:
        """Delete one file type if it is not system-managed."""
        return self.db_model_service.delete_file_type(organization_id, type_id)

    def seed_file_types(self, organization_id: str) -> FileTypeSeedResponse:
        """Seed default file type config values in actor org scope."""
        created = self.db_model_service.seed_default_file_types(organization_id)
        return FileTypeSeedResponse(
            message=f"Seeded {created} default file types", created_count=created
        )

    def upload_file(
        self,
        organization_id: str,
        user_id: str,
        request: FileUploadRequest,
        *,
        skip_agent_dispatch: bool = False,
    ) -> FileRecordResponse:
        """Validate and upload one file into metadata + filesystem store.

        When the file type has agent_processing_enabled in its metadata the
        file is automatically dispatched for processing so the caller does not
        need a separate dispatch call.
        """

        file_type = self.db_model_service.get_file_type(organization_id, request.type_id)
        if file_type is None:
            raise ValidationError("file type not found")
        if not file_type.is_active:
            raise ValidationError("file type is disabled")

        extension = os.path.splitext(request.filename)[1].lower()
        if file_type.allowed_extensions and extension not in file_type.allowed_extensions:
            raise ValidationError(f"file extension '{extension}' is not allowed")

        max_bytes = int(file_type.max_size_mb) * 1024 * 1024
        try:
            file_bytes = base64.b64decode(request.content.encode("utf-8"), validate=True)
        except Exception as exc:
            logger.debug("upload_file invalid base64 content: %s", exc)
            raise ValidationError("invalid base64 file content") from exc
        if len(file_bytes) > max_bytes:
            raise ValidationError("file size exceeds configured max_size_mb")

        self._validate_mime_type(file_bytes, file_type.allowed_extensions)

        entity_type_slug: str | None = None
        if request.owner_entity_id and self.entities_service_manager is not None:
            try:
                entity_type_name = self.entities_service_manager.get_entity_type_name_for_entity(
                    organization_id, request.owner_entity_id
                )
                if entity_type_name:
                    entity_type_slug = self._sanitize_entity_type_slug(entity_type_name)
            except Exception as exc:
                logger.warning(
                    "upload_file: could not resolve entity type slug for entity %s — "
                    "falling back to legacy storage path. Error: %s",
                    request.owner_entity_id,
                    exc,
                )

        type_storage = str(file_type.metadata.get("storage_provider") or "local")
        logger.debug(
            "upload_file: doc type %r has storage_provider=%r", request.type_id, type_storage
        )
        azure_creds = self._get_azure_creds(organization_id) if type_storage == "azure_blob" else None
        if type_storage == "azure_blob" and azure_creds is None:
            logger.warning(
                "upload_file: doc type %r requests azure_blob storage but no valid Azure credentials "
                "found for org %s — falling back to local storage",
                request.type_id,
                organization_id,
            )
        s3_creds = self._get_s3_creds(organization_id) if type_storage == S3_PROVIDER else None
        if type_storage == S3_PROVIDER and s3_creds is None:
            logger.warning(
                "upload_file: doc type %r requests s3 storage but no valid S3 credentials "
                "found for org %s — falling back to local storage",
                request.type_id,
                organization_id,
            )

        result = self.db_model_service.create_file(
            organization_id, request, uploaded_by=user_id, file_bytes=file_bytes,
            storage_provider="local",
            entity_type_slug=entity_type_slug,
        )

        if azure_creds and not result.deduplicated:
            try:
                self._azure_upload(azure_creds, result.record.storage_key, file_bytes, request.content_type)
                self.db_model_service.set_file_storage_provider(
                    organization_id, result.record.file_id, "azure"
                )
                result.record.storage_provider = "azure"
                self._discard_local_file(result.record.storage_key)
            except Exception as exc:
                logger.warning(
                    "Azure upload failed for file %s; file retained in local storage. Error: %s",
                    result.record.file_id,
                    exc,
                    exc_info=True,
                )

        if s3_creds and not result.deduplicated:
            try:
                self._s3_upload(
                    s3_creds, result.record.storage_key, file_bytes, request.content_type
                )
                self.db_model_service.set_file_storage_provider(
                    organization_id, result.record.file_id, S3_PROVIDER
                )
                result.record.storage_provider = S3_PROVIDER
                self._discard_local_file(result.record.storage_key)
            except Exception as exc:
                logger.warning(
                    "S3 upload failed for file %s; file retained in local storage. Error: %s",
                    result.record.file_id,
                    exc,
                    exc_info=True,
                )

        return self._build_upload_response(
            organization_id,
            user_id,
            result,
            file_type,
            skip_agent_dispatch=skip_agent_dispatch,
        )

    # libmagic reports these for any ZIP-based container, including OOXML files
    # (DOCX/XLSX) whose specific type it fails to identify — accepting them
    # requires confirming actual OOXML structure (see _is_ooxml_zip), never on
    # the generic mime alone, or any unrecognized binary would pass validation.
    _OOXML_CONTAINER_MIMES = frozenset({"application/zip", "application/octet-stream"})

    def _validate_mime_type(self, file_bytes: bytes, allowed_extensions: list[str]) -> None:
        try:
            import magic
            # Detect over the full content, not a truncated header: ZIP-based OOXML
            # files (DOCX/XLSX) are only recognized by libmagic from the ZIP central
            # directory at the END of the file, so a truncated read misreports them as
            # application/zip and would wrongly reject valid uploads.
            detected_mime = magic.from_buffer(file_bytes, mime=True)
            allowed_mimes = self._extensions_to_mimes(allowed_extensions)
            if allowed_mimes and detected_mime not in allowed_mimes:
                raise ValidationError(
                    f"file content type '{detected_mime}' does not match allowed types for this document category"
                )
            if detected_mime in self._OOXML_CONTAINER_MIMES and not self._is_ooxml_zip(file_bytes):
                raise ValidationError(
                    f"file content type '{detected_mime}' does not match allowed types for this document category"
                )
        except ImportError:
            logger.warning("python-magic not available; skipping MIME byte validation")

    @staticmethod
    def _is_ooxml_zip(file_bytes: bytes) -> bool:
        """Confirm a zip/octet-stream-detected file is actually an OOXML container.

        Every OOXML format (DOCX/XLSX/PPTX) carries a top-level
        ``[Content_Types].xml`` part — a plain zip archive or an unrelated
        binary that libmagic couldn't fingerprint will not.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                return "[Content_Types].xml" in archive.namelist()
        except zipfile.BadZipFile:
            return False

    def _build_upload_response(
        self,
        organization_id: str,
        user_id: str,
        result: FileCreateResult,
        file_type: FileTypeRecord,
        *,
        skip_agent_dispatch: bool = False,
    ) -> FileRecordResponse:
        row = result.record
        response = self._to_file_response(row)
        if result.deduplicated:
            response.auto_deduplicated = True
            return response
        if skip_agent_dispatch:
            return response
        # If the document type is set up for Agent Processing, auto-run the agent in
        # the background. The agent reads the file (read_document) and, driven by its
        # own prompt, performs the configured post-action via create_entity/update_entity.
        self._maybe_dispatch_agent_processing(organization_id, user_id, row, file_type, response)
        return response

    @staticmethod
    def _agent_processing_enabled(metadata: dict[str, object]) -> bool:
        value = metadata.get("agent_processing_enabled")
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _maybe_dispatch_agent_processing(
        self,
        organization_id: str,
        user_id: str,
        row,
        file_type: FileTypeRecord,
        response: FileRecordResponse,
    ) -> None:
        """Start a background agent run for an agent-processing document type."""
        metadata = dict(file_type.metadata or {})
        if not self._agent_processing_enabled(metadata):
            return
        agent_definition_id = str(metadata.get("agent_definition_id") or "").strip()
        if not agent_definition_id:
            logger.warning(
                "agent processing enabled for type %s but no agent_definition_id set", row.type_id
            )
            return
        if self.agent_service_manager is None:
            logger.warning("agent processing requested but agent_service_manager is not wired")
            return

        post_actions = self._resolve_post_actions(organization_id, file_type)
        # Reflect "processing" immediately so the UI shows it before the run finishes.
        try:
            self.db_model_service.set_file_status(
                organization_id, row.file_id, FileRecordStatus.PROCESSING.value
            )
            response.status = FileRecordStatus.PROCESSING.value
        except Exception as exc:
            logger.warning("could not set PROCESSING status for file %s: %s", row.file_id, exc)
        self._notify_processing(
            organization_id,
            user_id,
            row.file_id,
            "Document processing started",
            f"'{row.filename}' is being processed by an agent.",
        )

        thread = threading.Thread(
            target=self._run_agent_processing,
            args=(
                organization_id,
                user_id,
                row.file_id,
                row.filename,
                agent_definition_id,
                post_actions,
                getattr(row, "owner_entity_id", None),
                getattr(row, "owner_entity_type", None),
            ),
            name=f"agent-processing-{row.file_id}",
            daemon=True,
        )
        thread.start()

    def _resolve_post_actions(
        self, organization_id: str, file_type: FileTypeRecord
    ) -> list[dict[str, object]]:
        """Resolve post-action entity-type names to UUIDs for the agent instruction."""
        raw = (file_type.agent_config or {}).get("post_actions") or []
        resolved: list[dict[str, object]] = []
        for action in raw:
            if not isinstance(action, dict):
                continue
            entry = dict(action)
            entity_type_name = str(action.get("entity_type") or "").strip()
            if entity_type_name and self.entities_service_manager is not None:
                try:
                    record = self.entities_service_manager.get_entity_type_record(
                        organization_id=organization_id, name=entity_type_name
                    )
                    if record is not None:
                        entry["entity_type_id"] = record.entity_type_id
                except Exception as exc:
                    logger.warning(
                        "could not resolve entity_type %r to an id: %s", entity_type_name, exc
                    )
            resolved.append(entry)
        return resolved

    def _run_agent_processing(
        self,
        organization_id: str,
        user_id: str,
        file_id: str,
        filename: str | None,
        agent_definition_id: str,
        post_actions: list[dict[str, object]],
        owner_entity_id: str | None = None,
        owner_entity_type: str | None = None,
    ) -> None:
        """Background thread: run the agent for an uploaded document, then sync file status.

        Concurrency is bounded by ``_processing_slots`` and each run is registered in
        ``_active_processing`` for observability (see ``active_processing_count``).
        """
        # Bound concurrent runs; excess uploads queue here rather than all running at once.
        self._processing_slots.acquire()
        started_at = time.monotonic()
        with self._active_processing_lock:
            self._active_processing[file_id] = started_at
        logger.info(
            "agent processing started file=%s (active=%d)",
            file_id,
            len(self._active_processing),
        )
        try:
            self._run_agent_processing_inner(
                organization_id,
                user_id,
                file_id,
                filename,
                agent_definition_id,
                post_actions,
                owner_entity_id,
                owner_entity_type,
            )
        finally:
            duration = time.monotonic() - started_at
            with self._active_processing_lock:
                self._active_processing.pop(file_id, None)
                remaining = len(self._active_processing)
            self._processing_slots.release()
            log = logger.warning if duration > _PROCESSING_RUN_WARN_SECONDS else logger.info
            log(
                "agent processing finished file=%s in %.1fs (active=%d)",
                file_id,
                duration,
                remaining,
            )

    def active_processing_count(self) -> int:
        """Number of document-processing runs currently in flight (observability)."""
        with self._active_processing_lock:
            return len(self._active_processing)

    def _run_agent_processing_inner(
        self,
        organization_id: str,
        user_id: str,
        file_id: str,
        filename: str | None,
        agent_definition_id: str,
        post_actions: list[dict[str, object]],
        owner_entity_id: str | None = None,
        owner_entity_type: str | None = None,
    ) -> None:
        """Run the agent for an uploaded document, then sync file status."""
        # Lazy import to avoid a module-load import cycle (agent depends on nothing here).
        from agent.models.request import AgentRunRequest

        try:
            actor = {"organization_id": organization_id, "user_id": user_id, "roles": []}
            request = AgentRunRequest(
                definition_id=agent_definition_id,
                input=self._build_agent_instruction(
                    filename, post_actions, owner_entity_id, owner_entity_type
                ),
                document_id=file_id,
            )
            run = self.agent_service_manager.run_agent_for_actor(actor, request)
            run_id = getattr(run, "run_id", None)
            status = getattr(run, "status", None)
            if run_id:
                self.db_model_service.merge_file_metadata(
                    organization_id, file_id, {"agent_run_id": run_id}
                )
            # File status is derived from the run's own status only — not from individual
            # tool-call attempts, which may fail then succeed on retry within the same run.
            if status == AgentRunOutcome.COMPLETED:
                self.db_model_service.set_file_status(
                    organization_id, file_id, FileRecordStatus.PROCESSED.value
                )
                # Surface an entity the agent created (e.g. document-upload-driven
                # entity creation) so callers with no owner_entity_id yet can find it.
                # Only when this run had no owner_entity_id to begin with — an update-
                # flow run (file already attached to a real entity) must never have its
                # file reassigned just because create_entity also happens to appear
                # (however unexpectedly) among this run's tool calls.
                created = self._created_entity_from_tool_calls(run) if not owner_entity_id else None
                if created:
                    self.db_model_service.merge_file_metadata(
                        organization_id,
                        file_id,
                        {
                            "created_entity_id": created["entity_id"],
                            "created_entity_type_id": created["entity_type_id"],
                        },
                    )
                    # The file was uploaded before this entity existed, so it has no
                    # owner_entity_id yet — without this it would stay permanently
                    # invisible in the created entity's own document list.
                    try:
                        self.db_model_service.set_file_owner(
                            organization_id, file_id, created["entity_id"]
                        )
                    except Exception as exc:
                        logger.warning(
                            "could not attach file %s to created entity %s: %s",
                            file_id,
                            created["entity_id"],
                            exc,
                        )
                self._notify_processing(
                    organization_id,
                    user_id,
                    file_id,
                    "Document processed",
                    f"'{filename}' was processed successfully.",
                )
            else:
                reason = str(getattr(run, "error", None) or f"agent run status: {status}")
                self.db_model_service.set_file_status(
                    organization_id, file_id, FileRecordStatus.FAILED.value, failure_reason=reason
                )
                self._notify_processing(
                    organization_id,
                    user_id,
                    file_id,
                    "Document processing failed",
                    f"'{filename}' could not be processed: {reason}",
                )
        except Exception as exc:
            logger.exception("agent processing failed for file %s", file_id)
            try:
                self.db_model_service.set_file_status(
                    organization_id, file_id, FileRecordStatus.FAILED.value, failure_reason=str(exc)
                )
                self._notify_processing(
                    organization_id,
                    user_id,
                    file_id,
                    "Document processing failed",
                    f"'{filename}' could not be processed: {exc}",
                )
            except Exception as status_exc:
                logger.warning(
                    "could not set FAILED status for file %s: %s", file_id, status_exc
                )

    def _notify_processing(
        self,
        organization_id: str,
        recipient_id: str | None,
        file_id: str,
        title: str,
        body: str,
    ) -> None:
        """Best-effort in-app notification about document processing progress.

        Never raises — a notification failure must not affect the upload or the run.
        """
        if self.notifications_service_manager is None or not recipient_id:
            return
        # create_notification only persists when given a real session (db=None writes to
        # an in-memory dict the list endpoint can't see), so open our own engine-bound
        # session (thread-safe) and pass it.
        db_service = getattr(self.db_model_service, "current_db", None)
        engine = getattr(self.db_model_service, "current_db_engine", None)
        if db_service is None or engine is None:
            return
        try:
            with db_service.get_custom_db_contxt_session(engine) as db:
                self.notifications_service_manager.create_notification(
                    db=db,
                    organization_id=organization_id,
                    recipient_id=recipient_id,
                    notification_type="system",
                    entity_id=file_id,
                    entity_type="document",
                    title=title,
                    body=body,
                )
        except Exception as exc:
            logger.warning("could not create processing notification for %s: %s", file_id, exc)

    @classmethod
    def _created_entity_from_tool_calls(cls, run: object) -> dict[str, str] | None:
        """Return {entity_id, entity_type_id} from a successful create_entity call, if any.

        Lets a caller that uploaded a file with no owner_entity_id (document-upload-driven
        entity creation) discover the entity the agent created via the create_entity tool.
        """
        metadata = getattr(run, "metadata", None) or {}
        tool_calls = metadata.get("tool_calls") if isinstance(metadata, dict) else None
        for call in tool_calls or []:
            if not isinstance(call, dict) or call.get("tool") != "create_entity":
                continue
            if call.get("success") is not True:
                continue
            result_raw = call.get("result")
            result = result_raw if isinstance(result_raw, dict) else {}
            output_raw = result.get("output")
            output = output_raw if isinstance(output_raw, dict) else {}
            entity_id = output.get("entity_id")
            if entity_id:
                return {
                    "entity_id": str(entity_id),
                    "entity_type_id": str(output.get("entity_type_id") or ""),
                }
        return None

    @staticmethod
    def _build_agent_instruction(
        filename: str | None,
        post_actions: list[dict[str, object]],
        owner_entity_id: str | None = None,
        owner_entity_type: str | None = None,
    ) -> str:
        """System-generated run input. The *what/fields* live in the agent's own prompt;
        this only tells the agent to read the uploaded document and the post-actions.

        Note: intentionally does NOT pass the filename — the read_document tool already
        knows which file to read (via the run context). Naming the file tempts the model
        to pass it as a document_id, which is not a valid id.
        """
        _ = filename
        lines = [
            "A document was uploaded for processing.",
            "Call the read_document tool with NO arguments — it returns the uploaded "
            "document's content. Then follow your instructions to extract its data.",
        ]
        if owner_entity_id:
            owner = f"entity_id {owner_entity_id}"
            if owner_entity_type:
                owner += f" (type: {owner_entity_type})"
            lines.append(
                f"This document is attached to {owner}. For an update_entity post-action, "
                f"update that entity_id. For a create_entity post-action whose type links to "
                f"the owner's type, pass source_entity_ids=[\"{owner_entity_id}\"] so the new "
                f"record is linked to it."
            )
            if owner_entity_type:
                lines.append(
                    f"The entity type is exactly \"{owner_entity_type}\". Whenever a tool "
                    f"needs an entity type (e.g. get_form_schema), pass \"{owner_entity_type}\" "
                    f"verbatim — do NOT substitute a synonym or a guessed name."
                )
        for action in post_actions:
            action_type = str(action.get("type") or "").strip()
            if not action_type:
                continue
            # update_entity has nothing to update when no owner entity exists yet (e.g.
            # document-upload-driven entity creation) — listing it anyway tempts the
            # model into calling update_entity with a guessed/empty entity_id, which
            # always fails validation. Drop it; create_entity/find_or_create still apply.
            if action_type == "update_entity" and not owner_entity_id:
                continue
            entity_type = str(action.get("entity_type") or "").strip()
            entity_type_id = str(action.get("entity_type_id") or "").strip()
            detail = action_type
            if entity_type:
                detail += f" for entity type '{entity_type}'"
            if entity_type_id:
                detail += f" (entity_type_id: {entity_type_id})"
            lines.append(f"- Post-action: {detail}")
        return "\n".join(lines)

    _MIME_DETECTION_HEADER_BYTES: int = 2048

    _MIME_EXTENSION_MAP: dict[str, list[str]] = {
        ".jpg": ["image/jpeg"],
        ".jpeg": ["image/jpeg"],
        ".png": ["image/png"],
        ".gif": ["image/gif"],
        ".webp": ["image/webp"],
        ".pdf": ["application/pdf"],
        ".csv": ["text/csv", "text/plain"],
        # OOXML files are ZIP containers; libmagic sometimes reports the generic
        # container type instead of the specific OOXML type, so accept those as
        # aliases (the file extension is already validated before this check).
        ".xlsx": [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/zip",
            "application/octet-stream",
        ],
        ".xlsm": [
            "application/vnd.ms-excel.sheet.macroEnabled.12",
            "application/zip",
            "application/octet-stream",
        ],
        ".xls": [
            "application/vnd.ms-excel",
            "application/msexcel",
            "application/x-msexcel",
            "application/x-ole-storage",
        ],
        ".docx": [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
            "application/octet-stream",
        ],
        ".doc": ["application/msword"],
        ".txt": ["text/plain"],
        # libmagic reports XHTML separately from HTML, and both are served by
        # a .html/.htm extension. `text/plain` is deliberately not accepted:
        # libmagic reports it for a bare fragment with no document structure,
        # and allowing it would let any plain text file through as .html.
        ".html": ["text/html", "application/xhtml+xml"],
        ".htm": ["text/html", "application/xhtml+xml"],
    }

    @classmethod
    def _extensions_to_mimes(cls, extensions: list[str]) -> list[str]:
        mimes: list[str] = []
        for ext in extensions:
            mimes.extend(cls._MIME_EXTENSION_MAP.get(ext.lower(), []))
        return mimes

    def list_files(self, organization_id: str, request: FileListRequest) -> FileListResponse:
        """List file records in actor organization."""
        rows = self.db_model_service.list_files(
            organization_id,
            type_id=request.type_id,
            status=request.status,
            owner_entity_id=request.owner_entity_id,
        )
        return FileListResponse(
            count=len(rows), items=[self._to_file_response(row) for row in rows]
        )

    def get_file(
        self, organization_id: str, file_id: str, owner_entity_id: str | None = None
    ) -> FileRecordResponse:
        """Get one file metadata in actor organization."""
        row = self.db_model_service.get_file(organization_id, file_id, owner_entity_id)
        if row is None:
            raise NotFoundError("file not found")
        return self._to_file_response(row)

    def get_file_content(
        self, organization_id: str, file_id: str, *, type_id: str | None = None
    ) -> tuple[bytes, str] | None:
        """Return the raw bytes and content type for a stored file, or None if missing.

        When ``type_id`` is given, the file must be of that type; this lets the
        public content endpoint serve only logos rather than any org file whose
        id a read-role user can enumerate.
        """
        row = self.db_model_service.get_file(organization_id, file_id)
        if row is None:
            return None
        if type_id is not None and row.type_id != type_id:
            return None
        # Serve from whichever backend the file lives in (Azure or local disk).
        try:
            file_bytes = self._get_file_bytes(organization_id, row)
        except Exception as exc:
            logger.warning(
                "get_file_content: unable to fetch bytes for file %s: %s", file_id, exc
            )
            return None
        return file_bytes, row.content_type

    def copy_file_to_entity(
        self,
        organization_id: str,
        user_id: str,
        *,
        source_file_id: str,
        target_entity_id: str,
        metadata: dict[str, object] | None = None,
    ) -> FileRecordResponse:
        """Copy an existing org file into another entity using the normal file store.

        The copied file gets a new owner entity and metadata marker, but reuses
        the filehandler validation, storage, dedupe, and response mapping paths.
        """
        source = self.db_model_service.get_file(organization_id, source_file_id)
        if source is None:
            raise NotFoundError("source file not found")
        file_bytes = self._get_file_bytes(organization_id, source)
        request = FileUploadRequest(
            type_id=source.type_id,
            filename=source.filename,
            content_type=source.content_type,
            content=base64.b64encode(file_bytes).decode("utf-8"),
            owner_entity_id=target_entity_id,
            metadata={**dict(source.metadata or {}), **dict(metadata or {})},
        )
        copied = self.upload_file(organization_id, user_id, request)
        if metadata:
            merged = self.db_model_service.merge_file_metadata(
                organization_id, copied.file_id, dict(metadata)
            )
            if merged is not None:
                response = self._to_file_response(merged)
                response.auto_deduplicated = copied.auto_deduplicated
                return response
        return copied

    def get_download_url(self, organization_id: str, file_id: str) -> DownloadUrlResponse:
        """Return a URL the client can use to fetch raw file bytes.

        For Azure-stored files a short-lived SAS URL is generated so the browser
        can fetch directly from Azure Blob Storage without proxying through the
        backend. For local files the caller should continue using the /download
        endpoint (blob fetch with auth headers).
        """
        row = self.db_model_service.get_file(organization_id, file_id)
        if row is None:
            raise NotFoundError("file not found")

        if row.storage_provider == "azure":
            creds = self._get_azure_creds(organization_id)
            if creds is not None:
                try:
                    sas_url = self._azure_get_sas_url(creds, row.storage_key, expiry_minutes=15)
                    return DownloadUrlResponse(url=sas_url, provider="azure", expires_in=15 * 60)
                except ServiceError as exc:
                    logger.warning(
                        "Cannot generate SAS URL for file %s: %s; falling back to local download",
                        file_id,
                        exc,
                    )

        return DownloadUrlResponse(
            url=f"/filehandler/{file_id}/download",
            provider="local",
            expires_in=None,
        )

    def delete_file(self, organization_id: str, file_id: str) -> bool:
        """Delete one file metadata/filesystem content in actor organization."""
        return self.db_model_service.delete_file(organization_id, file_id)

    # --- Preview thumbnail signed URL helpers ---

    _THUMBNAIL_URL_TTL = 3600  # 1 hour
    _THUMBNAIL_CACHE_MAX_AGE = 3300  # slightly less than TTL for safe browser caching

    def _thumbnail_signing_secret(self) -> bytes:
        secret = os.getenv("SECRET_KEY", "dev-secret-change-me-in-production")
        return secret.encode("utf-8")

    def _sign_thumbnail_url(self, file_id: str, exp: int) -> str:
        msg = f"{file_id}:{exp}".encode("utf-8")
        return hmac.new(self._thumbnail_signing_secret(), msg, hashlib.sha256).hexdigest()

    def _verify_thumbnail_signature(self, file_id: str, sig: str, exp: int) -> bool:
        expected = self._sign_thumbnail_url(file_id, exp)
        return hmac.compare_digest(expected, sig)

    def has_preview_thumbnail_file_type(self, organization_id: str) -> bool:
        """Whether this org has any file type configured as the preview
        thumbnail — a cheap, entity-independent check callers can hoist
        outside a per-entity loop to skip the (otherwise always-None)
        per-entity file lookup entirely for orgs/workflows that don't use
        this feature."""
        return self.db_model_service.get_preview_thumbnail_file_type(organization_id) is not None

    def get_entity_preview_thumbnail_url(
        self, organization_id: str, entity_id: str, base_url: str = ""
    ) -> str | None:
        """Return a short-lived signed URL for the entity's preview thumbnail, or None."""
        file_type = self.db_model_service.get_preview_thumbnail_file_type(organization_id)
        if file_type is None:
            return None
        file_record = self.db_model_service.get_first_file_for_entity_type(
            organization_id, entity_id, file_type.type_id
        )
        if file_record is None:
            return None
        exp = int(time.time()) + self._THUMBNAIL_URL_TTL
        sig = self._sign_thumbnail_url(file_record.file_id, exp)
        return f"{base_url}/api/filehandler/serve/{file_record.file_id}?sig={sig}&exp={exp}"

    def get_entity_preview_thumbnail_urls(
        self, organization_id: str, entity_ids: set[str], base_url: str = ""
    ) -> dict[str, str]:
        """Build preview URLs for a summary page with two fixed DB lookups."""
        file_type = self.db_model_service.get_preview_thumbnail_file_type(organization_id)
        if file_type is None or not entity_ids:
            return {}
        records = self.db_model_service.get_first_files_for_entities_type(
            organization_id, entity_ids, file_type.type_id
        )
        exp = int(time.time()) + self._THUMBNAIL_URL_TTL
        return {
            entity_id: (
                f"{base_url}/api/filehandler/serve/{record.file_id}"
                f"?sig={self._sign_thumbnail_url(record.file_id, exp)}&exp={exp}"
            )
            for entity_id, record in records.items()
        }

    def serve_signed_thumbnail(
        self, file_id: str, sig: str, exp: int, organization_id: str = ""
    ) -> tuple[bytes, str] | None:
        """Validate signature + expiry then return (bytes, content_type), or None."""
        if int(time.time()) > exp:
            return None
        if not self._verify_thumbnail_signature(file_id, sig, exp):
            return None
        row = self.db_model_service.get_file_by_id(file_id)
        if row is None:
            return None
        try:
            file_bytes = self._get_file_bytes(row.organization_id, row)
        except Exception:
            return None
        return file_bytes, row.content_type

    def read_document_source(
        self,
        organization_id: str,
        document_id: str | None = None,
        storage_key: str | None = None,
    ) -> dict[str, object] | None:
        """Return raw file bytes + metadata for the tools.read_document tool.

        Storage-aware (local filesystem or Azure Blob via ``_get_file_bytes``). The
        actual per-format text extraction is done by the fileprocessor adapters — this
        method only sources the bytes, it does not decode them.
        """

        reference = document_id or storage_key or "unknown"
        row = None
        if document_id:
            row = self.db_model_service.get_file(organization_id, document_id)
        elif storage_key:
            row = self.db_model_service.get_file_by_storage_key(organization_id, storage_key)
        if row is None:
            logger.info("read_document_source: no file row for %s", reference)
            return None
        try:
            file_bytes = self._get_file_bytes(organization_id, row)
        except Exception:
            # Storage read failed (missing local object, Azure creds/download error).
            logger.warning(
                "read_document_source: failed to read bytes for file %s (provider=%s, key=%s)",
                row.file_id,
                getattr(row, "storage_provider", "local"),
                row.storage_key,
                exc_info=True,
            )
            raise
        return {
            "document_id": row.file_id,
            "storage_key": row.storage_key,
            "filename": row.filename,
            "content_type": row.content_type,
            "file_bytes": file_bytes,
            "status": row.status,
            "metadata": dict(row.metadata),
        }

    @staticmethod
    def _to_file_type_response(row) -> FileTypeResponse:
        """Map file type record to API response model."""

        return FileTypeResponse(
            organization_id=row.organization_id,
            type_id=row.type_id,
            display_name=row.display_name,
            description=row.description,
            folder=row.folder,
            allowed_extensions=list(row.allowed_extensions),
            max_size_mb=row.max_size_mb,
            is_active=row.is_active,
            is_system=row.is_system,
            version_control_enabled=bool(getattr(row, "version_control_enabled", False)),
            is_preview_thumbnail=bool(getattr(row, "is_preview_thumbnail", False)),
            upload_contexts=getattr(row, "upload_contexts", None),
            agent_config=getattr(row, "agent_config", None),
            metadata=dict(row.metadata),
        )

    @staticmethod
    def _to_file_response(row) -> FileRecordResponse:
        """Map file record to API response model."""

        return FileRecordResponse(
            file_id=row.file_id,
            organization_id=row.organization_id,
            type_id=row.type_id,
            filename=row.filename,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            storage_key=row.storage_key,
            status=row.status,
            uploaded_by=row.uploaded_by,
            owner_entity_id=row.owner_entity_id,
            owner_entity_type=row.owner_entity_type,
            storage_provider=getattr(row, "storage_provider", "local"),
            metadata=dict(row.metadata),
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
