"""Detects unproductive repair loops: returning to an earlier code state or hitting the same error repeatedly."""

from __future__ import annotations

import ast
import hashlib
from collections import Counter


def normalized_hash(code: str) -> str:
    """Hash of the AST, so formatting and comment changes do not count as a new state."""
    try:
        canonical = ast.dump(ast.parse(code), annotate_fields=False, include_attributes=False)
    except SyntaxError:
        canonical = " ".join(code.split())
    return hashlib.sha1(canonical.encode()).hexdigest()[:12]


class LoopGuard:
    def __init__(self, repeat_limit: int = 3) -> None:
        self.repeat_limit = repeat_limit
        self.seen: dict[str, int] = {}
        self.signatures: Counter[str] = Counter()
        self.actions: dict[str, tuple[int, str]] = {}
        self.triggers = 0
        self.total_triggers = 0

    def check_action(self, name: str, args: dict, step: int, result_head: str) -> str | None:
        """Flag an action that is identical to an earlier one (same tool, same arguments)."""
        key = name + "|" + repr(sorted((k, str(v)) for k, v in args.items() if k != "thought"))
        if key in self.actions:
            first_step, first_result = self.actions[key]
            self.triggers += 1
            self.total_triggers += 1
            return (f"LOOP GUARD: this exact {name} call was already made at step {first_step} and produced: "
                    f"'{first_result}'. Repeating it will not help; change the action or the arguments.")
        self.actions[key] = (step, result_head[:160])
        return None

    def check(self, code: str, step: int, error_signatures: list[str]) -> str | None:
        """Register a new code state. Returns a warning text if the agent is looping, else None."""
        warnings = []
        digest = normalized_hash(code)
        if digest in self.seen and self.seen[digest] != step:
            warnings.append(
                f"This code is identical (ignoring formatting) to the version from step {self.seen[digest]}, "
                "which already failed. You are oscillating; try a genuinely different approach."
            )
        self.seen.setdefault(digest, step)
        for sig in set(error_signatures):
            self.signatures[sig] += 1
            if self.signatures[sig] == self.repeat_limit:
                warnings.append(
                    f"The same failure ({sig}) has now appeared {self.repeat_limit} times. "
                    "Your hypothesis about it is probably wrong; gather evidence with eval_at_crash or run_snippet. "
                    "If that test asserts something the task statement does not say, use dispute_test."
                )
        if warnings:
            self.triggers += 1
            self.total_triggers += 1
            return "LOOP GUARD: " + " ".join(warnings)
        return None

    def new_trial(self) -> None:
        """Code-state history is kept across trials, but the stuck counter starts again."""
        self.triggers = 0
        self.signatures.clear()
        self.actions.clear()

    @property
    def stuck(self) -> bool:
        return self.triggers >= 2
