import json
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from benchmark.tasks import TASKS
from reflexdebug import ReflexDebugAgent, Settings
from reflexdebug.demo import DEMO_TASK, demo_llm
from reflexdebug.memory import ReflexionMemory
from ui import charts
from ui import theme as T
from ui.data import api_key_present
from ui.timeline import TOOLS, Timeline, healing_points, stage_of

T.header(
    "Run the agent",
    "Watch it write, test and repair code",
    "Choose a task, press start, and follow the five stages live. Each card below is one thing the agent did: what "
    "it was thinking, the action it took, and what came back.",
)

has_key = api_key_present()
MODES = ["Replay the demo", "Live run with OpenAI"]
mode = st.radio(
    "How do you want to run it?", MODES, horizontal=True, index=1 if has_key else 0,
    captions=["Free and offline. Model replies are pre-recorded; every test really runs.",
              "Uses your OpenAI key. About 1 to 2 US cents per task." if has_key else "Needs OPENAI_API_KEY in .env"],
)
live = mode == MODES[1]

if live:
    options = ["Write my own task"] + [t["title"] for t in TASKS]
    pick = st.selectbox("Task", options, index=0,
                        help="The benchmark tasks are precise specifications with tricky edge cases.")
    preset = "" if pick == options[0] else next(t["prompt"] for t in TASKS if t["title"] == pick)
    task = st.text_area("Describe the function to build", value=preset, height=150, key=f"task_{pick}",
                        placeholder="Example: Write is_leap(year: int) -> bool that returns True for leap years in the "
                                    "Gregorian calendar. Years divisible by 100 are not leap years unless they are "
                                    "also divisible by 400. Raise ValueError for years below 1.")
    st.caption("Tip: name the function and its exact signature, and spell out the edge cases. The agent writes its "
               "tests from this text, so anything left vague will not be tested.")
    with st.expander("Advanced settings"):
        c1, c2, c3, c4 = st.columns(4)
        model = c1.selectbox("Model", ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "gpt-4o"])
        trials = c2.number_input("Attempts", 1, 5, 3, help="Reflexion trials: fresh attempts after a reflection.")
        steps = c3.number_input("Steps per attempt", 1, 15, 6, help="Debugging actions allowed in one attempt.")
        use_memory = c4.toggle("Use memory", True, help="Recall lessons saved from earlier tasks.")
else:
    task = DEMO_TASK
    T.banner("info", "Demo task: running median", T.esc(DEMO_TASK), "description")
    model, trials, steps, use_memory = "scripted", 3, 3, True

start = st.button("Start", type="primary", disabled=(live and (not has_key or not task.strip())))

if start:
    settings = Settings()
    settings.max_trials, settings.max_steps_per_trial = int(trials), int(steps)
    if live:
        from reflexdebug.llm import LLM

        settings.model = model
        llm = LLM(settings)
        memory = ReflexionMemory(settings.memory_path, llm)
    else:
        llm = demo_llm()
        memory = ReflexionMemory(Path(tempfile.mkdtemp()) / "demo.json", llm)

    T.h2("Progress")
    tracker = st.empty()
    counters = st.empty()
    tracker.markdown(T.pipeline_html(active=0, done=0), unsafe_allow_html=True)
    timeline_box = st.container()
    tl = Timeline()
    state = {"stage": 0, "passed": 0, "total": 0, "steps": 0, "t0": time.time()}

    def sink(event):
        e = event.to_dict()
        stage = stage_of(e)
        if stage > state["stage"] or e["kind"] == "trial":
            state["stage"] = stage
        if e["kind"] == "observation" and e["data"].get("total"):
            state["passed"], state["total"] = e["data"]["passed"], e["data"]["total"]
        if e["kind"] == "tool":
            state["steps"] += 1
        done_upto = 5 if e["kind"] == "done" else state["stage"]
        tracker.markdown(T.pipeline_html(active=None if e["kind"] == "done" else state["stage"], done=done_upto),
                         unsafe_allow_html=True)
        tests = f"{state['passed']}/{state['total']}" if state["total"] else "..."
        counters.markdown(
            f"<div class='rd-muted'>Tests passing <b>{tests}</b> &nbsp;·&nbsp; debugging steps "
            f"<b>{state['steps']}</b> &nbsp;·&nbsp; model calls <b>{llm.usage.calls}</b> &nbsp;·&nbsp; "
            f"elapsed <b>{time.time() - state['t0']:.0f}s</b></div>", unsafe_allow_html=True)
        with timeline_box:
            tl.add(e)

    result = ReflexDebugAgent(llm, settings, memory=memory, sink=sink, use_memory=use_memory).solve(task)
    st.session_state["run_result"] = {"result": result.to_dict(), "live": live, "model": model}
    st.rerun()

