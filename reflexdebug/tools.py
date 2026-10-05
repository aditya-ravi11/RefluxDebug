"""ReAct tools: the agent's debugger-like action space, and observation formatting."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from . import prompts
from .safety import check_code
from .sandbox import Failure, RunResult, Sandbox
from .spec import Spec, get_test_source, list_tests, parse_json, replace_test

MAX_OBS = 6000


def numbered(code: str) -> str:
    return "```\n" + "\n".join(f"{i:>3} | {line}" for i, line in enumerate(code.splitlines(), 1)) + "\n```"


def _fmt_locals(locals_: dict) -> str:
    if not locals_:
        return "(none)"
    return ", ".join(f"{k}={v}" for k, v in locals_.items())


def format_failure(f: Failure, rich: bool = True) -> str:
    out = [f"--- FAIL {f.test}: {f.error_type}: {f.message}"]
    if not rich:
        out.append(f.traceback)
        return "\n".join(out)
    for note in f.notes:
        out.append(f"Hypothesis {note.strip()}")
    if f.distinct_failures > 1:
        out.append(f"(Hypothesis found {f.distinct_failures} distinct failures; showing the first)")
    if f.crash_frame:
        c = f.crash_frame
        out.append(f"Crash frame: solution.py line {c['line']} in {c['function']}(): `{c['source']}`")
        out.append(f"  locals: {_fmt_locals(c['locals'])}")
    if f.test_frame:
        t = f.test_frame
        out.append(f"Test frame: spec_tests.py line {t['line']}: `{t['source']}`")
        out.append(f"  locals: {_fmt_locals(t['locals'])}")
    tb = f.traceback.splitlines()
    out.append("\n".join(tb[-12:]))
    return "\n".join(out)


def failure_briefs(result: RunResult | None, limit: int = 6) -> list[dict]:
    """Compact, structured view of failures for user interfaces (the model sees format_run instead)."""
    if result is None:
        return []
    if result.blocked:
        return [{"test": "safety gate", "error": "Blocked", "message": result.blocked[:300], "example": "", "where": ""}]
    out = []
    for f in result.all_failures()[:limit]:
        example = ""
        for note in f.notes:
            body = note.split("(", 1)[-1].rsplit(")", 1)[0] if "(" in note else note
            example = " ".join(body.split()).rstrip(",")
            break
        where = ""
        if f.crash_frame:
            where = f"solution.py line {f.crash_frame['line']}: {f.crash_frame['source']}"
        out.append({"test": f.test, "error": f.error_type, "message": f.message[:300], "example": example,
                    "where": where})
    return out


def format_run(result: RunResult, rich: bool = True, max_failures: int = 3) -> str:
    if result.blocked:
        return result.blocked
    if result.import_error:
        head = "RESULT: solution.py could not be loaded, so no test ran."
        if result.import_error.test == "<import spec_tests>":
            head = "RESULT: the test module could not be loaded."
        return head + "\n" + format_failure(result.import_error, rich)
    lines = [f"RESULT: {len(result.passed)}/{result.total} tests passed."]
    if result.all_passed:
        lines.append("All specification tests pass.")
        return "\n".join(lines)
    for f in result.failed[:max_failures]:
        lines.append(format_failure(f, rich))
    rest = result.failed[max_failures:]
    if rest:
        lines.append(f"... plus {len(rest)} more failing tests: {', '.join(f.test for f in rest)}")
    if result.passed:
        lines.append(f"Passing: {', '.join(result.passed)}")
    return "\n".join(lines)


THOUGHT_PROP = {
    "type": "string",
    "description": "Your reasoning for this step: interpret the last observation, state a concrete hypothesis about "
                   "the root cause and why this action tests or fixes it (2 to 4 sentences).",
}


def format_trace(f: Failure, max_changes: int = 6) -> str:
    t = f.trace or {}
    head = f"Trace of solution.py while running {f.test} (failed with {f.error_type}: {f.message[:200]})"
    for note in f.notes:
        head += f"\nHypothesis {note.strip()}"
    if not t or not t.get("steps"):
        return head + "\nNo line of solution.py executed during this test."

    def row(func, line, source, changed):
        items = list(changed.items())[:max_changes]
        delta = ", ".join(f"{k}={v}" for k, v in items) or "-"
        return f"  {func}():{line:<4} {source[:60]:<60} | {delta}"

    lines = [head, f"{t['steps']} line events. First steps:"]
    lines += [row(*r) for r in t["first"]]
    last = [r for r in t["last"] if r[0] > len(t["first"])]
    if last:
        skipped = last[0][0] - len(t["first"]) - 1
        if skipped > 0:
            lines.append(f"  ... {skipped} steps omitted ...")
        lines.append("Final steps (the execution that failed):")
        lines += [row(*r[1:]) for r in last]
    ret = t.get("entry_return")
    if ret:
        lines.append(f"Entry function {ret['function']}() returned {ret['returned']} at line {ret['line']}.")
        lines.append("  locals at return: " + (", ".join(f"{k}={v}" for k, v in ret["locals"].items()) or "-"))
    if f.test_frame:
        lines.append(f"Test assertion: `{f.test_frame['source']}` with {_fmt_locals(f.test_frame['locals'])}")
    return "\n".join(lines)


def _schema(name: str, description: str, props: dict, required: list[str]) -> dict:
    """Every tool takes a required 'thought' so the ReAct reasoning trace is never skipped."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {"thought": THOUGHT_PROP, **props},
                           "required": ["thought", *required], "additionalProperties": False},
        },
    }


