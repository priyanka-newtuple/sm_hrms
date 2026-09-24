from __future__ import annotations

import httpx
import pytest

from common.data_model import RemoteFilesConfiguration
from exceptions import ValidationError
from remote_files.manager import RemoteFilesServiceManager


def _manager(*, enabled: bool = True) -> RemoteFilesServiceManager:
    return RemoteFilesServiceManager(
        RemoteFilesConfiguration(
            enabled=enabled,
            timeout_seconds=1,
            max_size_bytes=1024,
            max_redirects=1,
            fetch_concurrency=2,
        )
    )


def test_remote_files_service_rejects_non_https_before_network_access() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        _manager().fetch("http://example.com/image.jpg")


def test_remote_files_service_reports_each_failure_independently() -> None:
    results = _manager().fetch_many(
        ["http://one.example/a.jpg", "http://two.example/b.jpg"]
    )

    assert set(results) == {"http://one.example/a.jpg", "http://two.example/b.jpg"}
    assert all(isinstance(result, ValidationError) for result in results.values())


def test_disabled_remote_files_service_rejects_without_fetching() -> None:
    results = _manager(enabled=False).fetch_many(["https://example.com/image.jpg"])

    result = results["https://example.com/image.jpg"]
    assert isinstance(result, ValidationError)
    assert "disabled" in str(result)


def test_remote_files_service_rejects_extensions_generic_document_cannot_store() -> None:
    response = httpx.Response(200, request=httpx.Request("GET", "https://example.com/image.webp"))

    with pytest.raises(ValidationError, match="not supported for bulk import"):
        _manager()._filename(response, "https://example.com/image.webp", "image/webp")


def test_remote_files_service_normalizes_jpeg_to_supported_jpg_extension() -> None:
    response = httpx.Response(200, request=httpx.Request("GET", "https://example.com/image.jpeg"))

    assert _manager()._filename(
        response, "https://example.com/image.jpeg", "image/jpeg"
    ) == "image.jpg"
