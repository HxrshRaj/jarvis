"""Typed tool registry. The task engine, not the LLM, decides whether a tool may run."""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session


class ToolError(Exception):
    """Deterministic failure (bad input, denied path...). Never retried."""


class TransientToolError(ToolError):
    """Failure that may succeed on retry (bounded by ToolSpec.max_retries)."""


@dataclass
class ToolContext:
    user_id: str
    workspace: Path
    cancel: threading.Event
    db: Callable[[], Session]
    max_file_bytes: int = 256 * 1024
    max_output_chars: int = 20_000
    command_timeout: int = 60


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], dict[str, Any]]
    permissions: list[str] = field(default_factory=list)
    risk: str = "low"  # low | medium | high
    timeout: float = 30.0
    max_retries: int = 0
    # Per-call approval rule. Anything above "low" risk always needs approval.
    needs_approval: Callable[[BaseModel], bool] | None = None
    # Static policy check run at plan time (raises ToolError). Rejects plans before anything is queued.
    precheck: Callable[[BaseModel], None] | None = None
    available: bool = True
    audit: bool = True

    def approval_required(self, args: BaseModel) -> bool:
        if self.risk != "low":
            return True
        return bool(self.needs_approval and self.needs_approval(args))

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "permissions": self.permissions,
            "risk": self.risk,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "requires_approval": self.risk != "low",
            "available": self.available,
            "audited": self.audit,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        from app.tools.builtin import register_builtin

        _registry = ToolRegistry()
        register_builtin(_registry)
    return _registry
