from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from apps.assistant.agent.factory import create_agent


class BasePlugin(ABC):
    def __init__(self):
        self.agent = create_agent()

    @abstractmethod
    def execute_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[str]:
        pass
