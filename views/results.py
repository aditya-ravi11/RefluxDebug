import pandas as pd
import streamlit as st

from benchmark.tasks import TASK_BY_ID
from ui import charts
from ui import theme as T
from ui.data import results

R = results()
bench, audit, audit_v2 = R.get("benchmark"), R.get("spec_audit"), R.get("spec_audit_v2")

T.header(
    "Results",
    "How well does it work?",
    "We compared the full agent with three simpler strategies on 14 tricky programming tasks. Every final answer "
    "was scored on hidden tests that no strategy ever saw, so an agent cannot game its own tests.",
)

if not bench:
    T.banner("info", "No benchmark results yet", "Run <code>python cli.py bench</code> with an OpenAI key in .env, "
             "then refresh this page.", "bar_chart")
    st.stop()

ARMS = {
    "one_shot": ("One-shot", "Ask the model once. No tests, no feedback."),
    "traceback_loop": ("Traceback loop", "A few simple tests; show the error message and ask for a rewrite."),
    "rich_feedback": ("Rich feedback", "Reviewed tests with properties; show failing inputs and variables; rewrite."),
    "reflexdebug": ("ReflexDebug (full)", "All of the above plus debugger tools, small edits, reflection and memory."),
}
by = {s["strategy"]: s for s in bench["summary"]}

T.h2("The four strategies")
cards = []
for key, (name, desc) in ARMS.items():
    dot = (f"<span style='display:inline-block;width:.6rem;height:.6rem;border-radius:50%;"
           f"background:{T.ARM_COLORS[key]};margin-right:.45rem'></span>")
    cards.append(f"<div class='rd-card' style='margin:0'><h4>{dot}{T.esc(name)}</h4><p>{T.esc(desc)}</p></div>")
st.markdown("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.75rem;"
            f"margin-bottom:.8rem'>{''.join(cards)}</div>", unsafe_allow_html=True)
st.markdown(f"<div class='rd-muted'>Model {T.esc(bench['model'])}, at most {bench['max_llm_calls']} model calls per "
            f"task for every strategy, one run per task. Total cost of the benchmark: "
            f"${sum(s['total_cost_usd'] for s in bench['summary']):.2f}.</div>", unsafe_allow_html=True)

T.h2("Headline numbers")
with st.container(border=True):
    st.markdown("<div class='rd-kv'><b>Tasks fully solved</b> (every hidden test passes)</div>", unsafe_allow_html=True)
    st.altair_chart(charts.arm_bars(bench["summary"], "solve_rate", "share of the 14 tasks"), use_container_width=True)
with st.container(border=True):
    st.markdown("<div class='rd-kv'><b>Hidden tests passed</b> (average over tasks)</div>", unsafe_allow_html=True)
    st.altair_chart(charts.arm_bars(bench["summary"], "mean_hidden_pass_rate", "share of hidden tests"),
                    use_container_width=True)

best = max(bench["summary"], key=lambda s: s["mean_hidden_pass_rate"])
T.banner(
    "info", "What this means",
    f"Every repair loop made partly-correct code more correct than asking once "
    f"({by['one_shot']['mean_hidden_pass_rate']:.0%} for one-shot, up to {best['mean_hidden_pass_rate']:.0%} for "
    f"{T.esc(best['label'])}). But none of them solved more tasks outright: one-shot solved "
    f"{by['one_shot']['solved']}, each loop solved {by['reflexdebug']['solved']}. With a small model and 20 calls, "
    f"feedback mostly turns half-right code into mostly-right code. The next section shows what holds it back.",
    "lightbulb",
)

T.h2("Task by task")
st.markdown("<div class='rd-muted'>Green means every hidden test passed. Otherwise the cell shows the share of hidden "
            "tests passed.</div>", unsafe_allow_html=True)


def cell(row):
    if row is None:
        return "<td style='background:#efeeea'>-</td>"
    if row["hidden_solved"]:
        return "<td style='background:#e3f4ea;color:#17724a'>solved</td>"
    v = row["hidden_pass_rate"]
    bg, fg = ("#fbf1dc", "#8a5a10") if v >= 0.75 else (("#fcecec", "#b13a3a") if v < 0.5 else ("#fdf3ea", "#9a4f1c"))
    return f"<td style='background:{bg};color:{fg}'>{v:.0%}</td>"


head = "".join(f"<th>{T.esc(ARMS[s][0])}</th>" for s in bench["strategies"])
rows = []
for t in bench["tasks"]:
    cells = "".join(cell(next((r for r in bench["rows"] if r["task"] == t and r["strategy"] == s), None))
                    for s in bench["strategies"])
    rows.append(f"<tr><td class='task'>{T.esc(TASK_BY_ID[t]['title'])}</td>{cells}</tr>")
