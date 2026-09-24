"""Unit tests for multimodal image input (STAT-254).

Covers the touch-points that don't need a live model/DB:
- SDK adapter builds a multimodal user message when images are present.
- Runtime prepares the stored image (read → check type/size/model → data URL +
  audit); it FAILS the run when the model can't accept the image (no OCR fallback).
- Trace/capture serializer redacts base64 image data URLs (no-persistence).
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from agent.models.interface import (
    AgentExecutionContext,
    AgentRuntimeSpec,
    AgentSessionContext,
    RequestContext,
    RuntimeBackendRunRequest,
    RuntimeContext,
)
from agent.services.runtime import AgentRuntimeService
from agent.services.sdk_adapter import AgentsSdkRuntimeAdapterBase
from exceptions import ValidationError
from llm.services.tracing import json_safe_payload

DATA_URL = "data:image/png;base64,AAAA"


def _backend_request(*, input_images=None, with_history=False) -> RuntimeBackendRunRequest:
    spec = AgentRuntimeSpec(
        definition_id="def-1",
        key="vision_helper",
        name="Vision Helper",
        instructions="You look at images.",
        model="gpt-4.1-mini",
    )
    session = None
    if with_history:
        session = AgentSessionContext(
            session_id="session-1",
            definition_id="def-1",
            recent_messages=[
                {
                    "message_id": "m1",
                    "role": "user",
                    "content": "First prompt",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )
    execution_context = AgentExecutionContext(
        request=RequestContext(organization_id="org-1", user_id="admin-user"),
        runtime=RuntimeContext(organization_id="org-1", user_id="admin-user"),
        session=session,
    )
    return RuntimeBackendRunRequest(
        run_id="run-1",
        runtime_spec=spec,
        input_text="Describe the image",
        execution_context=execution_context,
        input_images=list(input_images or []),
    )


# --- SDK adapter: _build_runner_input -------------------------------------


def test_build_runner_input_no_images_returns_plain_string() -> None:
    out = AgentsSdkRuntimeAdapterBase._build_runner_input(_backend_request())
    assert out == "Describe the image"


def test_build_runner_input_attaches_images_as_multimodal_blocks() -> None:
    out = AgentsSdkRuntimeAdapterBase._build_runner_input(
        _backend_request(input_images=[DATA_URL])
    )
    assert out == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe the image"},
                {"type": "input_image", "image_url": DATA_URL},
            ],
        }
    ]


def test_build_runner_input_multimodal_appended_after_history() -> None:
    out = AgentsSdkRuntimeAdapterBase._build_runner_input(
        _backend_request(input_images=[DATA_URL], with_history=True)
    )
    assert out[0] == {"role": "user", "content": "First prompt"}
    assert out[-1] == {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "Describe the image"},
            {"type": "input_image", "image_url": DATA_URL},
        ],
    }


# --- Runtime vision guard: _resolve_input_images --------------------------


class _VisionStub:
    def __init__(self, supported: bool) -> None:
        self._supported = supported
        self.seen: list[str] = []

    def supports_vision(self, model: str) -> bool:
        self.seen.append(model)
        return self._supported


def _runtime(*, supported: bool, source) -> AgentRuntimeService:
    return AgentRuntimeService(
        None,
        None,
        None,
        None,
        llm_service_manager=_VisionStub(supported),
        document_source_fn=source,
    )


def _image_source(content_type: str, data: bytes):
    """Mimic filehandler.read_document_source(org, document_id) -> dict."""

    def _src(_org, document_id=None):
        return {"content_type": content_type, "file_bytes": data}

    return _src


def test_resolve_images_builds_data_url_and_audit_when_vision_and_image() -> None:
    raw = b"\x89PNG\r\n\x1a\n fake png bytes"
    svc = _runtime(supported=True, source=_image_source("image/png", raw))
    data_urls, audit = svc._resolve_input_images(
        RequestContext(organization_id="org-1"), model="gpt-4.1-mini", document_id="doc-1"
    )
    assert data_urls == [f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"]
    # Audit records the image details (never the base64) for the run record.
    assert audit == [
        {
            "document_id": "doc-1",
            "content_type": "image/png",
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    ]


def test_resolve_images_fails_when_model_not_vision_and_carries_audit() -> None:
    # No OCR fallback exists anymore: an image on a non-vision model must fail the
    # run, not silently drop the image and continue with incomplete input. The
    # raised error carries the image audit so the FAILED run still records it.
    raw = b"some png bytes"
    svc = _runtime(supported=False, source=_image_source("image/png", raw))
    with pytest.raises(ValidationError, match="does not support image input") as exc_info:
        svc._resolve_input_images(
            RequestContext(organization_id="org-1"), model="text-only-model", document_id="doc-1"
        )
    audit = exc_info.value.backend_metadata["input_images"]
    assert audit[0]["document_id"] == "doc-1"
    assert audit[0]["content_type"] == "image/png"
    assert audit[0]["size_bytes"] == len(raw)
    assert audit[0]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_resolve_images_fails_when_oversized_and_carries_audit(monkeypatch) -> None:
    monkeypatch.setattr("agent.services.runtime._MAX_IMAGE_BYTES", 10)
    svc = _runtime(supported=True, source=_image_source("image/jpeg", b"x" * 100))
    with pytest.raises(ValidationError, match="exceeding|exceeds|limit") as exc_info:
        svc._resolve_input_images(
            RequestContext(organization_id="org-1"), model="gpt-4.1-mini", document_id="doc-1"
        )
    assert exc_info.value.backend_metadata["input_images"][0]["document_id"] == "doc-1"


def test_resolve_images_no_op_for_non_image_document() -> None:
    svc = _runtime(supported=True, source=_image_source("application/pdf", b"%PDF-1.4"))
    data_urls, audit = svc._resolve_input_images(
        RequestContext(organization_id="org-1"), model="gpt-4.1-mini", document_id="doc-1"
    )
    assert data_urls == [] and audit == []


def test_resolve_images_no_op_when_no_document_id() -> None:
    svc = _runtime(supported=True, source=_image_source("image/png", b"bytes"))
    data_urls, audit = svc._resolve_input_images(
        RequestContext(organization_id="org-1"), model="gpt-4.1-mini", document_id=None
    )
    assert data_urls == [] and audit == []


def test_resolve_images_no_op_when_source_missing() -> None:
    svc = _runtime(supported=True, source=lambda _org, document_id=None: None)
    data_urls, audit = svc._resolve_input_images(
        RequestContext(organization_id="org-1"), model="gpt-4.1-mini", document_id="doc-1"
    )
    assert data_urls == [] and audit == []


def test_resolve_images_graceful_when_source_raises() -> None:
    def _boom(_org, document_id=None):
        raise RuntimeError("storage down")

    svc = _runtime(supported=True, source=_boom)
    data_urls, audit = svc._resolve_input_images(
        RequestContext(organization_id="org-1"), model="gpt-4.1-mini", document_id="doc-1"
    )
    assert data_urls == [] and audit == []


# --- No-persistence: trace/capture serializer redacts base64 image data URLs ---


def test_json_safe_payload_redacts_base64_image_urls() -> None:
    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "what colour?"},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,AAAABBBBCCCCDDDD",
                    },
                ],
            }
        ],
    }
    dumped = json.dumps(json_safe_payload(payload))
    # the raw base64 body must never survive into the persistable trace payload
    assert "AAAABBBBCCCCDDDD" not in dumped
    # but the MIME header is kept (as a redacted marker) for debuggability
    assert "data:image/png;base64,<redacted>" in dumped


def test_json_safe_payload_redacts_chat_style_image_url_dict() -> None:
    payload = {"image_url": {"url": "data:image/jpeg;base64,SECRETBYTES", "detail": "auto"}}
    dumped = json.dumps(json_safe_payload(payload))
    assert "SECRETBYTES" not in dumped
    assert "data:image/jpeg;base64,<redacted>" in dumped
