"""Offline tests for ReflexDebug (no network, no API key)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reflexdebug import ReflexDebugAgent, Settings  # noqa: E402
from reflexdebug.demo import DEMO_TASK, DEMO_TESTS, demo_llm  # noqa: E402
from reflexdebug.llm import ScriptedLLM  # noqa: E402
from reflexdebug.loopguard import LoopGuard, normalized_hash  # noqa: E402
from reflexdebug.memory import ReflexionMemory  # noqa: E402
from reflexdebug.safety import check_code  # noqa: E402
from reflexdebug.sandbox import Sandbox  # noqa: E402
from reflexdebug.spec import Spec, get_test_source, make_stub, replace_test  # noqa: E402
from reflexdebug.tools import Workspace  # noqa: E402

SB = Sandbox(Settings())


# safety gate

@pytest.mark.parametrize("src", [
    "import os",
    "import subprocess",
    "from socket import socket",
    "open('x', 'w')",
    "eval('1')",
    "().__class__.__bases__[0].__subclasses__()",
    "getattr(object, '__subclasses__')",
    "getattr(object, name)",
    "__builtins__['open']",
    "__import__('os')",
])
def test_safety_blocks_dangerous_code(src):
    assert not check_code(src).ok


def test_safety_allows_normal_code():
    src = "import math, itertools\nfrom collections import Counter\n\ndef f(x):\n    return math.sqrt(x)\n"
    assert check_code(src).ok


def test_safety_flags_syntax_error_separately():
    rep = check_code("def f(:\n  pass")
    assert not rep.ok and rep.syntax_error


# sandbox + harness

CODE = """
def mean(xs):
    total = 0
    for x in xs:
        total += x
    return total / len(xs)


def spin():
    n = 0
    while True:
        n += 1
"""

TESTS = """
import pytest
from hypothesis import given, strategies as st
from solution import mean, spin


def test_ok():
    assert mean([1, 2, 3]) == 2


@given(st.lists(st.integers(), max_size=5))
def test_property_float(xs):
    assert isinstance(mean(xs), float)


@pytest.mark.parametrize("xs, want", [([2, 4], 3), ([1], 1)])
def test_param(xs, want):
    assert mean(xs) == want


def test_hang():
    spin()