saved = st.session_state.get("run_result")
if saved and not start:
    r = saved["result"]
    st.divider()
    total = 0
    for e in reversed(r["events"]):
        if e["kind"] == "observation" and e["data"].get("total"):
            total = e["data"]["total"]
            break
    if r["solved"]:
        T.banner("good", "Solved: the final code passes every specification test",
                 f"It took {r['trials']} attempt(s) and {r['steps']} debugging step(s).", "check_circle")
    elif r.get("error"):
        T.banner("bad", "Stopped before a full pass", T.esc(r["error"]) + ". The best version found is shown below.",
                 "error")
    else:
        T.banner("bad", "Not fully solved", "The step budget ran out. The best version found is shown below.", "error")

    T.stats([
        ("Spec tests passing", f"{r['pass_rate']:.0%}", f"of {total} tests" if total else "", "good" if r["solved"] else "bad"),
        ("Attempts", str(r["trials"]), "Reflexion trials", ""),
        ("Debugging steps", str(r["steps"]), "ReAct actions", ""),
        ("Model calls", str(r["usage"]["llm_calls"]), f"{r['usage']['prompt_tokens'] + r['usage']['completion_tokens']:,} tokens", ""),
        ("Cost", f"${r['usage']['cost_usd']:.4f}" if saved["live"] else "free", "estimated" if saved["live"] else "replay", ""),
        ("Time", f"{r['wall_time']:.0f}s", "wall clock", ""),
    ])

    tab_story, tab_code, tab_tests, tab_progress = st.tabs(["What happened", "Final code", "Tests", "Progress"])
    with tab_story:
        T.pipeline(done=5, compact=True)
        tl = Timeline()
        for e in r["events"]:
            tl.add(e)
    with tab_code:
        st.code(r["code"] or "# no code produced", language="python", line_numbers=True)
        st.download_button("Download solution.py", r["code"] or "", "solution.py")
    with tab_tests:
        if r.get("spec"):
            st.markdown("<div class='rd-kv'>The tests the agent wrote for itself (after review and triage).</div>",
                        unsafe_allow_html=True)
            st.code(r["spec"]["tests"], language="python", line_numbers=True)
        else:
            st.info("No usable specification was produced for this run.")
    with tab_progress:
        pts = healing_points(r["events"])
        if len(pts) > 1:
            T.h2("Share of tests passing after each draft and edit")
            st.altair_chart(charts.healing(pts), use_container_width=True)
        if r.get("tool_counts"):
            T.h2("Debugging actions used")
            df = pd.DataFrame([{"Action": TOOLS.get(k, (k,))[0], "Tool": k, "Times": v}
                               for k, v in sorted(r["tool_counts"].items(), key=lambda kv: -kv[1])])
            st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("Download the full trace (JSON)", json.dumps(r, indent=1), "reflexdebug_trace.json",
                           mime="application/json")
elif not start:
    T.h2("What you will see")
    T.pipeline()
    st.markdown("<div class='rd-muted'>Start a run to fill this in live. New here? The guided tour explains each "
                "stage with a real example first.</div>", unsafe_allow_html=True)
