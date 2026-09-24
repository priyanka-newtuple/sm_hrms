"""Secure, bounded retrieval of externally hosted files."""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.message import Message
from hashlib import sha256
from typing import TYPE_CHECKING
from urllib.parse import unquote, urljoin, urlparse

import httpx

from common.outbound_http import resolve_safe_target
from connectors.models.interface import HEADER_HOST
from exceptions import ValidationError
from remote_files.models.interface import FetchedRemoteFile

if TYPE_CHECKING:
    from common.data_model import RemoteFilesConfiguration


class RemoteFilesServiceManager:
    """Fetch public HTTPS files with pinned DNS and strict resource limits."""

    _SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
    # Remote files are persisted under the system generic_document type. Keep
    # this contract aligned with that type so a fetch cannot succeed only to be
    # rejected moments later by filehandler.upload_file.
    _SUPPORTED_EXTENSIONS = frozenset(
        {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".png", ".jpg"}
    )

    def __init__(self, config: RemoteFilesConfiguration) -> None:
        self.enabled = config.enabled
        self.timeout_seconds = config.timeout_seconds
        self.max_size_bytes = config.max_size_bytes
        self.max_redirects = config.max_redirects
        self.concurrency = max(1, config.fetch_concurrency)

    def fetch_many(self, urls: list[str]) -> dict[str, FetchedRemoteFile | Exception]:
        unique_urls = list(dict.fromkeys(urls))
        if not unique_urls:
            return {}
        if not self.enabled:
            return {
                url: ValidationError("remote file retrieval is disabled")
                for url in unique_urls
            }
        results: dict[str, FetchedRemoteFile | Exception] = {}
        with ThreadPoolExecutor(max_workers=min(self.concurrency, len(unique_urls))) as executor:
            futures = {executor.submit(self.fetch, url): url for url in unique_urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    results[url] = future.result()
                except Exception as exc:
                    results[url] = exc
        return results

    def fetch(self, source_url: str) -> FetchedRemoteFile:
        current_url = source_url.strip()
        if urlparse(current_url).scheme.lower() != "https":
            raise ValidationError("remote files must use HTTPS")
        timeout = httpx.Timeout(self.timeout_seconds)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            for redirect_count in range(self.max_redirects + 1):
                target = resolve_safe_target(current_url, allow_private_hosts=False)
                headers = {HEADER_HOST: target.host_header} if target.host_header else {}
                request = client.build_request("GET", target.request_url, headers=headers)
                if target.sni_hostname:
                    request.extensions["sni_hostname"] = target.sni_hostname
                response = client.send(request, stream=True)
                try:
                    if response.is_redirect:
                        if redirect_count >= self.max_redirects:
                            raise ValidationError("remote file exceeded redirect limit")
                        location = response.headers.get("location")
                        if not location:
                            raise ValidationError("remote file redirect has no location")
                        current_url = urljoin(current_url, location)
                        if urlparse(current_url).scheme.lower() != "https":
                            raise ValidationError("remote file redirected outside HTTPS")
                        continue
                    if response.status_code < 200 or response.status_code >= 300:
                        raise ValidationError(f"remote file returned HTTP {response.status_code}")
                    declared_size = response.headers.get("content-length")
                    if declared_size and int(declared_size) > self.max_size_bytes:
                        raise ValidationError("remote file exceeds the configured size limit")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > self.max_size_bytes:
                            raise ValidationError("remote file exceeds the configured size limit")
                    if not content:
                        raise ValidationError("remote file is empty")
                    content_type = response.headers.get("content-type", "application/octet-stream")
                    content_type = content_type.split(";", 1)[0].strip().lower()
                    return FetchedRemoteFile(
                        source_url=source_url,
                        final_url=current_url,
                        filename=self._filename(response, current_url, content_type),
                        content_type=content_type,
                        content=bytes(content),
                        sha256=sha256(content).hexdigest(),
                        etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"),
                    )
                finally:
                    response.close()
        raise ValidationError("remote file could not be fetched")

    def _filename(self, response: httpx.Response, url: str, content_type: str) -> str:
        disposition = Message()
        disposition["content-disposition"] = response.headers.get("content-disposition", "")
        filename = disposition.get_filename() or os.path.basename(unquote(urlparse(url).path))
        filename = self._SAFE_FILENAME.sub("_", filename or "remote-file").strip(" .")
        extension = os.path.splitext(filename)[1].lower()
        if extension == ".jpeg":
            filename = f"{os.path.splitext(filename)[0]}.jpg"
            extension = ".jpg"
        if not extension:
            extension = {
                "application/pdf": ".pdf",
                "application/msword": ".doc",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/vnd.ms-excel": ".xls",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                "text/csv": ".csv",
                "image/png": ".png",
                "image/jpeg": ".jpg",
            }.get(content_type, "")
            filename = f"{filename}{extension}"
        if not extension:
            raise ValidationError("remote file has no supported file extension")
        if extension not in self._SUPPORTED_EXTENSIONS:
            raise ValidationError(
                f"remote file extension '{extension}' is not supported for bulk import"
            )
        return filename[:240]
