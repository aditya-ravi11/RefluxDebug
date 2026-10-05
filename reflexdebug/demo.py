"""Offline scripted demo. It replays a realistic model trajectory so the whole pipeline (spec, sandbox,
debugger tools, loop, reflection, memory) can be shown without an API key. Every test run in the demo is real;
only the model replies are pre-recorded."""

from __future__ import annotations

import json

from .llm import ScriptedLLM

DEMO_TASK = (
    "Write running_median(xs: list[int]) -> list[float] that returns, for every prefix xs[:i+1], the median of that "
    "prefix. For an even-length prefix the median is the mean of the two middle values. An empty input returns []."
)

DEMO_TESTS = '''import statistics

import pytest
from hypothesis import given, strategies as st

from solution import running_median


def test_example_empty():
    got = running_median([])
    assert got == [], f"got {got!r}"


def test_example_odd_prefixes():
    got = running_median([5, 1, 3])
    assert got == [5, 3.0, 3], f"got {got!r}"


def test_example_even_length():
    got = running_median([1, 2])
    assert got == [1, 1.5], f"got {got!r}"


def test_example_negative_and_duplicates():
    got = running_median([-2, -2, 4, 4])
    assert got == [-2, -2, -2, 1.0], f"got {got!r}"


@given(st.lists(st.integers(-50, 50), max_size=12))
def test_property_matches_oracle(xs):
    got = running_median(xs)
    expected = [statistics.median(xs[: i + 1]) for i in range(len(xs))]
    assert got == expected, f"got {got!r}, expected {expected!r}"


@given(st.lists(st.integers(-50, 50), max_size=12))
def test_property_length(xs):
    got = running_median(xs)
    assert len(got) == len(xs), f"got {got!r}"
'''

BUGGY = '''def running_median(xs: list[int]) -> list[float]:
    result = []
    for i in range(len(xs)):
        s = sorted(xs[: i + 1])
        n = len(s)
        result.append(s[n // 2])
    return result
'''

FIXED = '''def running_median(xs: list[int]) -> list[float]:
    result = []
    for i in range(len(xs)):
        s = sorted(xs[: i + 1])
        n = len(s)
        mid = n // 2
        if n % 2:
            result.append(s[mid])
        else:
            result.append((s[mid - 1] + s[mid]) / 2)
    return result
'''


def demo_script() -> list:
    return [
        json.dumps({
            "functions": ["def running_median(xs: list[int]) -> list[float]:"],
            "summary": "Median of every prefix, averaging the two middle values for even lengths.",
            "tests": DEMO_TESTS,
        }),
        json.dumps({"reviews": []}),
        f"```python\n{BUGGY}```",
        json.dumps({"verdicts": [
            {"test": "test_example_even_length", "verdict": "keep",
             "reason": "The task defines the even-length median as the mean of the two middle values."},
            {"test": "test_property_matches_oracle", "verdict": "keep",
             "reason": "statistics.median implements exactly the median the task describes."},
        ]}),
        {"content": "Thought: Several tests fail on even-length prefixes and Hypothesis shrank the oracle failure to "
                    "xs=[0, 1]. I want to see the function's own state when it returned for that input.",
         "tool": ("eval_at_crash", {"test_name": "test_property_matches_oracle", "expression": "(s, n, result)"})},
        {"content": "Thought: At return s=[0, 1], n=2 and result=[0, 1], but the median of [0, 1] is 0.5. The code "
                    "always takes s[n // 2], the upper middle, so even lengths need the mean of the two middle values.",
         "tool": ("apply_patch", {"search": "        result.append(s[n // 2])",
                                  "replace": "        if n % 2:\n            result.append(s[n // 2])\n        else:\n"
                                             "            result.append((s[n // 2 - 1] + s[n // 2]) // 2)"})},
        {"content": "Thought: The duplicate test now passes but [1, 2] still fails. Let me probe the exact output for "
                    "that input to confirm what the averaging produces.",
         "tool": ("run_snippet", {"code": "print(running_median([1, 2]))\nprint(running_median([0, 1, 2, 3]))"})},
        "The root cause is in the averaging of the two middle values: floor division `//` truncates 1.5 to 1 and 0.5 "
        "to 0, so every even-length prefix with an odd sum is wrong. My patch fixed the index selection but kept "
        "integer arithmetic, and I spent the last step probing instead of fixing it. Next trial: compute the even "
        "case with true division `/ 2` and keep odd-length prefixes returning the middle element unchanged.",
        f"```python\n{FIXED}```",
        json.dumps({"lesson": "When a result is the average of two integers (median, midpoint, mean), use true "
                              "division `/`; floor division `//` silently truncates and only fails on odd sums.",
                    "tags": ["division", "median", "numeric"]}),
    ]


def demo_llm() -> ScriptedLLM:
    return ScriptedLLM(demo_script())
