"""Runtime configuration loaded from environment variables and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    temperature: float = 0.2

    # Agent budgets
    max_trials: int = field(default_factory=lambda: _int("RD_MAX_TRIALS", 3))
    max_steps_per_trial: int = field(default_factory=lambda: _int("RD_MAX_STEPS", 8))
    max_llm_calls: int = field(default_factory=lambda: _int("RD_MAX_LLM_CALLS", 30))

    # Sandbox limits
    wall_timeout_s: float = field(default_factory=lambda: float(os.getenv("RD_WALL_TIMEOUT", "30")))
    per_test_timeout_s: int = field(default_factory=lambda: _int("RD_TEST_TIMEOUT", 4))
    cpu_limit_s: int = field(default_factory=lambda: _int("RD_CPU_LIMIT", 20))
    memory_limit_mb: int = field(default_factory=lambda: _int("RD_MEMORY_MB", 512))
    hypothesis_examples: int = field(default_factory=lambda: _int("RD_HYPOTHESIS_EXAMPLES", 150))

    # Memory
    memory_path: Path = field(
        default_factory=lambda: Path(os.getenv("RD_MEMORY_PATH", PROJECT_ROOT / "results" / "memory.json"))
    )
    memory_top_k: int = 3

    def require_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and paste your key there."
            )
