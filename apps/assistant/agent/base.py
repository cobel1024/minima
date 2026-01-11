from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseAgent(ABC):
    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    async def generate_stream(
        self,
        message: str,
        context: list[dict] | None = None,
        system_instruction: str | None = None,
        parts: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        yield ""
