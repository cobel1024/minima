from django.conf import settings

from apps.assistant.agent.base import BaseAgent
from apps.assistant.agent.gemini import GeminiAgent


def create_agent() -> BaseAgent:
    agent_type = settings.ASSISTANT_AGENT.lower()
    api_key = settings.ASSISTANT_AGENT_API_KEY

    if agent_type == "gemini":
        return GeminiAgent(api_key)
    elif agent_type == "openai":
        raise NotImplementedError("OpenAI agent is not implemented yet")
    elif agent_type == "anthropic":
        raise NotImplementedError("Anthropic agent is not implemented yet")
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
