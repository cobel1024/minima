from typing import Type

from apps.assistant.plugin.base import BasePlugin


class PluginRegistry:
    _plugins: dict[str, Type[BasePlugin]] = {}
    _loaded = False

    @classmethod
    def register(cls, kind: str):
        def decorator(plugin_class: Type[BasePlugin]):
            cls._plugins[kind] = plugin_class
            return plugin_class

        return decorator

    @classmethod
    def get(cls, kind: str) -> Type[BasePlugin]:
        if not cls._loaded:
            cls._load_plugins()
            cls._loaded = True

        plugin_class = cls._plugins.get(kind)
        if not plugin_class:
            raise ValueError(f"Plugin not found for kind: {kind}")
        return plugin_class

    @classmethod
    def _load_plugins(cls):
        from apps.assistant.plugin import assistant, curator  # noqa
