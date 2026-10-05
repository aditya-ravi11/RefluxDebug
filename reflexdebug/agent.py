"""ReflexDebug agent: spec-first, debugger-grounded ReAct repair inside Reflexion trials."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import prompts
from .config import Settings
from .events import Event, EventSink, null_sink
from .llm import BudgetExceeded
from .loopguard import LoopGuard, normalized_hash
from .memory import Lesson, ReflexionMemory
from .sandbox import RunResult, Sandbox
from .spec import Spec, SpecError, SpecSynthesizer, extract_code, parse_json
from .tools import TOOL_SCHEMAS, Workspace, failure_briefs, format_failure, format_run, numbered


@dataclass
class AgentResult:
    task: str
    code: str
    spec: Spec | None
    solved: bool
    pass_rate: float
    trials: int
    steps: int
    usage: dict
    wall_time: float
    disputes: list[dict] = field(default_factory=list)
    loop_guard_triggers: int = 0
    tool_counts: dict = field(default_factory=dict)
    reflections: list[str] = field(default_factory=list)
    lessons_used: list[str] = field(default_factory=list)
    lesson_learned: str | None = None
    events: list[dict] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["spec"] = (
            {"functions": self.spec.functions, "tests": self.spec.tests, "summary": self.spec.summary,
             "vacuous": self.spec.vacuous, "repairs": self.spec.repairs, "review": self.spec.review,
             "triage": self.spec.triage}
            if self.spec else None
        )
        return d


def build_coder_messages(task: str, spec: Spec, lessons: list[Lesson], reflections: list[str],
                         previous_code: str | None = None) -> list[dict]:
    spec_block = f"\nSPECIFICATION TESTS (your code must pass these):\n```python\n{spec.tests}```\n"
    lessons_block = ""
    if lessons:
        lessons_block = "\nLESSONS FROM PAST TASKS (long-term memory):\n" + "\n".join(f"- {l.lesson}" for l in lessons) + "\n"
    reflections_block = ""
    if reflections:
        reflections_block = "\nSELF-REFLECTIONS FROM YOUR EARLIER FAILED TRIALS ON THIS TASK:\n" + "\n".join(
            f"Trial {i}: {r}" for i, r in enumerate(reflections, 1)) + "\n"
        reflections_block += ("\nEarlier attempts failed. Write a fresh implementation that follows the reflections; "
                              "prefer a simpler, different design (for example validate by construction or compare "
                              "against a canonical form) over repeating the earlier structure.\n")
    return [
        {"role": "system", "content": prompts.CODER_SYSTEM},
        {"role": "user", "content": prompts.CODER_USER.format(
            task=task, functions="\n".join(spec.functions), spec_block=spec_block,
            lessons_block=lessons_block, reflections_block=reflections_block)},
    ]


class ReflexDebugAgent:
    def __init__(self, llm, settings: Settings | None = None, memory: ReflexionMemory | None = None,
                 sink: EventSink = null_sink, use_memory: bool = True) -> None:
        self.llm = llm
        self.settings = settings or Settings()
        self.sandbox = Sandbox(self.settings)
        self.memory = memory if memory is not None else ReflexionMemory(self.settings.memory_path, llm)
        self.use_memory = use_memory
        self.sink = sink
        self.events: list[Event] = []

    def emit(self, kind: str, title: str, **data) -> None:
        event = Event(kind, title, data)
        self.events.append(event)
        self.sink(event)

    # main entry point
    def solve(self, task: str, spec: Spec | None = None) -> AgentResult:
        start = time.time()
        self.events = []
        self.llm.reset_usage(self.settings.max_llm_calls)
        self.memory.start_task()
        best_code, best_score, best_result = "", -1.0, None
        trials_run, total_steps = 0, 0
        guard = LoopGuard()
        workspace: Workspace | None = None
        lessons: list[Lesson] = []
        error = None

        try:
            if self.use_memory:
                lessons = self.memory.retrieve(task, self.settings.memory_top_k)
                self.emit("memory", f"Retrieved {len(lessons)} lesson(s) from long-term memory",
                          lessons=[l.public() for l in lessons])

            synthesizer = SpecSynthesizer(self.llm, self.sandbox)
            if spec is None:
                self.emit("info", "Synthesising executable specification (examples + Hypothesis properties)")
                try:
                    spec = synthesizer.synthesize(task)
                except SpecError as exc:
                    return self._unverified_fallback(task, lessons, str(exc), start)
            self.emit("spec", f"Specification ready: {len(spec.test_names)} tests", functions=spec.functions,
                      tests=spec.tests, summary=spec.summary, vacuous=spec.vacuous, repairs=spec.repairs,
                      review=spec.review)

            for trial in range(1, self.settings.max_trials + 1):
                trials_run = trial
                self.emit("trial", f"Trial {trial} of {self.settings.max_trials}", trial=trial)
                guard.new_trial()
                coder_msgs = build_coder_messages(task, spec, lessons, self.memory.reflections)
                reply = self.llm.chat(coder_msgs, temperature=0.2 if trial == 1 else 0.8)
                code = extract_code(reply.content)
                if trial > 1 and normalized_hash(code) in guard.seen and self.llm.calls_left > 2:
                    coder_msgs += [reply.message, {"role": "user", "content": (
                        "This draft is identical to a version that already failed. Write a genuinely different "
                        "implementation.")}]
                    code = extract_code(self.llm.chat(coder_msgs, temperature=1.0).content)
                self.emit("code", "Coder produced a draft", code=code, trial=trial)

                workspace = Workspace(task, spec, code, self.sandbox, self.llm,
                                      disputes=workspace.disputes if workspace else [],
                                      tool_counts=workspace.tool_counts if workspace else {})
                result = workspace.run()
                self.emit("observation", f"Initial run: {len(result.passed)}/{result.total} passed",
                          text=format_run(result), passed=len(result.passed), total=result.total,
                          failures=failure_briefs(result))
                if trial == 1 and result.failed and not result.import_error and self.llm.calls_left > 4:
                    # Evidence-based spec triage: now that concrete counterexamples exist, wrong tests are visible.
                    applied = synthesizer.triage(task, spec, result.failed, format_failure)
                    if applied:
                        self.emit("spec", f"Specification amended by evidence-based triage: {len(applied)} test(s)",
                                  functions=spec.functions, tests=spec.tests, summary=spec.summary, vacuous=[],
                                  repairs=spec.repairs, review=applied)
                        result = workspace.run()
                        self.emit("observation", f"Re-run after triage: {len(result.passed)}/{result.total} passed",
                                  text=format_run(result), passed=len(result.passed), total=result.total,
                                  failures=failure_briefs(result))
                guard.check(code, total_steps, [f.signature for f in result.all_failures()])
                best_code, best_score, best_result = self._keep_best(workspace.code, result, best_code, best_score, best_result)
                if result.all_passed:
                    break

                steps, transcript = self._react(task, workspace, guard, lessons, total_steps)
                total_steps += steps
                best_code, best_score, best_result = self._keep_best(
                    workspace.code, workspace.last_result, best_code, best_score, best_result)
                if workspace.last_result and workspace.last_result.all_passed:
                    break
                if trial < self.settings.max_trials and self.llm.calls_left > 3:
                    self._reflect(task, transcript, workspace.last_result)
                elif trial < self.settings.max_trials:
                    break
        except BudgetExceeded as exc:
            error = str(exc)
            self.emit("info", f"Stopped: {exc}")
        except Exception as exc:  # keep the run's partial results rather than crash the UI
            error = f"{type(exc).__name__}: {exc}"
            self.emit("info", f"Agent error: {error}")

        solved = bool(best_result and best_result.all_passed)
        pass_rate = best_result.pass_rate if best_result else 0.0
        learned = None
        if self.use_memory and (trials_run > 1 or total_steps > 0) and error is None:
            learned = self._distil_lesson(task, solved)

        self.emit("done", "Solved: all specification tests pass" if solved else "Stopped without a full pass",
                  solved=solved, pass_rate=pass_rate, code=best_code, usage=self.llm.usage.as_dict())
        return AgentResult(
            task=task, code=best_code, spec=spec, solved=solved, pass_rate=pass_rate,
            trials=trials_run, steps=total_steps, usage=self.llm.usage.as_dict(), wall_time=round(time.time() - start, 2),
            disputes=workspace.disputes if workspace else [], loop_guard_triggers=guard.total_triggers,
            tool_counts=workspace.tool_counts if workspace else {}, reflections=list(self.memory.reflections),
            lessons_used=[l.lesson for l in lessons], lesson_learned=learned,
            events=[e.to_dict() for e in self.events], error=error,
        )

    def _unverified_fallback(self, task: str, lessons: list[Lesson], reason: str, start: float) -> AgentResult:
        """No valid spec: do not burn the budget against a broken test module; return a single unverified draft."""
        self.emit("info", f"No usable specification ({reason[:160]}); returning an unverified draft")
        code, error = "", reason
        try:
            messages = [
                {"role": "system", "content": prompts.CODER_SYSTEM},
                {"role": "user", "content": f"TASK:\n{task}\n\nWrite solution.py now."},
            ]
            code = extract_code(self.llm.chat(messages).content)
        except BudgetExceeded as exc:
            error = str(exc)
        self.emit("done", "Stopped without a verified solution", solved=False, pass_rate=0.0, code=code,
                  usage=self.llm.usage.as_dict())
        return AgentResult(task=task, code=code, spec=None, solved=False, pass_rate=0.0, trials=0, steps=0,
                           usage=self.llm.usage.as_dict(), wall_time=round(time.time() - start, 2),
                           lessons_used=[l.lesson for l in lessons], events=[e.to_dict() for e in self.events],
                           error=error)

    @staticmethod
    def _keep_best(code, result: RunResult | None, best_code, best_score, best_result):
        """Keep the draft with the highest score: a full pass beats any partial pass rate."""
        if result is None:
            return best_code, best_score, best_result
        score = result.pass_rate + (1.0 if result.all_passed else 0.0)
        if score > best_score:
            return code, score, result
        return best_code, best_score, best_result

    # ReAct loop
    def _react(self, task: str, ws: Workspace, guard: LoopGuard, lessons: list[Lesson], step_offset: int):
        memory_block = ""
        if lessons:
            memory_block = "\nLESSONS FROM LONG-TERM MEMORY:\n" + "\n".join(f"- {l.lesson}" for l in lessons)
        if self.memory.reflections:
            memory_block += "\nYOUR REFLECTIONS FROM EARLIER TRIALS:\n" + "\n".join(f"- {r}" for r in self.memory.reflections)
        messages = [
            {"role": "system", "content": prompts.REACT_SYSTEM},
            {"role": "user", "content": prompts.REACT_START.format(
                task=task, tests=ws.tests, numbered_code=numbered(ws.code),
                observation=format_run(ws.last_result), memory_block=memory_block)},
        ]
        transcript: list[str] = []
        steps = 0
        for step in range(1, self.settings.max_steps_per_trial + 1):
            steps = step
            reply = self.llm.chat(messages, tools=TOOL_SCHEMAS)
            messages.append(reply.message)
            if not reply.tool_calls:
                thought = reply.content.strip() or "(empty reply)"
                self.emit("thought", f"Step {step_offset + step}: Thought", text=thought)
                messages.append({"role": "user", "content": "Call exactly one tool now."})
                transcript.append(f"Step {step}: thought only: {thought[:200]}")
                continue
            call = reply.tool_calls[0]
            thought = (str(call.arguments.get("thought", "")).strip() or reply.content.strip()
                       or "(no explicit thought)")
            self.emit("thought", f"Step {step_offset + step}: Thought", text=thought)
            self.emit("tool", f"Action: {call.name}", name=call.name,
                      args={k: v for k, v in call.arguments.items() if k != "thought"})
            outcome = ws.dispatch(call.name, call.arguments)
            obs = outcome.observation
            if not outcome.edited:
                repeat = guard.check_action(call.name, call.arguments, step_offset + step,
                                            obs.splitlines()[0] if obs else "")
                if repeat:
                    obs += "\n\n" + repeat
                    self.emit("guard", "Loop guard triggered", text=repeat)
            if outcome.edited:
                warning = guard.check(ws.code, step_offset + step,
                                      [f.signature for f in ws.last_result.all_failures()])
                if warning:
                    obs += "\n\n" + warning
                    self.emit("guard", "Loop guard triggered", text=warning)
                self.emit("code", "Code updated", code=ws.code, step=step_offset + step)
            if call.name == "dispute_test":
                self.emit("dispute", "Test dispute resolved", **ws.disputes[-1])
                if outcome.tests_changed:
                    self.emit("spec", "Specification amended by arbiter", functions=ws.spec.functions,
                              tests=ws.spec.tests, summary=ws.spec.summary, vacuous=[], repairs=ws.spec.repairs)
            self.emit("observation", "Observation", text=obs,
                      passed=len(ws.last_result.passed) if ws.last_result else 0,
                      total=ws.last_result.total if ws.last_result else 0,
                      failures=failure_briefs(ws.last_result) if outcome.edited or call.name == "run_tests" else [],
                      tool=call.name, edited=outcome.edited)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": obs})
            for extra in reply.tool_calls[1:]:
                messages.append({"role": "tool", "tool_call_id": extra.id, "content": "Ignored: one tool per turn."})
            first_line = obs.splitlines()[0] if obs else ""
            brief = _brief({k: v for k, v in call.arguments.items() if k != "thought"})
            transcript.append(f"Step {step}: Thought: {thought[:300]}\n  Action: {call.name}({brief})\n  Result: {first_line[:200]}")
            if outcome.finished or (ws.last_result and ws.last_result.all_passed):
                break
            if guard.stuck and outcome.edited:
                self.emit("info", "Loop guard: ending trial early to force a fresh reflection")
                break
        return steps, transcript

    def _reflect(self, task: str, transcript: list[str], result: RunResult | None) -> None:
        failures = "\n\n".join(format_failure(f) for f in (result.all_failures() if result else [])[:3]) or "unknown"
        reply = self.llm.chat([
            {"role": "system", "content": prompts.REFLECT_SYSTEM},
            {"role": "user", "content": prompts.REFLECT_USER.format(
                task=task, trajectory="\n".join(transcript) or "(the first draft failed; no repair steps ran)",
                failures=failures)},
        ])
        self.memory.add_reflection(reply.content)
        self.emit("reflection", "Self-reflection (Reflexion)", text=reply.content.strip())

    def _distil_lesson(self, task: str, solved: bool) -> str | None:
        key_events = []
        for e in self.events:
            if e.kind in {"thought", "reflection", "guard", "dispute"}:
                text = e.data.get("text") or e.data.get("reason") or ""
                key_events.append(f"[{e.kind}] {text[:300]}")
        try:
            reply = self.llm.chat([
                {"role": "system", "content": prompts.LESSON_SYSTEM},
                {"role": "user", "content": prompts.LESSON_USER.format(
                    task=task, outcome="solved" if solved else "not solved", events="\n".join(key_events[-14:]))},
            ], json_mode=True)
            data = parse_json(reply.content)
        except (BudgetExceeded, ValueError):
            return None
        stored = self.memory.add_lesson(data.get("lesson", ""), data.get("tags", []), task,
                                        "solved" if solved else "unsolved")
        if stored:
            self.emit("lesson", "New lesson stored in long-term memory", lesson=stored.lesson, tags=stored.tags)
            return stored.lesson
        return None


def _brief(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", " ")
        parts.append(f"{k}={s[:60]!r}")
    return ", ".join(parts)
