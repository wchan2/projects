"""Plugin registry: strategies, filters and fetchers are plain functions registered by name.

Add a new one anywhere (e.g. a module listed under `plugins:` in config.yaml) with
`@register("strategy", "my_name")`; no core code needs editing.
"""

from collections.abc import Callable

_REGISTRY: dict[str, dict[str, Callable]] = {}


def register(kind: str, name: str | None = None):
    def deco(fn: Callable) -> Callable:
        _REGISTRY.setdefault(kind, {})[name or fn.__name__] = fn
        return fn

    return deco


def get(kind: str, name: str) -> Callable:
    try:
        return _REGISTRY[kind][name]
    except KeyError:
        raise KeyError(f"unknown {kind} '{name}'. Available: {available(kind)}") from None


def available(kind: str) -> list[str]:
    return sorted(_REGISTRY.get(kind, {}))
