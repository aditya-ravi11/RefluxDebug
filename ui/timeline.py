"""Turns the agent's event stream into a readable, card-based timeline (used live and for replays)."""

from __future__ import annotations

import difflib

import streamlit as st

from . import theme as T

# friendly names for the ReAct tools: (label, icon, tone, what it means)
TOOLS = {
    "run_tests": ("Ran the tests", "play_arrow", "gray", "Runs the whole specification again."),
    "inspect_failure": ("Read the failure details", "search", "blue", "Full traceback, variables and failing input."),
    "trace_test": ("Traced the execution", "timeline", "blue", "Replays the failing test line by line."),
    "eval_at_crash": ("Inspected variables", "data_object", "blue", "Evaluates an expression where the code failed."),
    "run_snippet": ("Ran an experiment", "science", "blue", "Calls the code on a custom input."),
    "apply_patch": ("Edited the code", "edit", "green", "Replaces a small piece of the code."),
    "rewrite_code": ("Rewrote the module", "restart_alt", "green", "Replaces the whole file."),
    "dispute_test": ("Challenged a test", "gavel", "amber", "Asks an independent judge whether a test is wrong."),
    "finish": ("Stopped this attempt", "stop_circle", "gray", "Ends the current attempt."),
}


def stage_of(event: dict) -> int:
    k = event["kind"]
    if k in ("memory", "info", "spec"):
        return 0
    if k in ("trial",) or (k == "code" and "trial" in event["data"]):
        return 1
    if k == "observation" and "tool" not in event["data"] and "Initial" in event["title"]:
        return 1
    if k == "reflection":
        return 3
    if k in ("lesson", "done"):
        return 4
    return 2


def pretty_test(name: str) -> str:
    base, _, param = name.partition("[")
    kind = ""
    for prefix, label in (("test_example_", "example"), ("test_property_", "property")):
        if base.startswith(prefix):
            base, kind = base[len(prefix):], label
            break
    base = base.removeprefix("test_").replace("_", " ")
    out = base + (f" [{param}" if param else "")
    return f"{out} ({kind})" if kind else out


