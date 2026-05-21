"""Overlord11 internal execution engine."""

__all__ = ["EngineRunner", "EventStream", "EventType"]


def __getattr__(name):
    if name == "EngineRunner":
        from .runner import EngineRunner

        return EngineRunner
    if name in {"EventStream", "EventType"}:
        from .event_stream import EventStream, EventType

        return {"EventStream": EventStream, "EventType": EventType}[name]
    raise AttributeError(name)
