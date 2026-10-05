"""Reflexion memory.

Short-term memory: the verbal self-reflections written after each failed trial of the current task.
Long-term memory: generalisable lessons distilled after every task, stored on disk with an embedding,
and retrieved by cosine similarity when a new task arrives.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .llm import hashed_embedding


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


@dataclass
class Lesson:
    id: str
    lesson: str
    tags: list[str]
    source_task: str
    outcome: str
    embedding: list[float]
    embed_model: str
    created: float = field(default_factory=time.time)
    score: float = 0.0

    def public(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "embedding"}


class ReflexionMemory:
    def __init__(self, path: Path, llm=None, min_score: float = 0.25) -> None:
        self.path = Path(path)
        self.llm = llm
        self.min_score = min_score
        self.lessons: list[Lesson] = []
        self.reflections: list[str] = []  # short-term, per task
        self._load()

    # persistence
    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                self.lessons = [Lesson(**{k: v for k, v in item.items() if k != "score"}) for item in raw]
            except (json.JSONDecodeError, TypeError):
                self.lessons = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [{k: v for k, v in l.__dict__.items() if k != "score"} for l in self.lessons]
        self.path.write_text(json.dumps(data, indent=1))

    def clear(self) -> None:
        self.lessons = []
        self.save()

    # embeddings
    def _embed(self, text: str) -> tuple[list[float], str]:
        if self.llm is not None and hasattr(self.llm, "embed") and getattr(self.llm, "model", "") != "scripted":
            try:
                return self.llm.embed([text])[0], "openai"
            except Exception:
                pass
        return hashed_embedding(text), "hashed"

    # short-term
    def start_task(self) -> None:
        self.reflections = []

    def add_reflection(self, text: str) -> None:
        self.reflections.append(text.strip())

    # long-term
    def retrieve(self, task: str, k: int = 3) -> list[Lesson]:
        if not self.lessons:
            return []
        query, model = self._embed(task)
        scored = []
        for lesson in self.lessons:
            if lesson.embed_model != model:
                lesson.embedding, lesson.embed_model = self._embed(lesson.lesson + " " + lesson.source_task)
            lesson.score = cosine(query, lesson.embedding)
            if lesson.score >= self.min_score:
                scored.append(lesson)
        scored.sort(key=lambda l: l.score, reverse=True)
        return scored[:k]

    def add_lesson(self, lesson: str, tags: list[str], task: str, outcome: str) -> Lesson | None:
        lesson = lesson.strip()
        if not lesson:
            return None
        vec, model = self._embed(lesson + " " + task)
        for existing in self.lessons:  # skip near duplicates
            if existing.embed_model == model and cosine(existing.embedding, vec) > 0.95:
                return None
        item = Lesson(uuid.uuid4().hex[:8], lesson, tags[:4], task[:300], outcome, vec, model)
        self.lessons.append(item)
        self.save()
        return item