"""


def test_sandbox_captures_crash_frame_and_falsifying_example():
    r = SB.run_tests(CODE, TESTS)
    assert "test_ok" in r.passed
    assert "test_param[[2, 4]-3]" in r.passed and "test_param[[1]-1]" in r.passed
    prop = next(f for f in r.failed if f.test == "test_property_float")
    assert prop.error_type == "ZeroDivisionError"
    assert prop.crash_frame["locals"]["xs"] == "[]"
    assert any("xs=[]" in n for n in prop.notes)


def test_sandbox_per_test_timeout_localises_infinite_loop():
    r = SB.run_tests(CODE, TESTS)
    hang = next(f for f in r.failed if f.test == "test_hang")
    assert hang.error_type == "TestTimeout"
    assert hang.crash_frame["function"] == "spin"


def test_eval_at_crash_evaluates_in_failing_frame():
    res = SB.eval_at_crash(CODE, TESTS, "test_property_float", "(total, len(xs))")
    assert res.eval_result == "(0, 0)"


def test_eval_expression_goes_through_safety_gate():
    res = SB.eval_at_crash(CODE, TESTS, "test_property_float", "__import__('os')")
    assert isinstance(res, str) and "Blocked" in res


def test_blocked_solution_never_runs():
    r = SB.run_tests("import os\nos.remove('x')\n", TESTS)
    assert r.blocked and not r.all_passed


def test_syntax_error_is_reported_as_failure():
    r = SB.run_tests("def mean(:\n    pass\n", TESTS)
    assert r.import_error and r.import_error.error_type == "SyntaxError"


def test_snippet_probe():
    assert SB.run_snippet(CODE, "print(mean([2, 6]))") == "4.0"


# spec helpers

def test_stub_and_test_editing():
    stub = make_stub(["def f(x: int) -> int"])
    assert "raise NotImplementedError" in stub
    src = "def test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n"
    assert get_test_source(src, "test_b").startswith("def test_b")
    assert "test_a" not in replace_test(src, "test_a", None)


# loop guard

def test_loop_guard_detects_oscillation_ignoring_formatting():
    g = LoopGuard()
    assert g.check("x = 1\n", 1, ["t:E:1"]) is None
    assert g.check("x = 2\n", 2, ["t:E:1"]) is None
    assert normalized_hash("x=1") == normalized_hash("x = 1  # comment")
    warning = g.check("x=1", 3, ["t:E:1"])
    assert warning and "identical" in warning and "3 times" in warning


# memory

def test_memory_retrieval_prefers_related_lessons(tmp_path):
    mem = ReflexionMemory(tmp_path / "m.json", ScriptedLLM([]), min_score=0.0)
    mem.add_lesson("Use true division when averaging integers for a median.", ["division"], "median task", "solved")
    mem.add_lesson("Validate CSV quoting state machines on doubled quotes.", ["csv"], "csv parser", "solved")
    top = mem.retrieve("compute the median of integer windows", k=1)
    assert "median" in top[0].lesson
    assert ReflexionMemory(tmp_path / "m.json").lessons  # persisted


# tools

def test_apply_patch_requires_unique_match():
    spec = Spec(["def running_median(xs: list[int]) -> list[float]:"], DEMO_TESTS)
    ws = Workspace("t", spec, "a = 1\na = 1\n", SB, ScriptedLLM([]))
    assert "matches 2 places" in ws.dispatch("apply_patch", {"search": "a = 1", "replace": "a = 2"}).observation
    assert "not found" in ws.dispatch("apply_patch", {"search": "zzz", "replace": "y"}).observation


# full agent (scripted)

def test_scripted_agent_heals_across_two_trials(tmp_path):
    settings = Settings()
    settings.max_steps_per_trial = 3
    llm = demo_llm()
    agent = ReflexDebugAgent(llm, settings, memory=ReflexionMemory(tmp_path / "m.json", llm))
    result = agent.solve(DEMO_TASK)
    assert result.solved and result.trials == 2
    assert result.tool_counts == {"eval_at_crash": 1, "apply_patch": 1, "run_snippet": 1}
    assert result.reflections and "division" in result.reflections[0]
    assert result.lesson_learned
    kinds = [e["kind"] for e in result.events]
    for k in ("spec", "thought", "tool", "observation", "reflection", "lesson", "done"):
        assert k in kinds


def test_memory_watchdog_contains_memory_bomb():
    code = "def f():\n    x = []\n    while True:\n        x.append(' ' * 10**7)\n"
    r = SB.run_tests(code, "from solution import f\n\ndef test_x():\n    f()\n")
    fail = r.failed[0]
    assert fail.error_type == "MemoryLimitExceeded"
    assert fail.crash_frame["function"] == "f"


def test_openai_wrapper_parses_tool_calls_and_usage():
    from types import SimpleNamespace as NS

    from reflexdebug.llm import LLM

    fake_msg = NS(content="Thought: probe it.", tool_calls=[
        NS(id="call_1", function=NS(name="run_snippet", arguments='{"code": "print(1)"}'))])
    fake_resp = NS(choices=[NS(message=fake_msg, finish_reason="stop")], usage=NS(prompt_tokens=1000, completion_tokens=200))
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return fake_resp

    llm = LLM.__new__(LLM)
    llm.settings, llm.model, llm.max_calls = Settings(), "gpt-4o-mini", 5
    llm.client = NS(chat=NS(completions=NS(create=create)))
    from reflexdebug.llm import Usage

    llm.usage = Usage()
    res = llm.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert res.tool_calls[0].name == "run_snippet" and res.tool_calls[0].arguments == {"code": "print(1)"}
    assert res.message["tool_calls"][0]["id"] == "call_1"
    assert sent["parallel_tool_calls"] is False and sent["tool_choice"] == "auto"
    assert abs(llm.usage.cost_usd - (1000 * 0.15 + 200 * 0.60) / 1e6) < 1e-12


def test_fuzzy_patch_tolerates_indentation_and_continuations():
    from reflexdebug.tools import fuzzy_replace

    code = "def f(x):\n    if (x == 1 or \\\n            x == 2):\n        return 1\n    return 0\n"
    new = fuzzy_replace(code, "if (x == 1 or \\\n  x == 2):", "if x in (1, 2, 3):")
    assert isinstance(new, str) and "    if x in (1, 2, 3):\n        return 1" in new
    assert fuzzy_replace(code, "no such line", "y") == 0
    assert fuzzy_replace("a = 1\na = 1\n", "  a = 1", "a = 2") == 2


def test_loop_guard_flags_repeated_identical_action():
    g = LoopGuard()
    assert g.check_action("apply_patch", {"search": "x", "replace": "y", "thought": "a"}, 1, "Patch rejected") is None
    warning = g.check_action("apply_patch", {"search": "x", "replace": "y", "thought": "b"}, 2, "Patch rejected")
    assert warning and "step 1" in warning


def test_edit_that_breaks_syntax_is_rejected_and_code_kept():
    spec = Spec(["def running_median(xs: list[int]) -> list[float]:"], DEMO_TESTS)
    from reflexdebug.demo import BUGGY

    ws = Workspace("t", spec, BUGGY, SB, ScriptedLLM([]))
    out = ws.dispatch("apply_patch", {"search": "        n = len(s)", "replace": "        n = len(s"})
    assert "NOT changed" in out.observation and ws.code == BUGGY and not out.edited


def test_snippet_prints_trailing_expression_like_a_repl():
    assert SB.run_snippet(CODE, "x = [2, 6]\nmean(x)") == "4.0"


def test_spec_review_fixes_and_removes_bad_tests():
    from reflexdebug.spec import SpecSynthesizer

    tests = "from solution import f\n\n" + "".join(
        f"def test_example_{i}():\n    assert f({i}) == {i + 1}\n\n\n" for i in range(5)
    ) + "def test_property_bad():\n    assert f('x') == 0\n"
    spec_json = json.dumps({"functions": ["def f(x: int) -> int:"], "tests": tests})
    review = json.dumps({"reviews": [
        {"test": "test_property_bad", "verdict": "remove", "reason": "wrong argument type"},
        {"test": "test_example_0", "verdict": "fix", "reason": "clarity",
         "fixed_test": "def test_example_0():\n    got = f(0)\n    assert got == 1, got"},
        {"test": "test_missing", "verdict": "remove", "reason": "ignored"},
    ]})
    spec = SpecSynthesizer(ScriptedLLM([spec_json, review]), SB).synthesize("f adds one")
    assert "test_property_bad" not in spec.test_names and "got = f(0)" in spec.tests
    assert [r["test"] for r in spec.review] == ["test_property_bad", "test_example_0"]


def test_time_budget_reports_remaining_tests_instead_of_killing_the_run():
    s = Settings()
    s.wall_timeout_s, s.per_test_timeout_s = 9, 2
    tests = "from solution import spin\n\n" + "".join(f"def test_hang_{i}():\n    spin()\n\n\n" for i in range(6))
    r = Sandbox(s).run_tests(CODE, tests)
    kinds = [f.error_type for f in r.failed]
    assert not r.killed and len(kinds) == 6
    assert "TestTimeout" in kinds and "NotRun" in kinds


def test_spec_accepts_tests_as_list_and_retries_truncated_reply():
    from reflexdebug.llm import ChatResult
    from reflexdebug.spec import SpecSynthesizer

    body = [f"def test_example_{i}():\n    assert f({i}) == {i + 1}\n" for i in range(5)]
    good = json.dumps({"functions": "def f(x: int) -> int", "tests": ["from solution import f\n"] + body})

    class Truncating(ScriptedLLM):
        def chat(self, messages, **kw):
            res = super().chat(messages, **kw)
            if self._i == 1:
                return ChatResult('{"tests": "def test_' * 50, [], {"role": "assistant", "content": ""}, "length")
            return res

    llm = Truncating(["ignored", good, json.dumps({"reviews": []})])
    spec = SpecSynthesizer(llm, SB).synthesize("f adds one")
    assert spec.functions == ["def f(x: int) -> int:"] and len(spec.test_names) == 5 and spec.repairs == 1


WRONG = """
def _join(prefix, key):
    return prefix + str(key)


