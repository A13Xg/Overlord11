from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolGatewayError(Exception):
    code: str
    message: str
    details: dict | None = None
    recoverable: bool = True
    retry_hint: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ParseError(ToolGatewayError):
    pass


class UnknownToolError(ToolGatewayError):
    pass


class ValidationError(ToolGatewayError):
    pass


class ExecutionError(ToolGatewayError):
    pass
