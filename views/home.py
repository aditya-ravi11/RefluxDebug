import streamlit as st

from ui import theme as T
from ui.data import results

P = st.session_state["pages"]
R = results()

T.header(
    "Generative AI Lab CA",
    "ReflexDebug",
    "Give it a programming task in plain English. It writes tests first, writes the code, runs everything in a "
    "sandbox, and when something fails it investigates like a person with a debugger: it looks at the failing input, "
    "traces the variables, edits the exact line, and if it gets stuck it reflects and starts a fresh attempt.",
)

c1, c2, _ = st.columns([1.35, 1, 2.2])
if c1.button("Take the guided tour", type="primary", use_container_width=True):
    st.switch_page(P["tour"])
if c2.button("Run the agent", use_container_width=True):
    st.switch_page(P["run"])

T.h2("How one run works")
T.pipeline()

bench = R.get("benchmark")
mut = (R.get("mutation_study") or {}).get("summary")
safety = (R.get("safety_eval") or {}).get("summary")
audit = (R.get("spec_audit") or {}).get("summary")

T.h2("What we found")
items = []
if mut:
    items.append(("Bugs that raise no error", f"{mut['silent_logic_bug_pct']:.0%}",
                  "of injected bugs only return a wrong value", "accent"))
if bench:
    by = {s["strategy"]: s for s in bench["summary"]}
    if "one_shot" in by and "rich_feedback" in by:
        items.append(("Hidden tests passed", f"{by['one_shot']['mean_hidden_pass_rate']:.0%} to "
                      f"{max(s['mean_hidden_pass_rate'] for s in bench['summary']):.0%}",
                      "one-shot vs best repair loop", "good"))
if audit:
    items.append(("Self-written specs fully correct", f"{audit['specs_consistent_with_reference']}/{audit['runs']}",
                  "checked against known-good solutions", ""))
if safety:
    items.append(("Hostile code blocked", f"{safety['hostile_blocked']}/{safety['hostile_samples']}",
                  f"with {safety['benign_samples'] - safety['benign_accepted']} false alarms", "good"))
if items:
    T.stats(items)

st.markdown(
    "<div class='rd-card'><h4>The short version</h4><p>Every repair loop we tested made partly-correct code more "
    "correct, but with a small model none of them solved more tasks outright than asking once. The reason turned out "
    "to be the tests the agent writes for itself: when they are wrong, the agent cannot recognise correct code. The "
    "Results page walks through the evidence.</p></div>",
    unsafe_allow_html=True,
)

T.h2("Where to go next")
a, b, c = st.columns(3)
with a:
    st.markdown(T.card("Guided tour", "Follow one real repair from task to fixed code, one step at a time, with "
                       "an explanation of what the agent is doing and why."), unsafe_allow_html=True)
    if st.button("Start the tour", key="go_tour", use_container_width=True):
        st.switch_page(P["tour"])
with b:
    st.markdown(T.card("Run the agent", "Give it your own task, or a benchmark task, and watch each stage live. "
                       "A free replay of the demo works without an API key."), unsafe_allow_html=True)
    if st.button("Open the runner", key="go_run", use_container_width=True):
        st.switch_page(P["run"])
with c:
    st.markdown(T.card("Results", "The benchmark against three simpler strategies, the spec audit and the "
                       "offline experiments, explained in plain language."), unsafe_allow_html=True)
    if st.button("See the results", key="go_results", use_container_width=True):
        st.switch_page(P["results"])