def flatten(obj, prefix=""):
    out = {}
    for key, value in obj.items():
        path = _join(prefix, key)
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out
"""
WRONG_TESTS = """
from solution import flatten


def test_nested():
    got = flatten({"a": {"b": 1}})
    assert got == {"a.b": 1}, f"got {got!r}"
"""


def test_trace_and_eval_work_for_wrong_value_failures():
    from reflexdebug.tools import format_trace

    res = SB.eval_at_crash(WRONG, WRONG_TESTS, "test_nested", "(prefix, out)")
    assert "flatten() at its return" in res.eval_frame and res.eval_result == "('', {'ab': 1})"
    traced = SB.trace_test(WRONG, WRONG_TESTS, "test_nested")
    text = format_trace(traced)
    assert "path='ab'" in text and "returned {'ab': 1}" in text


def test_snippet_can_call_private_helpers():
    assert SB.run_snippet(WRONG, "_join('a', 'b')") == "'ab'"


def test_evidence_based_triage_fixes_a_test_with_out_of_domain_inputs():
    from reflexdebug.spec import SpecSynthesizer
    from reflexdebug.tools import format_failure

    code = "def inc(x: int) -> int:\n    if x < 0:\n        raise ValueError(x)\n    return x + 1\n"
    tests = "import pytest\nfrom hypothesis import given, strategies as st\nfrom solution import inc\n\n" + "".join(
        f"def test_example_{i}():\n    assert inc({i}) == {i + 1}\n\n\n" for i in range(4)) + (
        "@given(st.integers(-5, 5))\ndef test_property_grows(x):\n    assert inc(x) > x\n")
    spec = Spec(["def inc(x: int) -> int:"], tests)
    failing = SB.run_tests(code, tests).failed
    assert [f.test for f in failing] == ["test_property_grows"] and "x=-1" in failing[0].notes[0]
    fixed = ("@given(st.integers(0, 5))\ndef test_property_grows(x):\n    assert inc(x) > x\n")
    verdict = json.dumps({"verdicts": [{"test": "test_property_grows", "verdict": "fix",
                                        "reason": "negative inputs must raise", "fixed_test": fixed}]})
    applied = SpecSynthesizer(ScriptedLLM([verdict]), SB).triage("inc(x) for x >= 0, negative raises", spec,
                                                                 failing, format_failure)
    assert applied and SB.run_tests(code, spec.tests).all_passed and spec.triage == applied


def test_invalid_spec_falls_back_to_unverified_draft(tmp_path):
    bad = json.dumps({"functions": ["def f(x: int) -> int:"], "tests": "def test_x(:\n    pass\n"})
    llm = ScriptedLLM([bad, bad, bad, "```python\ndef f(x):\n    return x + 1\n```"])
    res = ReflexDebugAgent(llm, Settings(), memory=ReflexionMemory(tmp_path / "m.json", llm)).solve("f adds one")
    assert not res.solved and "return x + 1" in res.code and res.usage["llm_calls"] == 4
