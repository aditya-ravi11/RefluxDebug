import datetime as dt

import streamlit as st

from reflexdebug.config import Settings
from reflexdebug.memory import ReflexionMemory
from ui import theme as T
from ui.data import RESULTS

T.header(
    "Memory",
    "Lessons the agent has learned",
    "After a task that needed repair, the agent writes one short, general lesson and stores it with an embedding. "
    "When a new task looks similar, the closest lessons are shown to the agent before it starts.",
)

sources = {"Lessons from your runs": Settings().memory_path,
           "Lessons learned during the benchmark": RESULTS / "benchmark_memory.json"}
choice = st.radio("Show", list(sources), horizontal=True, label_visibility="collapsed")
mem = ReflexionMemory(sources[choice])

if not mem.lessons:
    T.banner("info", "No lessons yet",
             "Lessons appear here after a live run where the agent had to debug or retry. Runs that pass on the first "
             "draft teach nothing new, so they store nothing.", "school")
else:
    st.markdown(f"<div class='rd-muted'>{len(mem.lessons)} lesson(s)</div>", unsafe_allow_html=True)
    for lesson in sorted(mem.lessons, key=lambda l: l.created, reverse=True):
        tags = "".join(T.chip(t, "green") for t in lesson.tags)
        outcome = T.chip("task solved", "green") if lesson.outcome == "solved" else T.chip("task not solved", "amber")
        when = dt.datetime.fromtimestamp(lesson.created).strftime("%d %b %Y, %H:%M")
        st.markdown(
            f"<div class='rd-card'><h4>{T.esc(lesson.lesson)}</h4><div style='margin:.35rem 0'>{tags}{outcome}</div>"
            f"<p class='rd-muted'>Learned from: {T.esc(lesson.source_task[:160])}{'...' if len(lesson.source_task) > 160 else ''}"
            f" &nbsp;·&nbsp; {when}</p></div>",
            unsafe_allow_html=True)
    if choice == "Lessons from your runs":
        with st.expander("Reset memory"):
            st.markdown("<div class='rd-kv'>This deletes every lesson from your runs. The benchmark memory is not "
                        "affected.</div>", unsafe_allow_html=True)
            if st.button("Delete all lessons"):
                mem.clear()
                st.rerun()
