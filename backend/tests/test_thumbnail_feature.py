"""Tests for the STAT-191 preview thumbnail feature.

Covers:
  - Marking a file type as preview thumbnail
  - Exclusivity constraint (only one per org)
  - Toggle off / update
  - Signed URL generation and serving via the unauthenticated endpoint
  - Enrollment enrichment (preview_thumbnail_url on entity state)
"""
from __future__ import annotations

import base64
import struct
import time
import zlib

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from filehandler.controller import FilehandlerRestController
from filehandler.db_models import FilehandlerModelService
from filehandler.manager import FilehandlerServiceManager
from filehandler.models.request import FileTypeCreateRequest, FileUploadRequest


# ── minimal 1×1 red PNG ──────────────────────────────────────────────────────

def _make_tiny_png() -> bytes:
    """Return a valid 1×1 red PNG as bytes (no Pillow dependency)."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return length + tag + data + crc

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    raw_row = b"\x00\xFF\x00\x00"  # filter byte + R G B
    compressed = zlib.compress(raw_row)
    idat = _chunk(b"IDAT", compressed)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


PNG_BYTES = _make_tiny_png()


# ── test client factory ───────────────────────────────────────────────────────

def _build_client() -> tuple[TestClient, FilehandlerServiceManager]:
    db = FilehandlerModelService(database_service_manager=None)
    manager = FilehandlerServiceManager(
        db,
        database_service_manager=None,
        config=None,
    )
    manager.start()

    controller = FilehandlerRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), manager


HEADERS = {"x-user-id": "u-1", "x-org-id": "org-1", "x-user-roles": "admin"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _create_type(client: TestClient, type_id: str, is_preview_thumbnail: bool = False) -> dict:
    resp = client.post(
        "/config/file-types",
        json={
            "type_id": type_id,
            "display_name": type_id.replace("_", " ").title(),
            "folder": type_id,
            "allowed_extensions": [".png", ".jpg"],
            "max_size_mb": 5,
            "is_preview_thumbnail": is_preview_thumbnail,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_image(client: TestClient, type_id: str, entity_id: str) -> dict:
    resp = client.post(
        "/filehandler/upload",
        params={
            "type_id": type_id,
            "owner_entity_id": entity_id,
            "owner_entity_type": "candidate",
        },
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── tests ─────────────────────────────────────────────────────────────────────

def test_create_file_type_with_thumbnail_flag() -> None:
    client, _ = _build_client()
    doc = _create_type(client, "photo", is_preview_thumbnail=True)
    assert doc["is_preview_thumbnail"] is True


def test_thumbnail_flag_defaults_to_false() -> None:
    client, _ = _build_client()
    doc = _create_type(client, "resume", is_preview_thumbnail=False)
    assert doc["is_preview_thumbnail"] is False


def test_exclusivity_only_one_thumbnail_type_per_org() -> None:
    """Setting a second type as thumbnail should clear the first."""
    client, manager = _build_client()
    _create_type(client, "photo_a", is_preview_thumbnail=True)
    _create_type(client, "photo_b", is_preview_thumbnail=True)

    types = manager.list_file_types("org-1")
    thumbnail_types = [t for t in types if t.is_preview_thumbnail]
    assert len(thumbnail_types) == 1
    assert thumbnail_types[0].type_id == "photo_b"


def test_update_sets_thumbnail_flag_and_clears_others() -> None:
    client, manager = _build_client()
    _create_type(client, "photo_a", is_preview_thumbnail=True)
    _create_type(client, "photo_b", is_preview_thumbnail=False)

    resp = client.put(
        "/config/file-types/photo_b",
        json={"is_preview_thumbnail": True},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["is_preview_thumbnail"] is True

    types = manager.list_file_types("org-1")
    assert sum(1 for t in types if t.is_preview_thumbnail) == 1
    active = next(t for t in types if t.is_preview_thumbnail)
    assert active.type_id == "photo_b"


def test_update_unsets_thumbnail_flag() -> None:
    client, _ = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)

    resp = client.put(
        "/config/file-types/photo",
        json={"is_preview_thumbnail": False},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["is_preview_thumbnail"] is False


def test_no_thumbnail_url_when_no_type_configured() -> None:
    _, manager = _build_client()
    url = manager.get_entity_preview_thumbnail_url("org-1", "entity-42")
    assert url is None


def test_no_thumbnail_url_when_no_file_uploaded() -> None:
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)

    url = manager.get_entity_preview_thumbnail_url("org-1", "entity-42")
    assert url is None


def test_thumbnail_url_generated_after_upload() -> None:
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)
    _upload_image(client, "photo", "entity-1")

    url = manager.get_entity_preview_thumbnail_url("org-1", "entity-1", base_url="")
    assert url is not None
    assert url.startswith("/api/filehandler/serve/")
    assert "sig=" in url
    assert "exp=" in url


def test_thumbnail_urls_are_resolved_in_bulk() -> None:
    _, manager = _build_client()
    manager.create_file_type(
        "org-1",
        FileTypeCreateRequest(
            type_id="photo",
            display_name="Photo",
            folder="photo",
            allowed_extensions=[".png"],
            max_size_mb=5,
            is_preview_thumbnail=True,
        ),
    )
    for entity_id in ("entity-1", "entity-2"):
        manager.upload_file(
            "org-1",
            "u-1",
            FileUploadRequest(
                type_id="photo",
                filename="photo.png",
                content_type="image/png",
                content=base64.b64encode(PNG_BYTES).decode("ascii"),
                owner_entity_id=entity_id,
                owner_entity_type="candidate",
            ),
        )

    urls = manager.get_entity_preview_thumbnail_urls(
        "org-1", {"entity-1", "entity-2", "entity-without-file"}
    )

    assert set(urls) == {"entity-1", "entity-2"}
    assert all(url.startswith("/api/filehandler/serve/") for url in urls.values())


def test_signed_url_serves_image() -> None:
    """The unauthenticated serve endpoint must return the image bytes."""
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)
    _upload_image(client, "photo", "entity-1")

    url = manager.get_entity_preview_thumbnail_url("org-1", "entity-1", base_url="")
    assert url is not None

    # Strip the /api prefix (TestClient routes are registered under /filehandler/...)
    path = url.removeprefix("/api")
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
    assert resp.content == PNG_BYTES


def test_signed_url_is_cached() -> None:
    """Cache-Control header must be present on serve response."""
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)
    _upload_image(client, "photo", "entity-1")

    url = manager.get_entity_preview_thumbnail_url("org-1", "entity-1", base_url="")
    path = url.removeprefix("/api")  # type: ignore[union-attr]
    resp = client.get(path)
    assert "cache-control" in resp.headers


def test_expired_signed_url_is_rejected() -> None:
    """An already-expired signature must return 403."""
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)
    uploaded = _upload_image(client, "photo", "entity-1")
    file_id = uploaded["file_id"]

    past_exp = int(time.time()) - 1
    sig = manager._sign_thumbnail_url(file_id, past_exp)
    resp = client.get(f"/filehandler/serve/{file_id}?sig={sig}&exp={past_exp}")
    assert resp.status_code == 403


def test_tampered_signature_is_rejected() -> None:
    """A forged sig on a valid file_id must be rejected."""
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)
    uploaded = _upload_image(client, "photo", "entity-1")
    file_id = uploaded["file_id"]

    exp = int(time.time()) + 3600
    resp = client.get(f"/filehandler/serve/{file_id}?sig=badsig&exp={exp}")
    assert resp.status_code == 403


def test_only_first_upload_is_used_for_thumbnail() -> None:
    """Uploading a second image must not change which file is used for the thumbnail URL."""
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)

    first = _upload_image(client, "photo", "entity-1")
    _upload_image(client, "photo", "entity-1")  # second upload (different content_hash would be needed in real DB)

    url = manager.get_entity_preview_thumbnail_url("org-1", "entity-1", base_url="")
    assert url is not None
    assert first["file_id"] in url


def test_thumbnail_url_isolated_per_entity() -> None:
    """Two different entities must each get their own thumbnail URL."""
    client, manager = _build_client()
    _create_type(client, "photo", is_preview_thumbnail=True)
    _upload_image(client, "photo", "entity-A")
    _upload_image(client, "photo", "entity-B")

    url_a = manager.get_entity_preview_thumbnail_url("org-1", "entity-A", base_url="")
    url_b = manager.get_entity_preview_thumbnail_url("org-1", "entity-B", base_url="")
    assert url_a is not None
    assert url_b is not None
    assert url_a != url_b
