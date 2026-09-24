"""Provider-specific agent-model services."""

from common.data_model import LLMProvider
from llm.models.interface import AgentModelService
from llm.services.azure_foundry import AzureFoundryAgentModelService
from llm.services.azure_openai import AzureOpenAIAgentModelService
from llm.services.bedrock import BedrockAgentModelService
from llm.services.litellm import LiteLLMAgentModelService
from llm.services.openai import OpenAIAgentModelService


def default_agent_model_services() -> dict[LLMProvider, AgentModelService]:
    """Return the provider-to-service registry used by the LLM manager."""
    litellm_service = LiteLLMAgentModelService()
    return {
        LLMProvider.openai: OpenAIAgentModelService(),
        LLMProvider.azure_openai: AzureOpenAIAgentModelService(),
        LLMProvider.azure_foundry: AzureFoundryAgentModelService(),
        LLMProvider.bedrock: BedrockAgentModelService(),
        LLMProvider.anthropic_ai: litellm_service,
        LLMProvider.gemini_ai: litellm_service,
        LLMProvider.perplexity_ai: litellm_service,
        LLMProvider.lite_llm: litellm_service,
    }


__all__ = [
    "AzureFoundryAgentModelService",
    "AzureOpenAIAgentModelService",
    "BedrockAgentModelService",
    "LiteLLMAgentModelService",
    "OpenAIAgentModelService",
    "default_agent_model_services",
]
