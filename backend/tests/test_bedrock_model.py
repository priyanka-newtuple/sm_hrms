from __future__ import annotations

import asyncio

from agents import ModelSettings, function_tool
from agents.models.interface import ModelTracing
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseReasoningItem,
)

from llm.services.bedrock_converse import BedrockConverseModel


class FakeBedrockClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def converse(self, **kwargs):
        self.requests.append(kwargs)
        return self.response


@function_tool
def lookup_candidate(candidate_id: str) -> str:
    """Look up a candidate by identifier."""
    return candidate_id


def test_bedrock_converse_translates_tools_reasoning_and_usage() -> None:
    client = FakeBedrockClient(
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "reasoningContent": {
                                "reasoningText": {
                                    "text": "I should look this up.",
                                    "signature": "signed-reasoning",
                                }
                            }
                        },
                        {"text": "Checking the candidate."},
                        {
                            "toolUse": {
                                "toolUseId": "tool-1",
                                "name": "lookup_candidate",
                                "input": {"candidate_id": "candidate-1"},
                            }
                        },
                    ]
                }
            },
            "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
        }
    )
    model = BedrockConverseModel(
        model="bedrock/us.anthropic.claude-sonnet-4-6",
        client=client,
    )

    response = asyncio.run(
        model.get_response(
            "You are a recruiting assistant.",
            "Find candidate-1",
            ModelSettings(tool_choice="required", max_tokens=200),
            [lookup_candidate],
            None,
            [],
            ModelTracing.DISABLED,
            previous_response_id=None,
            conversation_id=None,
            prompt=None,
        )
    )

    request = client.requests[0]
    assert request["modelId"] == "us.anthropic.claude-sonnet-4-6"
    assert request["system"] == [{"text": "You are a recruiting assistant."}]
    assert request["messages"] == [
        {"role": "user", "content": [{"text": "Find candidate-1"}]}
    ]
    assert request["toolConfig"]["toolChoice"] == {"any": {}}
    assert request["toolConfig"]["tools"][0]["toolSpec"]["name"] == (
        "lookup_candidate"
    )
    assert response.usage.total_tokens == 20
    assert isinstance(response.output[0], ResponseReasoningItem)
    assert isinstance(response.output[1], ResponseOutputMessage)
    assert isinstance(response.output[2], ResponseFunctionToolCall)
    assert model.captured_llm_requests[0]["api"] == "bedrock.converse"

    follow_up_input = [
        *response.output,
        {
            "type": "function_call_output",
            "call_id": "tool-1",
            "output": '{"name":"Dhiraj"}',
        },
    ]
    messages, _ = model._convert_messages(follow_up_input)
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"] == [
        {
            "reasoningContent": {
                "reasoningText": {
                    "text": "I should look this up.",
                    "signature": "signed-reasoning",
                }
            }
        },
        {"text": "Checking the candidate."},
        {
            "toolUse": {
                "toolUseId": "tool-1",
                "name": "lookup_candidate",
                "input": {"candidate_id": "candidate-1"},
            }
        },
    ]
    assert messages[1] == {
        "role": "user",
        "content": [
            {
                "toolResult": {
                    "toolUseId": "tool-1",
                    "content": [{"json": {"name": "Dhiraj"}}],
                }
            }
        ],
    }
