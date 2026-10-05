"""Resource-limited subprocess sandbox.

Code is written to a fresh temporary directory and executed by ``harness.py`` in a separate
Python interpreter started in isolated mode (``-I``) with an empty environment, CPU / memory /
file-size / process limits (where the OS supports them) and a hard wall-clock timeout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .safety import check_code

HARNESS = Path(__file__).with_name("harness.py")
RESULT_MARKER = "__RD_RESULT__"


@dataclass
class Failure:
    test: str
    error_type: str
    message: str
    traceback: str
    notes: list[str] = field(default_factory=list)
    distinct_failures: int = 1
    crash_frame: dict | None = None
    test_frame: dict | None = None
    eval_result: str | None = None
    eval_frame: str | None = None
    trace: dict | None = None

    @property
    def signature(self) -> str:
        line = (self.crash_frame or self.test_frame or {}).get("line", "?")
        return f"{self.test}:{self.error_type}:{line}"

    @classmethod
    def from_dict(cls, data: dict) -> "Failure":
        known = {k: data.get(k) for k in cls.__dataclass_fields__ if k in data}
        known.setdefault("notes", [])
        return cls(**known)


@dataclass
class RunResult:
    passed: list[str] = field(default_factory=list)
    failed: list[Failure] = field(default_factory=list)
    import_error: Failure | None = None
    blocked: str | None = None
    stdout: str = ""
    wall_time: float = 0.0
    killed: bool = False

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed)

    @property
    def all_passed(self) -> bool:
        return (
            self.blocked is None
            and self.import_error is None
            and not self.killed
            and not self.failed
            and len(self.passed) > 0
        )

    @property
    def pass_rate(self) -> float:
        if self.blocked or self.import_error or self.killed or self.total == 0:
            return 0.0
        return len(self.passed) / self.total

    def all_failures(self) -> list[Failure]:
        return ([self.import_error] if self.import_error else []) + self.failed

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failed": [f.__dict__ for f in self.failed],
            "import_error": self.import_error.__dict__ if self.import_error else None,
            "blocked": self.blocked,
            "stdout": self.stdout,
            "wall_time": self.wall_time,
            "killed": self.killed,
        }


def _limit_resources(settings: Settings):
    def apply() -> None:
        try:
            import resource
        except ImportError:  # non-POSIX platform
            return
        mem = settings.memory_limit_mb * 1024 * 1024
        limits = [
            (getattr(resource, "RLIMIT_CPU", None), (settings.cpu_limit_s, settings.cpu_limit_s + 1)),
            (getattr(resource, "RLIMIT_AS", None), (mem, mem)),
            (getattr(resource, "RLIMIT_DATA", None), (mem, mem)),
            (getattr(resource, "RLIMIT_FSIZE", None), (5 * 1024 * 1024, 5 * 1024 * 1024)),
            (getattr(resource, "RLIMIT_CORE", None), (0, 0)),
        ]
        for which, value in limits:
            if which is None:
                continue
            try:
                resource.setrlimit(which, value)
            except (ValueError, OSError):
                pass  # some limits (e.g. RLIMIT_AS on macOS) are not enforceable; the wall timeout still applies
        os.setsid()

    return apply


class Sandbox:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def _execute(self, files: dict[str, str], config: dict) -> tuple[dict | None, str, float, bool]:
        with tempfile.TemporaryDirectory(prefix="reflexdebug_") as tmp:
            for name, content in files.items():
                Path(tmp, name).write_text(content, encoding="utf-8")
            env = {"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
            start = time.perf_counter()
            killed = False
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", str(HARNESS), tmp, json.dumps(config)],
                    cwd=tmp,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.settings.wall_timeout_s,
                    preexec_fn=_limit_resources(self.settings) if os.name == "posix" else None,
                )
                raw = proc.stdout
                stderr = proc.stderr
            except subprocess.TimeoutExpired as exc:
                killed = True
                raw = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = "sandbox wall-clock timeout"
            elapsed = time.perf_counter() - start
        if RESULT_MARKER in raw:
            payload = json.loads(raw.rsplit(RESULT_MARKER, 1)[1])
            return payload, stderr, elapsed, killed
        return None, (stderr or raw)[-2000:], elapsed, killed

    def run_tests(self, code: str, tests: str, only_test: str | None = None) -> RunResult:
        for label, src in (("solution", code), ("tests", tests)):
            report = check_code(src)
            if not report.ok and not report.syntax_error:
                return RunResult(blocked=f"[{label}] {report}")
        config = {
            "mode": "run",
            "only_test": only_test,
            "per_test_timeout": self.settings.per_test_timeout_s,
            "max_examples": self.settings.hypothesis_examples,
            "memory_mb": self.settings.memory_limit_mb,
            "time_budget": max(1.0, self.settings.wall_timeout_s - 5),
        }
        payload, stderr, elapsed, killed = self._execute(
            {"solution.py": code, "spec_tests.py": tests}, config
        )
        return self._to_result(payload, stderr, elapsed, killed)

    def eval_at_crash(self, code: str, tests: str, test_name: str, expr: str) -> Failure | str:
        report = check_code(expr, mode="eval")
        if not report.ok:
            return str(report)
        config = {
            "mode": "eval",
            "only_test": test_name,
            "expr": expr,
            "per_test_timeout": self.settings.per_test_timeout_s,
            "max_examples": self.settings.hypothesis_examples,
            "memory_mb": self.settings.memory_limit_mb,
            "time_budget": max(1.0, self.settings.wall_timeout_s - 5),
        }
        payload, stderr, _, killed = self._execute({"solution.py": code, "spec_tests.py": tests}, config)
        if payload is None:
            return f"sandbox error: {'killed by timeout' if killed else stderr}"
        if payload.get("import_error"):
            return f"cannot import: {payload['import_error']['message']}"
        if payload.get("failed"):
            return Failure.from_dict(payload["failed"][0])
        return f"test {test_name!r} passed on re-run, so there is no crash frame to inspect"

    def trace_test(self, code: str, tests: str, test_name: str) -> Failure | str:
        config = {
            "mode": "trace",
            "only_test": test_name,
            "per_test_timeout": self.settings.per_test_timeout_s,
            "max_examples": self.settings.hypothesis_examples,
            "memory_mb": self.settings.memory_limit_mb,
            "time_budget": max(1.0, self.settings.wall_timeout_s - 5),
        }
        payload, stderr, _, killed = self._execute({"solution.py": code, "spec_tests.py": tests}, config)
        if payload is None:
            return f"sandbox error: {'killed by timeout' if killed else stderr}"
        if payload.get("import_error"):
            return f"cannot import: {payload['import_error']['message']}"
        if payload.get("failed"):
            return Failure.from_dict(payload["failed"][0])
        return f"test {test_name!r} passed on re-run, so there is nothing to trace"

    def run_snippet(self, code: str, snippet: str) -> str:
        report = check_code(snippet)
        if not report.ok:
            return str(report)
        config = {"mode": "snippet", "code": snippet, "per_test_timeout": self.settings.per_test_timeout_s}
        payload, stderr, _, killed = self._execute({"solution.py": code, "spec_tests.py": ""}, config)
        if payload is None:
            return f"sandbox error: {'killed by timeout' if killed else stderr}"
        text = payload.get("stdout", "")
        if payload.get("error"):
            text += f"\n[error] {payload['error']}"
        return text.strip() or "(no output)"

    @staticmethod
    def _to_result(payload: dict | None, stderr: str, elapsed: float, killed: bool) -> RunResult:
        if payload is None:
            msg = "whole test run exceeded the wall-clock limit" if killed else f"harness crashed: {stderr}"
            fail = Failure(test="<sandbox>", error_type="SandboxKilled" if killed else "HarnessError",
                           message=msg, traceback=msg)
            return RunResult(import_error=fail, wall_time=elapsed, killed=killed)
        return RunResult(
            passed=payload["passed"],
            failed=[Failure.from_dict(f) for f in payload["failed"]],
            import_error=Failure.from_dict(payload["import_error"]) if payload.get("import_error") else None,
            stdout=payload.get("stdout", ""),
            wall_time=elapsed,
        )