TOOL_SCHEMAS = [
    _schema("run_tests", "Run the full specification test suite against the current solution.py.", {}, []),
    _schema(
        "inspect_failure",
        "Show complete debugger details (full traceback, all captured locals, falsifying example) for one failing test.",
        {"test_name": {"type": "string"}},
        ["test_name"],
    ),
    _schema(
        "eval_at_crash",
        "Re-run one failing test and evaluate a Python expression inside solution.py, like a post-mortem debugger: "
        "in the frame that raised the exception, or, for wrong-value failures, in the entry function's frame at the "
        "moment it returned (so its local variables are available).",
        {"test_name": {"type": "string"}, "expression": {"type": "string", "description": "e.g. 'parts' or 'len(stack)'"}},
        ["test_name", "expression"],
    ),
    _schema(
        "trace_test",
        "Re-run one failing test under a line tracer and show how solution.py executed: which lines ran, how local "
        "variables changed step by step, and what the entry function returned. Best tool for wrong-value "
        "(AssertionError) failures, where no exception points at the faulty line.",
        {"test_name": {"type": "string"}},
        ["test_name"],
    ),
    _schema(
        "run_snippet",
        "Execute a short Python snippet with every function of the current solution.py already imported. "
        "Use print() to see values. Good for probing behaviour on custom inputs.",
        {"code": {"type": "string"}},
        ["code"],
    ),
    _schema(
        "apply_patch",
        "Edit solution.py by replacing a snippet. 'search' should be copied from the current code and must identify "
        "one place (a few complete lines work best; indentation differences are tolerated). Tests re-run "
        "automatically after the edit.",
        {"search": {"type": "string"}, "replace": {"type": "string"}},
        ["search", "replace"],
    ),
    _schema(
        "rewrite_code",
        "Replace the whole solution.py with new source. Use only when the overall approach is wrong. Tests re-run automatically.",
        {"code": {"type": "string"}},
        ["code"],
    ),
    _schema(
        "dispute_test",
        "Claim that a specification test contradicts the task statement. An independent arbiter (who cannot see "
        "your code) will keep, fix or remove it. Use sparingly and only with a strong argument citing the task text.",
        {"test_name": {"type": "string"}, "argument": {"type": "string"}},
        ["test_name", "argument"],
    ),
    _schema(
        "finish",
        "Stop working on this trial. Call when all tests pass or when no further progress is possible.",
        {"summary": {"type": "string"}},
        ["summary"],
    ),
]


def _norm(line: str) -> str:
    return " ".join(line.replace("\\", " ").split())


