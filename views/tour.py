import difflib

import streamlit as st

from reflexdebug.spec import get_test_source
from ui import charts
from ui import theme as T
from ui.data import demo_run
from ui.timeline import failures_html, healing_points, pretty_test, progress_html

P = st.session_state["pages"]

with st.spinner("Preparing the walkthrough (running the demo in the sandbox)..."):
    run = demo_run()
ev = run["events"]


def find(kind, start=0, pred=lambda e: True):
    for i in range(start, len(ev)):
        if ev[i]["kind"] == kind and pred(ev[i]):
            return i
    return None


i_spec = find("spec")
i_draft = find("code", pred=lambda e: e["data"].get("trial") == 1)
i_obs1 = find("observation", i_draft)
i_tools = [i for i, e in enumerate(ev) if e["kind"] == "tool"]
i_reflect = find("reflection")
i_draft2 = find("code", pred=lambda e: e["data"].get("trial") == 2)
i_obs2 = find("observation", i_draft2)
i_lesson = find("lesson")


def thought_before(i):
    for j in range(i, -1, -1):
        if ev[j]["kind"] == "thought":
            return ev[j]["data"]["text"].removeprefix("Thought:").strip()
    return ""


def obs_after(i):
    return ev[find("observation", i)]


spec = ev[i_spec]["data"]
draft = ev[i_draft]["data"]["code"]
obs1 = ev[i_obs1]["data"]
t_eval, t_patch, t_snip = i_tools[:3]
obs_eval, obs_patch, obs_snip = obs_after(t_eval)["data"], obs_after(t_patch)["data"], obs_after(t_snip)["data"]
patched = ev[find("code", t_patch)]["data"]["code"]


def why(text):
    st.markdown(f"<div class='rd-why'><b>Why this matters.</b> {text}</div>", unsafe_allow_html=True)


def say(text):
    st.markdown(f"<div style='font-size:.97rem;line-height:1.65;color:#2b2a28'>{text}</div>", unsafe_allow_html=True)


def s_task():
    say("This is the whole input: one paragraph describing a function. The agent has to build "
        "<code>running_median(xs)</code>, which returns the median of every prefix of a list. The catch is in one "
        "sentence: for an even number of values the median is the <b>mean of the two middle values</b>.")
    say("<br>Over the next steps you will watch the agent go through the five stages shown on the right. Everything you see "
        "really ran in the sandbox; only the model's replies are pre-recorded, so the tour works without an API key.")
    why("Most coding agents only react when the program crashes. A median that is slightly wrong never crashes, "
        "so this task shows what the extra machinery is for.")
    return lambda: (T.banner("info", "The task", T.esc(run["task"]), "description"), T.pipeline(compact=True))


def s_spec():
    say("Before writing a single line of the solution, the agent writes the tests. It writes two kinds: "
        "<b>example tests</b>, which check one concrete input, and <b>property tests</b>, which state a rule that "
        "must hold for every input. The property test here compares the answer with Python's own "
        "<code>statistics.median</code> on hundreds of random lists.")
    say("<br>The spec is checked before it is used: it must be valid, safe Python, and it is reviewed against the "
        "task so that tests that ask for something the task never said are fixed or dropped.")
    why("Tests written first turn a silent wrong answer into a visible failure. In our mutation study, 43% of "
        "real bugs raised no error at all.")

    def right():
        for name in ("test_example_even_length", "test_property_matches_oracle"):
            src = get_test_source(spec["tests"], name)
            if src:
                st.markdown(T.chip("example test" if "example" in name else "property test",
                                   "blue" if "example" in name else "violet"), unsafe_allow_html=True)
                st.code(src, language="python")
        with st.expander("All tests in the specification"):
            st.code(spec["tests"], language="python", line_numbers=True)
    return right


def s_draft():
    say(f"Now the agent writes a first draft and runs the tests in the sandbox. Only "
        f"<b>{obs1['passed']} of {obs1['total']}</b> pass. Look at the failures on the right: every value for an "
        "odd-length prefix is right, and every value for an even-length prefix is wrong. For "
        "<code>[5, 1, 3]</code> the middle answer should be 3 (the mean of 1 and 5) but the draft says 5.")
    say("<br>Notice the <b>failing input</b> line. The property test tried hundreds of lists and then shrank the "
        "failure down to the smallest list that still breaks: <code>xs=[0, 1]</code>.")
    say("<br>Before blaming the code, an independent judge (who never sees the code) checks whether each failing "
        "test really follows from the task. Here all of them do, so they are kept.")
    why("A two-element list is the kind of evidence a person would want. It points straight at the even-length "
        "case instead of a wall of random numbers.")

    def right():
        st.code(draft, language="python", line_numbers=True)
        st.markdown(progress_html(obs1["passed"], obs1["total"]) + failures_html(obs1.get("failures") or [], 4),
                    unsafe_allow_html=True)
    return right


def s_inspect():
    say("The test failed on a wrong value, not an exception, so there is no crash line to look at. Instead the agent "
        "asks the debugger to evaluate variables inside <code>running_median()</code> at the moment it returned for "
        "the failing input.")
    say(f"<br><b>Agent's reasoning:</b> <i>{T.rich(thought_before(t_eval))}</i>")
    why("This is the debugger-grounded part. Instead of guessing from a stack trace, the agent reads the program's "
        "actual state for the smallest failing input.")

    def right():
        st.markdown(T.chip("action: eval_at_crash", "blue"), unsafe_allow_html=True)
        where, value = obs_eval["text"].split("\n", 1)
        st.markdown(f"<div class='rd-kv'>{T.esc(where)}</div>", unsafe_allow_html=True)
        st.code(value.strip(), language="python")
        st.markdown("<div class='rd-kv'>For the sorted prefix <code>[0, 1]</code> the code returned <code>1</code>, "
                    "the upper middle value. The correct median is <code>0.5</code>.</div>", unsafe_allow_html=True)
    return right


