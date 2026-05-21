from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class BaseTool(ABC):
    name: str
    description: str
    risk_level: str = "low"
    destructive: bool = False
    supports_dry_run: bool = False
    timeout_behavior: str = "tool-defined"
    examples: list[dict[str, Any]] = []
    input_model: type[BaseModel]

    @abstractmethod
    def execute(self, args: BaseModel) -> dict[str, Any]:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level,
            "destructive": self.destructive,
            "supports_dry_run": self.supports_dry_run,
            "timeout_behavior": self.timeout_behavior,
            "examples": self.examples,
            "input_schema": self.input_model.model_json_schema(),
        }