def fuzzy_replace(code: str, search: str, replace: str) -> str | int:
    """Line-level match that ignores indentation and inner whitespace (model edits often get these wrong).

    Returns the new code, or 0 when there is no match and 2 when the match is ambiguous. The replacement is
    re-indented so its first line lines up with the first matched line.
    """
    s_lines = [l for l in search.splitlines() if l.strip()]
    if not s_lines:
        return 0
    c_lines = code.splitlines()
    target = [_norm(l) for l in s_lines]
    hits = []
    for i in range(len(c_lines)):
        j, k = i, 0
        while j < len(c_lines) and k < len(target):
            if not c_lines[j].strip():
                j += 1
                continue
            if _norm(c_lines[j]) != target[k]:
                break
            j, k = j + 1, k + 1
        if k == len(target):
            hits.append((i, j))
    if len(hits) != 1:
        return 0 if not hits else 2
    start, end = hits[0]
    have = len(c_lines[start]) - len(c_lines[start].lstrip())
    r_lines = replace.splitlines()
    first = next((l for l in r_lines if l.strip()), "")
    shift = have - (len(first) - len(first.lstrip()))
    fixed = []
    for l in r_lines:
        if not l.strip():
            fixed.append("")
        elif shift >= 0:
            fixed.append(" " * shift + l)
        else:
            cut = min(-shift, len(l) - len(l.lstrip()))
            fixed.append(l[cut:])
    new = c_lines[:start] + fixed + c_lines[end:]
    return "\n".join(new) + ("\n" if code.endswith("\n") else "")


@dataclass
class ToolOutcome:
    observation: str
    edited: bool = False
    finished: bool = False
    tests_changed: bool = False


