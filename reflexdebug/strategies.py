"""Ablation arms for the experiment. Each takes a task and returns a StrategyResult.

one_shot         the model writes code once, no execution feedback
traceback_loop   classic self-debugging: a few plain assert tests, feed back the raw traceback, full rewrite
rich_feedback    property-based spec + crash-frame locals + falsifying examples, still full rewrites, no tools
reflexdebug      full system: rich spec + ReAct debugger tools + patching + loop guard + Reflexion trials + memory
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import prompts
from .agent import ReflexDebugAgent
from .config import Settings
from .events import EventSink, null_sink
from .llm import BudgetExceeded
from .memory import ReflexionMemory
from .sandbox import Sandbox
from .spec import SpecSynthesizer, extract_code
from .tools import format_run

STRATEGIES = ["one_shot", "traceback_loop", "rich_feedback", "reflexdebug"]
STRATEGY_LABELS = {
    "one_shot": "One-shot",
    "traceback_loop": "Traceback loop",
    "rich_feedback": "Rich feedback",
    "reflexdebug": "ReflexDebug (full)",
}


@dataclass
class StrategyResult:
    strategy: str
    code: str
    self_verified: bool
    self_pass_rate: float
    iterations: int
    usage: dict
    wall_time: float
    spec_tests: int = 0
    extra: dict = field(default_factory=dict)
    error: str | None = None


def _coder(llm, task: str, tests: str | None) -> str:
    user = f"TASK:\n{task}\n"
    if tests:
        user += f"\nTESTS YOUR CODE MUST PASS:\n```python\n{tests}```\n"
    user += "\nWrite solution.py now."
    reply = llm.chat([{"role": "system", "content": prompts.CODER_SYSTEM}, {"role": "user", "content": user}])
    return extract_code(reply.content)


def run_one_shot(llm, task: str, settings: Settings, **_) -> StrategyResult:
    start = time.time()
    llm.reset_usage(settings.max_llm_calls)
    code = _coder(llm, task, None)
    return StrategyResult("one_shot", code, False, 0.0, 0, llm.usage.as_dict(), round(time.time() - start, 2))


def _feedback_loop(name: str, llm, task: str, settings: Settings, rich: bool, max_iters: int = 10) -> StrategyResult:
    start = time.time()
    llm.reset_usage(settings.max_llm_calls)
    sandbox = Sandbox(settings)
    code, tests, iterations, error = "", "", 0, None
    best = ("", -1.0, False)
    try:
        spec = SpecSynthesizer(llm, sandbox, simple=not rich).synthesize(task)
        tests = spec.tests
        code = _coder(llm, task, tests)
        for iterations in range(0, max_iters + 1):
            result = sandbox.run_tests(code, tests)
            score = result.pass_rate + (1.0 if result.all_passed else 0.0)
            if score > best[1]:
                best = (code, score, result.all_passed)
            if result.all_passed or iterations == max_iters:
                break
            reply = llm.chat([
                {"role": "system", "content": prompts.FIX_SYSTEM},
                {"role": "user", "content": prompts.FIX_USER.format(
                    task=task, code=code, feedback=format_run(result, rich=rich))},
            ])
            code = extract_code(reply.content)
    except BudgetExceeded as exc:
        error = str(exc)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    final_code, score, ok = best if best[1] >= 0 else (code, 0.0, False)
    rate = min(score, 1.0) if not ok else 1.0
    return StrategyResult(name, final_code, ok, rate, iterations, llm.usage.as_dict(),
                          round(time.time() - start, 2), spec_tests=len(tests.split("def test_")) - 1, error=error)


def run_traceback_loop(llm, task: str, settings: Settings, **_) -> StrategyResult:
    return _feedback_loop("traceback_loop", llm, task, settings, rich=False)


def run_rich_feedback(llm, task: str, settings: Settings, **_) -> StrategyResult:
    return _feedback_loop("rich_feedback", llm, task, settings, rich=True)


def run_reflexdebug(llm, task: str, settings: Settings, memory: ReflexionMemory | None = None,
                    sink: EventSink = null_sink, **_) -> StrategyResult:
    agent = ReflexDebugAgent(llm, settings, memory=memory, sink=sink)
    res = agent.solve(task)
    return StrategyResult(
        "reflexdebug", res.code, res.solved, res.pass_rate, res.steps, res.usage, res.wall_time,
        spec_tests=len(res.spec.test_names) if res.spec else 0,
        extra={"trials": res.trials, "disputes": res.disputes, "loop_guard_triggers": res.loop_guard_triggers,
               "tool_counts": res.tool_counts, "reflections": res.reflections, "lessons_used": res.lessons_used,
               "lesson_learned": res.lesson_learned, "events": res.events,
               "vacuous_tests": res.spec.vacuous if res.spec else [],
               "spec_review": res.spec.review if res.spec else [], "spec_triage": res.spec.triage if res.spec else []},
        error=res.error,
    )


RUNNERS = {
    "one_shot": run_one_shot,
    "traceback_loop": run_traceback_loop,
    "rich_feedback": run_rich_feedback,
    "reflexdebug": run_reflexdebug,
}