def s_patch():
    say("With that evidence the agent makes a small, targeted edit: when the length is even, average the two middle "
        "values. The tests re-run automatically after every edit.")
    say(f"<br><b>Agent's reasoning:</b> <i>{T.rich(thought_before(t_patch))}</i>")
    say(f"<br>Progress: <b>{obs_patch['passed']} of {obs_patch['total']}</b> now pass. The remaining failures share "
        "one cause, and the failing input shows it: the average of 0 and 1 came out as 0.")
    why("Small edits keep everything that already worked. Whole-file rewrites often fix one thing and break another.")

    def right():
        diff = "\n".join(difflib.unified_diff(draft.splitlines(), patched.splitlines(), "before", "after",
                                              lineterm="", n=1))
        st.code(diff, language="diff")
        st.markdown(progress_html(obs_patch["passed"], obs_patch["total"])
                    + failures_html(obs_patch.get("failures") or [], 2), unsafe_allow_html=True)
    return right


def s_probe():
    say("Instead of fixing it straight away, the agent runs a quick experiment to confirm what the new code does. "
        "The output confirms it: <code>// 2</code> is floor division, so 1.5 becomes 1.")
    say(f"<br><b>Agent's reasoning:</b> <i>{T.rich(thought_before(t_snip))}</i>")
    say("<br>That used the last step of this attempt, so the attempt ends without a full pass.")
    why("Every attempt has a small step budget. Running out is normal; what matters is what the agent does next.")

    def right():
        code = ev[t_snip]["data"]["args"].get("code", "")
        st.markdown(T.chip("action: run_snippet", "blue"), unsafe_allow_html=True)
        st.code(code, language="python")
        st.markdown("<div class='rd-kv'>Output</div>", unsafe_allow_html=True)
        st.code(obs_snip["text"].removeprefix("Snippet output:\n"), language="text")
    return right


def s_reflect():
    reflection = ev[i_reflect]["data"]["text"]
    obs2 = ev[i_obs2]["data"]
    say("When an attempt fails, the agent writes a short reflection: what went wrong, why its fixes did not work, and "
        "what to do differently. This is the Reflexion idea: learning from a failure in words, not by retraining.")
    say(f"<br>A fresh attempt then starts with that reflection in mind. This time the first draft passes "
        f"<b>{obs2['passed']} of {obs2['total']}</b> tests.")
    why("Starting over with a clear diagnosis often beats patching a broken design. The reflection is what makes the "
        "second attempt different from the first.")

    def right():
        T.banner("violet", "The agent's reflection", T.rich(reflection), "psychology")
        st.code(ev[i_draft2]["data"]["code"], language="python", line_numbers=True)
        st.markdown(progress_html(obs2["passed"], obs2["total"]), unsafe_allow_html=True)
    return right


def s_learn():
    lesson = ev[i_lesson]["data"]
    say("Finally the agent turns the experience into a short, general lesson and saves it with an embedding. When a "
        "future task looks similar, the lesson is recalled and shown to the agent before it starts.")
    say(f"<br>This run needed <b>{run['usage']['llm_calls']} model calls</b> across <b>{run['trials']} attempts</b>. "
        "The chart shows the share of tests passing after each draft and edit.")
    why("Reflections help within one task; lessons carry over to the next one.")

    def right():
        T.banner("good", "Lesson saved to memory", T.rich(lesson["lesson"]), "school")
        st.altair_chart(charts.healing(healing_points(ev)), use_container_width=True)
    return right


STEPS = [
    ("The task", None, s_task),
    ("Tests come first", 0, s_spec),
    ("A first draft, and what fails", 1, s_draft),
    ("Looking inside the code", 2, s_inspect),
    ("A small, targeted fix", 2, s_patch),
    ("A quick experiment", 2, s_probe),
    ("Reflect and try again", 3, s_reflect),
    ("Remember the lesson", 4, s_learn),
]

if "tour_step" not in st.session_state:
    st.session_state.tour_step = 0
n = st.session_state.tour_step
title, stage, builder = STEPS[n]

T.header("Guided tour", title)
dots = "".join(f"<span class='{'on' if i <= n else ''}'></span>" for i in range(len(STEPS)))
st.markdown(f"<div class='rd-muted'>Step {n + 1} of {len(STEPS)}</div><div class='rd-dots'>{dots}</div>",
            unsafe_allow_html=True)
if stage is not None:
    T.pipeline(active=stage, done=stage, compact=True)

left, right = st.columns([0.9, 1.1], gap="large")
with left:
    render_right = builder()
with right:
    render_right()

st.write("")
b1, b2, _, b3 = st.columns([1, 1.4, 1.2, 1.5])
if b1.button("Back", disabled=n == 0, use_container_width=True):
    st.session_state.tour_step = n - 1
    st.rerun()
if n < len(STEPS) - 1:
    if b2.button("Next", type="primary", use_container_width=True):
        st.session_state.tour_step = n + 1
        st.rerun()
else:
    if b2.button("Run it yourself", type="primary", use_container_width=True):
        st.switch_page(P["run"])
    if b3.button("See the results", use_container_width=True):
        st.switch_page(P["results"])
if 0 < n < len(STEPS) - 1:
    if b3.button("Restart the tour", key="restart", use_container_width=True):
        st.session_state.tour_step = 0
        st.rerun()
