from typing import Any, AsyncIterator

from apps.assistant.plugin.base import BasePlugin
from apps.assistant.plugin.registry import PluginRegistry


@PluginRegistry.register("curator")
class CuratorPlugin(BasePlugin):
    def execute_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[str]:
        raise NotImplementedError
