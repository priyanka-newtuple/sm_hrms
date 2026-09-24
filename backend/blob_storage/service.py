"""Azure Blob Storage SAS URL refresh service."""

from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from azure.storage.blob import BlobSasPermissions, generate_blob_sas

from common.logger import logger

_SAS_EXPIRY_SECONDS = 3600
# Regenerate 2 min before expiry so callers never receive an about-to-expire URL.
_CACHE_REFRESH_BUFFER_SECONDS = 120
_MAX_CACHE_SIZE = 1000


class BlobStorageService:
    """Generates fresh SAS read URLs for blobs stored in a single Azure container."""

    def __init__(self) -> None:
        self._account_name: str = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "").strip()
        self._account_key: str = os.environ.get("AZURE_STORAGE_ACCOUNT_KEY", "").strip()
        self._container_name: str = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "").strip()
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def is_configured(self) -> bool:
        """Return True when all three Azure credentials are present."""
        return bool(self._account_name) and bool(self._account_key) and bool(self._container_name)

    def extract_blob_path(self, sas_url: str) -> str | None:
        """Return the blob path (within the container) from a SAS URL, or None on mismatch."""
        try:
            parsed = urlparse(sas_url)
            path = parsed.path.lstrip("/")
            prefix = self._container_name + "/"
            if not path.startswith(prefix):
                return None
            return path[len(prefix) :]
        except Exception:
            return None

    def refresh_url(self, blob_path: str) -> str | None:
        """Return a cached or newly generated SAS read URL for *blob_path*."""
        if not self.is_configured():
            return None
        now = time.time()
        with self._lock:
            cached = self._cache.get(blob_path)
            if cached and now < cached[1] - _CACHE_REFRESH_BUFFER_SECONDS:
                return cached[0]
            if len(self._cache) >= _MAX_CACHE_SIZE:
                sorted_keys = sorted(self._cache, key=lambda k: self._cache[k][1])
                for key in sorted_keys[: _MAX_CACHE_SIZE // 2]:
                    del self._cache[key]
        try:
            expiry = datetime.now(tz=UTC) + timedelta(seconds=_SAS_EXPIRY_SECONDS)
            sas_token = generate_blob_sas(
                account_name=self._account_name,
                container_name=self._container_name,
                blob_name=blob_path,
                account_key=self._account_key,
                permission=BlobSasPermissions(read=True),
                expiry=expiry,
            )
            url = (
                f"https://{self._account_name}.blob.core.windows.net"
                f"/{self._container_name}/{blob_path}?{sas_token}"
            )
            with self._lock:
                self._cache[blob_path] = (url, expiry.timestamp())
            return url
        except Exception as exc:
            logger.warning(
                "blob_storage refresh_url failed", extra={"blob_path": blob_path, "error": str(exc)}
            )
            return None

    def resolve_field(self, data: dict[str, object], dotpath: str) -> str | None:
        """Navigate a dot-path into *data* supporting list indices (e.g. ``photos.0.url``)."""
        current: object = data
        for segment in dotpath.split("."):
            if isinstance(current, list):
                try:
                    current = current[int(segment)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(current, dict):
                current = current.get(segment)
            else:
                return None
            if current is None:
                return None
        return current if isinstance(current, str) else None

    def get_fresh_url(self, data: dict[str, object], dotpath: str) -> str | None:
        """Resolve *dotpath* from entity data and return a fresh SAS URL, or the stored value if not configured."""
        stored_url = self.resolve_field(data, dotpath)
        if stored_url is None:
            return None
        if not self.is_configured():
            return stored_url
        blob_path = self.extract_blob_path(stored_url)
        if blob_path is None:
            return stored_url
        return self.refresh_url(blob_path) or stored_url

    @staticmethod
    def _with_value_at_path(node: object, segments: list[str], value: str) -> object | None:
        """Return a copy of *node* with *value* set at the remaining path
        *segments*, copying only the containers actually on the path — the
        rest of the structure is shared by reference, not deep-copied.
        Returns None (no-op) if the path doesn't resolve to an existing
        string leaf, so this never partially mutates anything.

        `record.data` here is a plain dict deserialized fresh per request
        (not a live ORM-tracked object), but this stays copy-on-write rather
        than in-place regardless — safer against any future caching layer
        and impossible to accidentally leak into another request's view."""
        if not segments:
            return None
        segment, rest = segments[0], segments[1:]
        if isinstance(node, list):
            try:
                idx = int(segment)
            except ValueError:
                return None
            if not (0 <= idx < len(node)):
                return None
            if not rest:
                if not isinstance(node[idx], str):
                    return None
                updated = list(node)
                updated[idx] = value
                return updated
            child = BlobStorageService._with_value_at_path(node[idx], rest, value)
            if child is None:
                return None
            updated = list(node)
            updated[idx] = child
            return updated
        if isinstance(node, dict):
            if segment not in node:
                return None
            if not rest:
                if not isinstance(node[segment], str):
                    return None
                updated = dict(node)
                updated[segment] = value
                return updated
            child = BlobStorageService._with_value_at_path(node[segment], rest, value)
            if child is None:
                return None
            updated = dict(node)
            updated[segment] = child
            return updated
        return None

    def refresh_field(self, data: dict[str, object], dotpath: str) -> dict[str, object] | None:
        """Return a new `data` dict with the blob URL at *dotpath* replaced by
        a fresh one, or None (no-op) if the path is missing/not a blob
        URL/not configured — callers keep using their original `data`
        unchanged in that case. Never mutates the input."""
        fresh = self.get_fresh_url(data, dotpath)
        if fresh is None:
            return None
        updated = self._with_value_at_path(data, dotpath.split("."), fresh)
        return updated if isinstance(updated, dict) else None
