from apps.assistant.agent.base import BaseAgent


class ClaudeAgent(BaseAgent):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        raise NotImplementedError("Claude agent is not implemented yet")