st.markdown(f"<table class='rd-grid'><tr><th>Task</th>{head}</tr>{''.join(rows)}</table>", unsafe_allow_html=True)

with st.expander("Cost and effort per strategy"):
    df = pd.DataFrame([{
        "Strategy": s["label"], "Solved": f"{s['solved']}/{s['tasks']}",
        "Hidden tests passed": f"{s['mean_hidden_pass_rate']:.1%}",
        "Passed own tests but failed hidden ones": s["false_confidence"],
        "Model calls per task": s["mean_llm_calls"], "Tokens per task": f"{s['mean_tokens']:,}",
        "Total cost (USD)": f"{s['total_cost_usd']:.3f}", "Seconds per task": s["mean_wall_time_s"],
    } for s in bench["summary"]])
    st.dataframe(df, hide_index=True, use_container_width=True)

if audit:
    a = audit["summary"]
    T.h2("What holds it back: the agent's own tests")
    st.markdown(
        "<div class='rd-sub' style='margin-bottom:.6rem'>Because we have a correct reference solution for every task, "
        "we can test the tests: any test the correct solution fails is a wrong test. A loop that trusts a wrong test "
        "can never accept correct code, so it keeps editing until its budget runs out.</div>",
        unsafe_allow_html=True)
    items = []
    if audit_v2:
        v2 = audit_v2["summary"]
        items.append(("Specs fully correct, before triage", f"{v2['specs_consistent_with_reference']}/{v2['runs']}",
                      "version 2 of the agent", "bad"))
    items += [
        ("Specs fully correct, with triage", f"{a['specs_consistent_with_reference']}/{a['runs']}", "final version", "good"),
        ("Runs improved by repair", f"{a['repair_improved']}/{a['runs']}", "and none made worse", "good"),
        ("Triage changes that were right", f"{a['triage_justified']}/{a['triage_amendments']}",
         "the judge also blamed correct tests", "accent"),
    ]
    T.stats(items)
    st.markdown(
        "<div class='rd-card'><h4>Evidence-based triage</h4><p>After the first draft runs, each failing test and its "
        "smallest failing input go to an independent judge that sees the task but not the code. That caught tests "
        "with impossible inputs (for example an interval whose start is after its end, which the task says must be "
        "rejected). It also removed some correct tests, so a stronger judge model is the clearest next step.</p></div>",
        unsafe_allow_html=True)

mut, safety = (R.get("mutation_study") or {}).get("summary"), (R.get("safety_eval") or {}).get("summary")
if mut or safety:
    T.h2("Offline experiments (no model involved)")
    c1, c2 = st.columns(2, gap="large")
    if mut:
        with c1:
            st.markdown(
                T.card("What does a failure tell you?",
                       f"We injected {mut['mutants']} small bugs into correct solutions. {mut['silent_logic_bug_pct']:.0%} "
                       f"of the detected bugs raised no error at all, and for crashes the reported line was the faulty "
                       f"line only {mut['crash_line_exact_pct_of_exceptions']:.0%} of the time. Property tests produced a "
                       f"minimal failing input {mut['falsifying_example_pct_of_property_failures']:.0%} of the time."),
                unsafe_allow_html=True)
    if safety:
        with c2:
            st.markdown(
                T.card("Is the sandbox safe?",
                       f"The static gate blocked {safety['hostile_blocked']} of {safety['hostile_samples']} hostile "
                       f"programs and accepted all {safety['benign_accepted']} legitimate ones. All "
                       f"{safety['resource_abuse_contained']} resource-abuse programs (infinite loop, memory bomb, deep "
                       f"recursion, output flood, exponential work) were stopped within seconds."),
                unsafe_allow_html=True)

versions = [(lbl, R.get(key)) for lbl, key in (("Version 1 (stopped after 8 tasks)", "benchmark_v1"),
                                                ("Version 2", "benchmark_v2"), ("Final", "benchmark"))]
rows = []
for lbl, data in versions:
    if not data:
        continue
    rs = [r for r in data["rows"] if r["strategy"] == "reflexdebug"]
    if rs:
        rows.append({"Version": lbl, "Tasks": len(rs), "Solved": sum(r["hidden_solved"] for r in rs),
                     "Hidden tests passed": f"{sum(r['hidden_pass_rate'] for r in rs) / len(rs):.1%}",
                     "Model calls per task": round(sum(r["usage"]["llm_calls"] for r in rs) / len(rs), 1)})
if len(rows) > 1:
    with st.expander("How the full agent changed between versions"):
        st.markdown("<div class='rd-kv'>Each version fixed problems found by reading the previous version's traces "
                    "(never the hidden tests). The full list of changes is in the lab report, Section 10.4.</div>",
                    unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
