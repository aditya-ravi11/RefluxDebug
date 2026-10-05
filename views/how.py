import streamlit as st

from ui import theme as T
from ui.data import ROOT
from ui.timeline import TOOLS

T.header(
    "How it works",
    "Under the hood",
    "The ideas behind the agent, in plain terms. The lab report has the full details and references.",
)

T.h2("The five stages")
T.pipeline()

arch = ROOT / "report" / "figures" / "architecture.png"
if arch.exists():
    with st.expander("Full architecture diagram", expanded=False):
        st.image(str(arch), use_column_width=True)

T.h2("Key ideas")
IDEAS = [
    ("Tests first (the specification)",
     "Before any code exists the agent writes example tests and property tests. A property test states a rule for "
     "all inputs, for example 'the answer equals statistics.median', and the Hypothesis library searches for an input "
     "that breaks it, then shrinks it to the smallest such input."),
    ("ReAct: think, act, observe",
     "Each debugging step is a short piece of reasoning followed by exactly one action, such as tracing a test or "
     "editing a line. The result of the action is the observation that the next step reasons about."),
    ("Debugger-grounded evidence",
     "When a test fails the agent sees the failing input and the variables at the point of failure. For wrong answers, "
     "where nothing crashes, it can replay the test line by line and read the values."),
    ("Reflexion",
     "If an attempt runs out of steps, the agent writes a short reflection on what went wrong and starts a fresh "
     "attempt with that reflection in mind, instead of patching the same broken design forever."),
    ("Checking its own tests",
     "Self-written tests can be wrong. A review pass checks them against the task before coding, and after the first "
     "draft an independent judge looks at each failing test and its counterexample, without seeing the code."),
    ("Loop guard and memory",
     "The agent is warned when it repeats the same action or returns to code that already failed. After each task, a "
     "general lesson is stored and recalled for similar tasks later."),
]
cols = st.columns(2, gap="medium")
for i, (title, body) in enumerate(IDEAS):
    cols[i % 2].markdown(T.card(title, body), unsafe_allow_html=True)

T.h2("The agent's tools")
rows = "".join(
    f"<tr><td style='white-space:nowrap;padding:.45rem .6rem'><span class='ic {tone}' style='display:inline-flex;"
    f"width:1.6rem;height:1.6rem;border-radius:7px;align-items:center;justify-content:center;margin-right:.5rem'>{T.icon(icon, '1rem')}"
    f"</span><b>{T.esc(label)}</b></td><td style='padding:.45rem .6rem'><code>{name}</code></td>"
    f"<td style='padding:.45rem .6rem;color:#5b5a56'>{T.esc(desc)}</td></tr>"
    for name, (label, icon, tone, desc) in TOOLS.items()
)
st.markdown(f"<div class='rd-card' style='padding:.4rem .5rem'><table class='rd-tools' style='width:100%;border-collapse:collapse;"
            f"font-size:.9rem'>{rows}</table></div>", unsafe_allow_html=True)

T.h2("Safety")
st.markdown(T.card(
    "Two layers between generated code and your computer",
    "First, every program is parsed and rejected if it imports anything outside an allowlist (no os, subprocess, "
    "network or file access) or uses known escape tricks. Second, whatever passes runs in a separate Python process "
    "with CPU, memory, file-size and time limits. Tests that hang are stopped individually and reported, so one bad "
    "loop cannot freeze the run."), unsafe_allow_html=True)

T.h2("Glossary")
GLOSSARY = [
    ("Hidden tests", "Tests we wrote for scoring. No strategy ever sees them."),
    ("Specification", "The tests the agent writes for itself before coding."),
    ("Property test", "A test that checks a rule on many generated inputs."),
    ("Counterexample", "The smallest input that makes a test fail."),
    ("Attempt (trial)", "One draft plus the debugging steps that follow it."),
    ("Step", "One think-then-act cycle inside an attempt."),
]
st.markdown("<div class='rd-stats'>" + "".join(
    f"<div class='rd-stat'><div class='l'>{T.esc(k)}</div><div class='s' style='font-size:.88rem;margin-top:.3rem'>"
    f"{T.esc(v)}</div></div>" for k, v in GLOSSARY) + "</div>", unsafe_allow_html=True)
