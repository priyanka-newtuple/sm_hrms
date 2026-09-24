"""OpenAI Agents SDK model adapter for Amazon Bedrock Converse."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from agents import ModelSettings
from agents.handoffs import Handoff
from agents.items import TResponseInputItem
from agents.models.chatcmpl_converter import Converter
from agents.models.interface import Model, ModelResponse, ModelTracing
from agents.tool import Tool
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseStreamEvent,
)

from exceptions import ServiceError


class BedrockConverseModel(Model):
    """Translate Agents SDK model calls to Amazon Bedrock Converse."""

    def __init__(self, *, model: str, client: Any) -> None:
        self.model = model.removeprefix("bedrock/")
        self.client = client
        self.captured_llm_requests: list[dict[str, Any]] = []
        self.resolved_provider = "bedrock"
        self.runtime_kwargs: dict[str, Any] = {}

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Any | None,
        handoffs: list[Handoff[Any, Any]],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any | None,
    ) -> ModelResponse:
        _ = tracing, previous_response_id, conversation_id
        if prompt is not None:
            raise ServiceError("Bedrock Converse does not support Agents SDK prompt references")
        if output_schema is not None:
            raise ServiceError(
                "Structured agent output is not yet supported by the Bedrock Converse adapter"
            )

        request = self._build_request(
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            handoffs=handoffs,
        )
        self.captured_llm_requests.append(
            {
                "api": "bedrock.converse",
                "provider": self.resolved_provider,
                "body": self._json_safe(request),
            }
        )
        response = await asyncio.to_thread(self.client.converse, **request)
        return self._to_model_response(response)

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Any | None,
        handoffs: list[Handoff[Any, Any]],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any | None,
    ) -> AsyncIterator[ResponseStreamEvent]:
        _ = (
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id,
            conversation_id,
            prompt,
        )
        if False:  # pragma: no cover - keeps this method an async generator
            yield Any  # type: ignore[misc]
        raise ServiceError("Streaming is not yet supported by the Bedrock Converse adapter")

    def _build_request(
        self,
        *,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        handoffs: list[Handoff[Any, Any]],
    ) -> dict[str, Any]:
        messages, system = self._convert_messages(input)
        if system_instructions:
            system.insert(0, {"text": system_instructions})

        request: dict[str, Any] = {
            "modelId": self.model,
            "messages": messages,
        }
        if system:
            request["system"] = system

        inference_config = self._inference_config(model_settings)
        if inference_config:
            request["inferenceConfig"] = inference_config

        tool_config = self._tool_config(model_settings, tools, handoffs)
        if tool_config:
            request["toolConfig"] = tool_config
        return request

    @classmethod
    def _convert_messages(
        cls, input: str | list[TResponseInputItem]
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        messages: list[dict[str, Any]] = []
        system: list[dict[str, str]] = []
        items: list[Any] = (
            [{"role": "user", "content": input}] if isinstance(input, str) else list(input)
        )
        assistant_content: list[dict[str, Any]] = []

        def flush_assistant() -> None:
            nonlocal assistant_content
            if assistant_content:
                cls._append_message(messages, "assistant", assistant_content)
                assistant_content = []

        for item in items:
            item_payload = (
                item.model_dump(mode="json", exclude_none=True)
                if hasattr(item, "model_dump")
                else item
            )
            message = Converter.maybe_easy_input_message(
                item_payload
            ) or Converter.maybe_input_message(
                item_payload
            )
            if message:
                role = str(message.get("role") or "user")
                content = message.get("content")
                if role in {"system", "developer"}:
                    flush_assistant()
                    text = cls._content_text(content)
                    if text:
                        system.append({"text": text})
                    continue
                if role == "assistant":
                    assistant_content.extend(cls._content_blocks(content))
                    continue
                flush_assistant()
                blocks = cls._content_blocks(content)
                if blocks:
                    cls._append_message(messages, "user", blocks)
                continue

            if response_message := Converter.maybe_response_output_message(item_payload):
                for content_item in response_message.get("content", []):
                    if content_item.get("type") == "output_text":
                        assistant_content.append({"text": str(content_item.get("text") or "")})
                    elif content_item.get("type") == "refusal":
                        assistant_content.append(
                            {"text": str(content_item.get("refusal") or "")}
                        )
                continue

            if function_call := Converter.maybe_function_tool_call(item_payload):
                assistant_content.append(
                    {
                        "toolUse": {
                            "toolUseId": str(function_call.get("call_id") or uuid4()),
                            "name": str(function_call.get("name") or ""),
                            "input": cls._json_object(function_call.get("arguments")),
                        }
                    }
                )
                continue

            if function_output := Converter.maybe_function_tool_call_output(item_payload):
                flush_assistant()
                cls._append_message(
                    messages,
                    "user",
                    [
                        {
                            "toolResult": {
                                "toolUseId": str(function_output.get("call_id") or ""),
                                "content": cls._tool_result_content(
                                    function_output.get("output")
                                ),
                            }
                        }
                    ],
                )
                continue

            if reasoning := Converter.maybe_reasoning_message(item_payload):
                signatures = str(reasoning.get("encrypted_content") or "").split("\n")
                for content_item in reasoning.get("content", []) or []:
                    if content_item.get("type") != "reasoning_text":
                        continue
                    reasoning_text: dict[str, str] = {
                        "text": str(content_item.get("text") or "")
                    }
                    if signatures and signatures[0]:
                        reasoning_text["signature"] = signatures.pop(0)
                    assistant_content.append(
                        {"reasoningContent": {"reasoningText": reasoning_text}}
                    )
                continue

            chat_messages = Converter.items_to_messages(
                [item_payload], preserve_thinking_blocks=True
            )
            for chat_message in chat_messages:
                role = str(chat_message.get("role") or "user")
                if role in {"system", "developer"}:
                    text = cls._content_text(chat_message.get("content"))
                    if text:
                        system.append({"text": text})
                    continue
                if role == "tool":
                    flush_assistant()
                    cls._append_message(
                        messages,
                        "user",
                        [
                            {
                                "toolResult": {
                                    "toolUseId": str(
                                        chat_message.get("tool_call_id") or ""
                                    ),
                                    "content": cls._tool_result_content(
                                        chat_message.get("content")
                                    ),
                                }
                            }
                        ],
                    )
                    continue
                blocks = cls._content_blocks(chat_message.get("content"))
                if role == "assistant":
                    assistant_content.extend(blocks)
                else:
                    flush_assistant()
                    cls._append_message(messages, "user", blocks)

        flush_assistant()
        return messages, system

    @staticmethod
    def _append_message(
        messages: list[dict[str, Any]], role: str, content: list[dict[str, Any]]
    ) -> None:
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(content)
            return
        messages.append({"role": role, "content": content})

    @classmethod
    def _content_blocks(cls, content: Any) -> list[dict[str, Any]]:
        if content is None:
            return []
        if isinstance(content, str):
            return [{"text": content}] if content else []
        if not isinstance(content, list):
            return [{"text": str(content)}]

        blocks: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict):
                blocks.append({"text": str(part)})
                continue
            part_type = part.get("type")
            if part_type in {"text", "input_text", "output_text"}:
                blocks.append({"text": str(part.get("text") or "")})
            elif part_type == "thinking":
                reasoning_text: dict[str, str] = {
                    "text": str(part.get("thinking") or "")
                }
                if part.get("signature"):
                    reasoning_text["signature"] = str(part["signature"])
                blocks.append({"reasoningContent": {"reasoningText": reasoning_text}})
            elif part_type in {"image_url", "input_image"}:
                blocks.append(cls._image_block(part.get("image_url")))
            else:
                raise ServiceError(f"Unsupported Bedrock message content type: {part_type}")
        return blocks

    @staticmethod
    def _image_block(image_url: Any) -> dict[str, Any]:
        url = image_url.get("url") if isinstance(image_url, dict) else image_url
        if not isinstance(url, str) or not url.startswith("data:image/"):
            raise ServiceError("Bedrock image input requires a base64 data URL")
        header, encoded = url.split(",", 1)
        image_format = header.split("/", 1)[1].split(";", 1)[0].lower()
        if image_format == "jpg":
            image_format = "jpeg"
        if image_format not in {"png", "jpeg", "gif", "webp"}:
            raise ServiceError(f"Unsupported Bedrock image format: {image_format}")
        return {
            "image": {
                "format": image_format,
                "source": {"bytes": base64.b64decode(encoded)},
            }
        }

    @classmethod
    def _tool_result_content(cls, content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return [{"text": content}]
            return [{"json": parsed}] if isinstance(parsed, dict | list) else [{"text": content}]
        if isinstance(content, dict | list):
            return [{"json": content}]
        return [{"text": str(content or "")}]

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value or "{}")
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") in {"text", "input_text"}
            )
        return str(content or "")

    @staticmethod
    def _inference_config(model_settings: ModelSettings) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if model_settings.max_tokens is not None:
            config["maxTokens"] = model_settings.max_tokens
        if model_settings.temperature is not None:
            config["temperature"] = model_settings.temperature
        if model_settings.top_p is not None:
            config["topP"] = model_settings.top_p
        return config

    @staticmethod
    def _tool_config(
        model_settings: ModelSettings,
        tools: list[Tool],
        handoffs: list[Handoff[Any, Any]],
    ) -> dict[str, Any] | None:
        tool_choice = model_settings.tool_choice
        if tool_choice == "none":
            return None

        converted = [Converter.tool_to_openai(tool) for tool in tools]
        converted.extend(Converter.convert_handoff_tool(handoff) for handoff in handoffs)
        bedrock_tools = []
        for tool in converted:
            function = tool.get("function", {})
            bedrock_tools.append(
                {
                    "toolSpec": {
                        "name": function.get("name"),
                        "description": function.get("description") or "",
                        "inputSchema": {"json": function.get("parameters") or {}},
                    }
                }
            )
        if not bedrock_tools:
            return None

        config: dict[str, Any] = {"tools": bedrock_tools}
        if tool_choice == "required":
            config["toolChoice"] = {"any": {}}
        elif isinstance(tool_choice, str) and tool_choice not in {"auto", "none"}:
            config["toolChoice"] = {"tool": {"name": tool_choice}}
        else:
            config["toolChoice"] = {"auto": {}}
        return config

    @staticmethod
    def _to_model_response(response: dict[str, Any]) -> ModelResponse:
        output_items: list[Any] = []
        content = response.get("output", {}).get("message", {}).get("content", [])

        for block in content:
            if "text" in block:
                output_items.append(
                    ResponseOutputMessage(
                        id=f"message_{uuid4().hex}",
                        content=[
                            ResponseOutputText(
                                annotations=[],
                                text=str(block["text"]),
                                type="output_text",
                            )
                        ],
                        role="assistant",
                        status="completed",
                        type="message",
                    )
                )
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                output_items.append(
                    ResponseFunctionToolCall(
                        arguments=json.dumps(tool_use.get("input") or {}),
                        call_id=str(tool_use.get("toolUseId") or uuid4()),
                        name=str(tool_use.get("name") or ""),
                        type="function_call",
                        id=None,
                        status="completed",
                    )
                )
            elif "reasoningContent" in block:
                reasoning_text = block["reasoningContent"].get("reasoningText", {})
                reasoning_parts: list[Any] = []
                if reasoning_text.get("text"):
                    from openai.types.responses.response_reasoning_item import Content

                    reasoning_parts.append(
                        Content(text=str(reasoning_text["text"]), type="reasoning_text")
                    )
                output_items.append(
                    ResponseReasoningItem(
                        id=f"reasoning_{uuid4().hex}",
                        summary=[],
                        type="reasoning",
                        content=reasoning_parts or None,
                        encrypted_content=str(reasoning_text.get("signature") or "") or None,
                        status="completed",
                    )
                )

        usage_data = response.get("usage") or {}
        usage = Usage(
            requests=1,
            input_tokens=int(usage_data.get("inputTokens") or 0),
            output_tokens=int(usage_data.get("outputTokens") or 0),
            total_tokens=int(usage_data.get("totalTokens") or 0),
        )
        return ModelResponse(output=output_items, usage=usage, response_id=None)

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, bytes):
            return f"<bytes:{len(value)}>"
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [cls._json_safe(item) for item in value]
        return str(value)