def count_tests(source: str) -> tuple[int, int]:
    import ast

    try:
        names = [n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    except SyntaxError:
        return 0, 0
    props = sum(n.startswith("test_property") for n in names)
    return len(names) - props, props


def progress_html(passed: int, total: int) -> str:
    if not total:
        return ""
    frac = passed / total
    color = T.GREEN if passed == total else (T.AMBER if frac >= 0.5 else T.RED)
    return (f"<div class='rd-kv'><b>{passed} of {total}</b> specification tests pass</div>"
            + T.bar(frac, color))


def failures_html(failures: list[dict], limit: int = 3) -> str:
    out = []
    for f in failures[:limit]:
        example = f"<div class='x'>Failing input: <code>{T.esc(f['example'][:160])}</code></div>" if f.get("example") else ""
        where = f"<div class='x'>Raised at <code>{T.esc(f['where'][:140])}</code></div>" if f.get("where") else ""
        msg = T.esc(f["message"][:220]) if f.get("message") else ""
        out.append(f"<div class='rd-fail'><span class='n'>{T.esc(pretty_test(f['test']))}</span> "
                   f"<span class='rd-chip red'>{T.esc(f['error'])}</span><div class='m'>{msg}</div>{example}{where}</div>")
    more = len(failures) - limit
    if more > 0:
        out.append(f"<div class='rd-muted'>and {more} more failing test(s)</div>")
    return "".join(out)


def head(icon: str, tone: str, title: str, sub: str = "") -> str:
    s = f"<span class='st'>{T.esc(sub)}</span>" if sub else ""
    return (f"<div class='rd-evhead'><span class='ic {tone}'>{T.icon(icon, '1.05rem')}</span>"
            f"<span class='tt'>{T.esc(title)}</span>{s}</div>")


def args_summary(name: str, args: dict) -> str:
    if name in ("inspect_failure", "trace_test"):
        return f"on <b>{T.esc(pretty_test(args.get('test_name', '')))}</b>"
    if name == "eval_at_crash":
        return (f"evaluated <code>{T.esc(args.get('expression', ''))}</code> in "
                f"<b>{T.esc(pretty_test(args.get('test_name', '')))}</b>")
    if name == "dispute_test":
        return f"on <b>{T.esc(pretty_test(args.get('test_name', '')))}</b>: {T.esc(str(args.get('argument', ''))[:220])}"
    if name == "finish":
        return T.esc(str(args.get("summary", ""))[:220])
    return ""


class Timeline:
    """Renders events into the current Streamlit container. Call add() for every event, in order."""

    def __init__(self, show_raw: bool = True) -> None:
        self.show_raw = show_raw
        self.step = 0
        self.card = None
        self.tool = None
        self.last_code: str | None = None
        self.pending_code: str | None = None

    def add(self, e: dict) -> None:
        k, d = e["kind"], e["data"]
        handler = getattr(self, f"_{k}", None)
        if handler:
            handler(e, d)

    # stage 0
    def _memory(self, e, d):
        lessons = d.get("lessons") or []
        if lessons:
            items = "".join(f"<li>{T.esc(l['lesson'])}</li>" for l in lessons)
            with st.container(border=True):
                st.markdown(head("school", "violet", f"Recalled {len(lessons)} lesson(s) from earlier tasks")
                            + f"<ul class='rd-kv'>{items}</ul>", unsafe_allow_html=True)

    def _info(self, e, d):
        title = e["title"]
        if title.startswith(("Stopped", "Agent error", "No usable")):
            T.banner("warn", "The run stopped early", T.esc(title), "error")
        elif title.startswith("Loop guard"):
            T.banner("warn", "Loop guard ended this attempt", "The agent kept repeating itself, so it moves on to a "
                     "fresh attempt guided by a reflection.", "sync_problem")

    def _spec(self, e, d):
        amended = d.get("review") or []
        if "triage" in e["title"] or "arbiter" in e["title"]:
            with st.container(border=True):
                st.markdown(head("gavel", "amber", "Checked the failing tests against the task",
                                 f"{len(amended)} test(s) changed"), unsafe_allow_html=True)
                st.markdown("<div class='rd-kv'>A first draft failed some tests. An independent judge, who never "
                            "sees the code, compared each failing test and its counterexample with the task text.</div>",
                            unsafe_allow_html=True)
                for r in amended:
                    tone = "red" if r["verdict"] == "remove" else "amber"
                    st.markdown(f"{T.chip(r['verdict'], tone)} <b>{T.esc(pretty_test(r['test']))}</b>: "
                                f"<span class='rd-kv'>{T.esc(r['reason'])}</span>", unsafe_allow_html=True)
            return
        examples, props = count_tests(d["tests"])
        with st.container(border=True):
            st.markdown(head("checklist", "blue", "Wrote the tests before writing any code",
                             f"{examples + props} tests") +
                        f"{T.chip(f'{examples} example tests', 'blue')}{T.chip(f'{props} property tests', 'violet')}"
                        + (T.chip(f"{len(amended)} fixed by review", "amber") if amended else ""),
                        unsafe_allow_html=True)
            fns = ", ".join(f"<code>{T.esc(f.removeprefix('def ').rstrip(':'))}</code>" for f in d.get("functions", []))
            st.markdown(f"<div class='rd-kv'>Function to build: {fns}</div>", unsafe_allow_html=True)
            with st.expander("Show the specification tests"):
                st.code(d["tests"], language="python", line_numbers=True)

    # stage 1
    def _trial(self, e, d):
        n = d.get("trial", 1)
        sub = "first attempt" if n == 1 else "fresh attempt, guided by the reflection above"
        st.markdown(f"<div class='rd-trial'><span class='b'>Attempt {n}</span><span class='x'>{sub}</span></div>",
                    unsafe_allow_html=True)

    def _code(self, e, d):
        if "trial" in d:
            self.last_code = d["code"]
            with st.container(border=True):
                st.markdown(head("description", "gray", "Wrote a draft of solution.py",
                                 f"{len(d['code'].splitlines())} lines"), unsafe_allow_html=True)
                with st.expander("Show the draft"):
                    st.code(d["code"], language="python", line_numbers=True)
        else:
            self.pending_code = d["code"]

    def _observation(self, e, d):
        standalone = e["title"].startswith(("Initial", "Re-run")) or ("tool" not in d and self.card is None)
        if standalone:
            with st.container(border=True):
                label = "Re-ran the tests with the amended specification" if e["title"].startswith("Re-run") \
                    else "Ran the tests on the draft"
                st.markdown(head("play_arrow", "gray", label) + progress_html(d.get("passed", 0), d.get("total", 0))
                            + failures_html(d.get("failures") or []), unsafe_allow_html=True)
                if self.show_raw:
                    with st.expander("Raw output shown to the agent"):
                        st.code(d["text"], language="text")
            return
        if self.card is None:
            return
        with self.card:
            tool = d.get("tool") or self.tool
            text = d.get("text", "")
            if d.get("edited") and self.pending_code is not None:
                diff = "\n".join(difflib.unified_diff((self.last_code or "").splitlines(),
                                                      self.pending_code.splitlines(), "before", "after", lineterm="", n=1))
                st.code(diff or "(no change)", language="diff")
                self.last_code, self.pending_code = self.pending_code, None
                st.markdown(progress_html(d.get("passed", 0), d.get("total", 0))
                            + failures_html(d.get("failures") or [], limit=2), unsafe_allow_html=True)
            elif text.startswith(("Edit rejected", "Patch rejected")):
                T.banner("warn", "The edit was refused", T.esc(text.splitlines()[0][:260]), "block")
            elif tool == "eval_at_crash" and "\n" in text:
                where, value = text.split("\n", 1)
                st.markdown(f"<div class='rd-kv'>{T.esc(where)}</div>", unsafe_allow_html=True)
                st.code(value.strip().split("\n\nLOOP GUARD")[0], language="python")
            elif tool == "run_snippet":
                st.code(text.removeprefix("Snippet output:\n").split("\n\nLOOP GUARD")[0], language="text")
            elif tool == "trace_test":
                with st.expander("Show the execution trace", expanded=True):
                    st.code(text.split("\n\nLOOP GUARD")[0], language="text")
            elif tool == "run_tests":
                st.markdown(progress_html(d.get("passed", 0), d.get("total", 0))
                            + failures_html(d.get("failures") or []), unsafe_allow_html=True)
            elif self.show_raw:
                with st.expander("Result"):
                    st.code(text, language="text")
        self.card = None

    # stage 2
    def _thought(self, e, d):
        self.pending_thought = d["text"]

    def _tool(self, e, d):
        self.step += 1
        self.tool = d["name"]
        label, icon, tone, _ = TOOLS.get(d["name"], (d["name"], "circle", "gray", ""))
        self.card = st.container(border=True)
        thought = getattr(self, "pending_thought", "").removeprefix("Thought:").strip()
        with self.card:
            st.markdown(head(icon, tone, label, f"step {self.step}  ·  {d['name']}")
                        + (f"<div class='rd-thought'>{T.rich(thought)}</div>" if thought else "")
                        + (f"<div class='rd-kv'>{args_summary(d['name'], d.get('args', {}))}</div>"
                           if args_summary(d['name'], d.get('args', {})) else ""),
                        unsafe_allow_html=True)
            args = d.get("args", {})
            if d["name"] == "apply_patch" and args.get("search"):
                pass  # the diff is shown with the result
            elif d["name"] == "run_snippet" and args.get("code"):
                st.code(args["code"], language="python")
        self.pending_thought = ""

    def _guard(self, e, d):
        target = self.card if self.card is not None else st.container()
        with target:
            T.banner("warn", "Loop guard", T.esc(d["text"].removeprefix("LOOP GUARD: ")), "sync_problem")

    def _dispute(self, e, d):
        tone = "good" if d["verdict"] == "keep" else "warn"
        T.banner(tone, f"Judge's verdict: {d['verdict']}", T.esc(d.get("reason", "")), "gavel")

    # stage 3 and 4
    def _reflection(self, e, d):
        T.banner("violet", "Reflected on the failed attempt", T.rich(d["text"]), "psychology")

    def _lesson(self, e, d):
        tags = "".join(T.chip(t, "green") for t in d.get("tags", []))
        T.banner("good", "Saved a lesson for future tasks", T.rich(d["lesson"]) + f"<div>{tags}</div>", "school")

    def _done(self, e, d):
        pass  # the page shows its own summary


def healing_points(events: list[dict]) -> list[tuple[str, float]]:
    pts, attempt, step = [], 0, 0
    for e in events:
        if e["kind"] == "trial":
            attempt, step = e["data"].get("trial", attempt + 1), 0
        if e["kind"] == "observation" and e["data"].get("total") and (
                e["data"].get("edited") or "tool" not in e["data"] or e["data"].get("tool") == "run_tests"):
            if "tool" not in e["data"]:
                label = f"A{attempt} checked spec" if e["title"].startswith("Re-run") else f"A{attempt} draft"
            else:
                label = f"A{attempt} edit {step + 1}"
            if "tool" in e["data"]:
                step += 1
            pts.append((label, e["data"]["passed"] / e["data"]["total"]))
    return pts
