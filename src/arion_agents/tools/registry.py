from __future__ import annotations

from typing import Any, Dict, Optional, Type

from .base import BaseTool, ToolConfig, ToolRunInput, ToolRunOutput


class EchoTool(BaseTool):
    """A built-in tool that echoes inputs. provider_type: 'builtin:echo'"""

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        return ToolRunOutput(ok=True, result={
            "echo": payload.params,
            "system": payload.system,
            "metadata": payload.metadata,
        })


PROVIDERS: Dict[str, Type[BaseTool]] = {
    "builtin:echo": EchoTool,
}


def instantiate_tool(cfg: ToolConfig, secret_value: Optional[str]) -> BaseTool:
    cls = PROVIDERS.get(cfg.provider_type)
    if not cls:
        raise ValueError(f"No provider for type '{cfg.provider_type}'")
    return cls(cfg, secret_value)

