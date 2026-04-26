"""Tool registry. Tools register themselves via the @tool decorator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Awaitable[Any]]
    dangerous: bool = False


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    input_schema: dict,
    *,
    dangerous: bool = False,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            fn=fn,
            dangerous=dangerous,
        )
        return fn

    return decorator


def get_tool(name: str) -> Optional[Tool]:
    return REGISTRY.get(name)


def all_tools() -> list[Tool]:
    return list(REGISTRY.values())


def claude_schemas() -> list[dict]:
    """Schemas in Anthropic Messages API format."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in REGISTRY.values()
    ]


# Registering tool modules. Each import triggers @tool decorators.
from . import apps  # noqa: E402, F401
from . import confirm  # noqa: E402, F401
from . import history  # noqa: E402, F401
from . import keyboard  # noqa: E402, F401
from . import screen  # noqa: E402, F401
from . import vision  # noqa: E402, F401
from . import voice  # noqa: E402, F401
from . import web  # noqa: E402, F401
