"""Spec synthesis: turn a natural-language task into an executable specification before writing code.

The specification is a test module with example tests and Hypothesis property tests. It is validated
(safety gate, importability, collection) and self-repaired if broken. A vacuity check runs it against a
stub implementation: tests that pass against a stub cannot detect bugs and are reported.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field

from . import prompts
from .sandbox import Sandbox


class SpecError(RuntimeError):
    """No valid specification could be produced within the repair budget."""


@dataclass
class Spec:
    functions: list[str]
    tests: str
    summary: str = ""
    vacuous: list[str] = field(default_factory=list)
    repairs: int = 0
    review: list[dict] = field(default_factory=list)
    triage: list[dict] = field(default_factory=list)

    @property
    def test_names(self) -> list[str]:
        return list_tests(self.tests)

    def stub(self) -> str:
        return make_stub(self.functions)


def parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(text[start : end + 1])


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    return text.strip() + "\n"


def normalize_signature(sig: str) -> str:
    sig = sig.strip()
    if not sig.startswith("def "):
        sig = "def " + sig
    if not sig.endswith(":"):
        sig += ":"
    return sig


def make_stub(functions: list[str]) -> str:
    lines = ["from __future__ import annotations", ""]
    for sig in functions:
        lines += [normalize_signature(sig), "    raise NotImplementedError('stub')", ""]
    return "\n".join(lines)


def list_tests(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def _test_span(source: str, name: str) -> tuple[int, int] | None:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            return start, node.end_lineno or node.lineno
    return None


def get_test_source(source: str, name: str) -> str | None:
    span = _test_span(source, name)
    if not span:
        return None
    lines = source.splitlines()
    return "\n".join(lines[span[0] - 1 : span[1]])


def replace_test(source: str, name: str, new_source: str | None) -> str:
    """Replace test ``name`` with ``new_source`` (or delete it when new_source is None)."""
    span = _test_span(source, name)
    if not span:
        return source
    lines = source.splitlines()
    replacement = new_source.strip("\n").splitlines() if new_source else []
    return "\n".join(lines[: span[0] - 1] + replacement + lines[span[1] :]) + "\n"


class SpecSynthesizer:
    def __init__(self, llm, sandbox: Sandbox, max_repairs: int = 2, simple: bool = False) -> None:
        self.llm = llm
        self.sandbox = sandbox
        self.max_repairs = max_repairs
        self.simple = simple  # baseline mode: a few plain asserts, no property tests

    def synthesize(self, task: str) -> Spec:
        system = prompts.SIMPLE_TESTS_SYSTEM if self.simple else prompts.SPEC_SYSTEM
        messages = [{"role": "system", "content": system}, {"role": "user", "content": f"TASK:\n{task}"}]
        spec: Spec | None = None
        for attempt in range(self.max_repairs + 1):
            reply = self.llm.chat(messages, json_mode=True)
            if reply.finish_reason == "length":
                # Degenerate, over-long output: do not feed it back in full, just ask for a shorter module.
                messages.append({"role": "assistant", "content": reply.content[:1500] + "\n...[cut off]"})
                problem = ("Your reply was cut off at the token limit, so it is not valid JSON. Write a much shorter "
                           "module: at most 9 example tests and 4 property tests, no repeated or generated lists.")
                if attempt < self.max_repairs:
                    messages.append({"role": "user", "content": prompts.SPEC_REPAIR_USER.format(problem=problem)})
                continue
            messages.append(reply.message)
            try:
                data = parse_json(reply.content)
                functions = data.get("functions", [])
                functions = [functions] if isinstance(functions, str) else functions
                functions = [normalize_signature(s) for s in functions if isinstance(s, str) and s.strip()]
                tests = data.get("tests", "")
                if isinstance(tests, list):  # some replies give the module as a list of source chunks
                    tests = "\n\n".join(str(t) for t in tests)
                if not functions or not tests:
                    raise ValueError("JSON must contain non-empty 'functions' and 'tests'")
                spec = Spec(functions, tests.rstrip() + "\n", data.get("summary", ""), repairs=attempt)
                problem = self.validate(spec)
            except (ValueError, json.JSONDecodeError) as err:
                problem = f"Invalid response: {err}"
            if problem is None:
                if not self.simple:
                    self.review(task, spec)  # type: ignore[arg-type]
                return spec  # type: ignore[return-value]
            if attempt < self.max_repairs:
                messages.append({"role": "user", "content": prompts.SPEC_REPAIR_USER.format(problem=problem)})
        raise SpecError(f"could not synthesise a usable specification: {problem}")

    def review(self, task: str, spec: Spec) -> None:
        """Independent critic pass: fix or drop tests that contradict the task or can never pass (CodeT-style)."""
        try:
            reply = self.llm.chat([
                {"role": "system", "content": prompts.SPEC_REVIEW_SYSTEM},
                {"role": "user", "content": prompts.SPEC_REVIEW_USER.format(task=task, tests=spec.tests)},
            ], json_mode=True, temperature=0.0)
            reviews = parse_json(reply.content).get("reviews", [])
        except Exception:
            return
        applied = self.apply_verdicts(spec, reviews)
        spec.review = applied

    def apply_verdicts(self, spec: Spec, verdicts: list, min_tests: int = 3) -> list[dict]:
        """Apply keep / fix / remove verdicts safely; revert everything if the result is no longer a valid spec."""
        from .safety import check_code

        original, applied = spec.tests, []
        for item in verdicts if isinstance(verdicts, list) else []:
            if not isinstance(item, dict):
                continue
            name, verdict = item.get("test", ""), item.get("verdict", "")
            if name not in list_tests(spec.tests):
                continue
            if verdict == "remove" and len(list_tests(spec.tests)) > min_tests:
                spec.tests = replace_test(spec.tests, name, None)
            elif verdict == "fix" and item.get("fixed_test"):
                candidate = replace_test(spec.tests, name, item["fixed_test"])
                if not check_code(candidate).ok or name not in list_tests(candidate):
                    continue
                spec.tests = candidate
            else:
                continue
            applied.append({"test": name, "verdict": verdict, "reason": item.get("reason", "")})
        if applied and self.validate(spec) is not None:
            spec.tests, applied = original, []
            self.validate(spec)
        return applied

    def triage(self, task: str, spec: Spec, failures: list, formatter) -> list[dict]:
        """Evidence-based review: failing tests plus their concrete counterexamples go to an independent judge."""
        items = []
        for f in failures[:8]:
            source = get_test_source(spec.tests, f.test.split("[", 1)[0])
            if source:
                items.append(f"### {f.test}\n```python\n{source}\n```\nEVIDENCE:\n{formatter(f)}")
        if not items:
            return []
        try:
            reply = self.llm.chat([
                {"role": "system", "content": prompts.SPEC_TRIAGE_SYSTEM},
                {"role": "user", "content": prompts.SPEC_TRIAGE_USER.format(task=task, items="\n\n".join(items))},
            ], json_mode=True, temperature=0.0)
            verdicts = parse_json(reply.content).get("verdicts", [])
        except (ValueError, json.JSONDecodeError):
            return []
        applied = self.apply_verdicts(spec, verdicts)
        spec.triage.extend(applied)
        return applied

    def validate(self, spec: Spec) -> str | None:
        names = spec.test_names
        if not names:
            return "The test module defines no top-level functions named test_* (or has a syntax error)."
        if len(names) < 5 and not self.simple:
            return (f"Only {len(names)} test functions were written. Write at least 5 example tests (one behaviour "
                    "each, so one failure does not hide the others) plus 2 to 4 property tests.")
        try:
            ast.parse(spec.stub())
        except SyntaxError as err:
            return f"The 'functions' signatures are not valid Python: {err}"
        result = self.sandbox.run_tests(spec.stub(), spec.tests)
        if result.blocked:
            return result.blocked
        if result.import_error:
            err = result.import_error
            return f"Importing the test module failed with {err.error_type}: {err.message}\n{err.traceback}"
        broken = [f for f in result.failed if f.error_type in {"NameError", "ImportError", "SyntaxError", "TypeError", "AttributeError", "InvalidArgument"}
                  and not (f.crash_frame or {})]
        if broken:
            f = broken[0]
            return f"Test {f.test} is broken independently of the solution: {f.error_type}: {f.message}\n{f.traceback}"
        spec.vacuous = list(result.passed)
        return None