@dataclass
class Workspace:
    task: str
    spec: Spec
    code: str
    sandbox: Sandbox
    llm: object
    last_result: RunResult | None = None
    disputes: list[dict] = field(default_factory=list)
    max_disputes: int = 2
    edits: int = 0
    tool_counts: dict = field(default_factory=dict)

    @property
    def tests(self) -> str:
        return self.spec.tests

    def run(self) -> RunResult:
        self.last_result = self.sandbox.run_tests(self.code, self.tests)
        return self.last_result

    # dispatcher
    def dispatch(self, name: str, args: dict) -> ToolOutcome:
        self.tool_counts[name] = self.tool_counts.get(name, 0) + 1
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return ToolOutcome(f"Unknown tool '{name}'. Available: {', '.join(s['function']['name'] for s in TOOL_SCHEMAS)}")
        try:
            outcome = handler(**{k: v for k, v in args.items() if not k.startswith("_") and k != "thought"})
        except TypeError as err:
            return ToolOutcome(f"Bad arguments for {name}: {err}")
        if len(outcome.observation) > MAX_OBS:
            outcome.observation = outcome.observation[:MAX_OBS] + "\n...[truncated]"
        return outcome

    def tool_run_tests(self) -> ToolOutcome:
        return ToolOutcome(format_run(self.run()))

    def tool_inspect_failure(self, test_name: str) -> ToolOutcome:
        result = self.last_result or self.run()
        for f in result.all_failures():
            if f.test == test_name:
                text = format_failure(f)
                text = text.replace("\n".join(f.traceback.splitlines()[-12:]), f.traceback)
                return ToolOutcome(text)
        names = [f.test for f in result.all_failures()]
        return ToolOutcome(f"No failing test named {test_name!r}. Currently failing: {names or 'none'}")

    def tool_eval_at_crash(self, test_name: str, expression: str) -> ToolOutcome:
        res = self.sandbox.eval_at_crash(self.code, self.tests, test_name, expression)
        if isinstance(res, str):
            return ToolOutcome(res)
        if res.eval_frame == "solution.py":
            where = res.crash_frame or {}
            place = f"solution.py line {where.get('line')} (`{where.get('source', '')}`)"
        elif res.eval_frame == "spec_tests.py":
            where = res.test_frame or {}
            place = f"spec_tests.py line {where.get('line')} (`{where.get('source', '')}`)"
        else:
            place = res.eval_frame or "unknown frame"
        return ToolOutcome(f"Evaluated in {place}; the test failed with {res.error_type}:\n  {expression} = "
                           f"{res.eval_result}")

    def tool_trace_test(self, test_name: str) -> ToolOutcome:
        res = self.sandbox.trace_test(self.code, self.tests, test_name)
        if isinstance(res, str):
            return ToolOutcome(res)
        return ToolOutcome(format_trace(res))

    def tool_run_snippet(self, code: str) -> ToolOutcome:
        return ToolOutcome("Snippet output:\n" + self.sandbox.run_snippet(self.code, code))

    def _set_code(self, new_code: str) -> ToolOutcome:
        report = check_code(new_code)
        if report.syntax_error and check_code(self.code).ok:
            head = report.violations[0].split()[1].rstrip(":") if report.violations else "0"
            lineno = int(head) if head.isdigit() else 0
            context = "\n".join(f"{i:>3} | {l}" for i, l in enumerate(new_code.splitlines(), 1)
                                if abs(i - lineno) <= 2)
            return ToolOutcome("Edit rejected: it would make solution.py invalid Python "
                               f"({report.violations[0]}). The code was NOT changed.\n"
                               f"The edited code around that line would have been:\n{context}\n"
                               "Replace whole statements (all lines of a multi-line condition), or use rewrite_code.")
        if not report.ok and not report.syntax_error:
            return ToolOutcome(f"Edit rejected. {report}")
        diff = "\n".join(
            difflib.unified_diff(self.code.splitlines(), new_code.splitlines(), "before", "after", lineterm="", n=1)
        )
        self.code = new_code
        self.edits += 1
        result = self.run()
        return ToolOutcome(f"Edit applied.\nDIFF:\n{diff or '(no change)'}\n\n{format_run(result)}", edited=True)

    def tool_apply_patch(self, search: str, replace: str) -> ToolOutcome:
        count = self.code.count(search) if search else 0
        if count == 1:
            return self._set_code(self.code.replace(search, replace, 1))
        if count > 1:
            return ToolOutcome(f"Patch rejected: 'search' matches {count} places. Include more surrounding lines.")
        fuzzy = fuzzy_replace(self.code, search, replace)
        if isinstance(fuzzy, str):
            outcome = self._set_code(fuzzy)
            outcome.observation = "(matched ignoring indentation and whitespace)\n" + outcome.observation
            return outcome
        if fuzzy == 2:
            return ToolOutcome("Patch rejected: 'search' matches several places (ignoring whitespace). "
                               "Include more surrounding lines.")
        first = (search.strip().splitlines() or [""])[0]
        close = difflib.get_close_matches(first, self.code.splitlines(), n=3, cutoff=0.5)
        hint = "\nClosest lines in the current code:\n" + "\n".join(f"  {c!r}" for c in close) if close else ""
        return ToolOutcome("Patch rejected: 'search' text not found verbatim in solution.py." + hint +
                           "\nCurrent code:\n" + numbered(self.code))

    def tool_rewrite_code(self, code: str) -> ToolOutcome:
        from .spec import extract_code

        return self._set_code(extract_code(code) if "```" in code else code)

    def tool_dispute_test(self, test_name: str, argument: str) -> ToolOutcome:
        if len(self.disputes) >= self.max_disputes:
            return ToolOutcome("Dispute rejected: the dispute limit for this task is reached. Fix the code instead.")
        source = get_test_source(self.tests, test_name)
        if source is None:
            return ToolOutcome(f"No test named {test_name!r}. Tests: {', '.join(self.spec.test_names)}")
        result = self.last_result or self.run()
        evidence = next((format_failure(f) for f in result.all_failures() if f.test == test_name), "test currently passes")
        reply = self.llm.chat(
            [
                {"role": "system", "content": prompts.ARBITER_SYSTEM},
                {"role": "user", "content": prompts.ARBITER_USER.format(
                    task=self.task, test_source=source, evidence=evidence, argument=argument)},
            ],
            json_mode=True,
            temperature=0.0,
        )
        try:
            verdict = parse_json(reply.content)
        except ValueError:
            verdict = {"verdict": "keep", "reason": "arbiter output unreadable"}
        decision = verdict.get("verdict", "keep")
        record = {"test": test_name, "argument": argument, "verdict": decision, "reason": verdict.get("reason", "")}
        changed = False
        if decision == "remove" and len(self.spec.test_names) > 1:
            self.spec.tests = replace_test(self.tests, test_name, None)
            changed = True
        elif decision == "fix" and verdict.get("fixed_test"):
            candidate = replace_test(self.tests, test_name, verdict["fixed_test"])
            if check_code(candidate).ok and test_name in list_tests(candidate):
                self.spec.tests = candidate
                record["fixed_test"] = verdict["fixed_test"]
                changed = True
            else:
                record["verdict"] = decision = "keep"
                record["reason"] += " (proposed fix was invalid, test kept)"
        elif decision not in {"keep", "fix", "remove"}:
            decision = record["verdict"] = "keep"
        self.disputes.append(record)
        text = f"Arbiter verdict: {decision.upper()}. {record['reason']}"
        if changed:
            text += "\n\n" + format_run(self.run())
        return ToolOutcome(text, tests_changed=changed)

    def tool_finish(self, summary: str = "") -> ToolOutcome:
        return ToolOutcome(f"Trial finished: {summary}", finished=True)
