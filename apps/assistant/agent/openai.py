from apps.assistant.agent.base import BaseAgent


class OpenAIAgent(BaseAgent):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        raise NotImplementedError("OpenAI agent is not implemented yet")
