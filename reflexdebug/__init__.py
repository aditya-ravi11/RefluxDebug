"""ReflexDebug: a debugger-grounded, spec-first, self-healing code agent (ReAct + Reflexion)."""

from .agent import AgentResult, ReflexDebugAgent
from .config import Settings

__all__ = ["AgentResult", "ReflexDebugAgent", "Settings"]
__version__ = "1.0.0"
