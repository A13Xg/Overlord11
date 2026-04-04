"""
Overlord11 Internal Execution Engine
=====================================
Provides a Python-native execution loop that replaces direct CLI dependency.
Maintains full compatibility with the existing CLI onboarding workflow.
"""

from engine.runner import EngineRunner
from engine.session_manager import SessionManager
from engine.event_stream import EventStream

__all__ = ["EngineRunner", "SessionManager", "EventStream"]
__version__ = "3.0.0"
