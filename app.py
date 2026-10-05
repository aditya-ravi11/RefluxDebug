"""ReflexDebug web UI.  Run with:  streamlit run app.py"""

from __future__ import annotations

import streamlit as st

from ui import theme
from ui.data import api_key_present

st.set_page_config(page_title="ReflexDebug", page_icon=":material/bug_report:", layout="wide",
                   initial_sidebar_state="expanded")
theme.apply()

PAGES = {
    "home": st.Page("views/home.py", title="Start here", icon=":material/home:", default=True),
    "tour": st.Page("views/tour.py", title="Guided tour", icon=":material/tour:"),
    "run": st.Page("views/run.py", title="Run the agent", icon=":material/play_circle:"),
    "memory": st.Page("views/memory.py", title="Memory", icon=":material/psychology:"),
    "results": st.Page("views/results.py", title="Results", icon=":material/insights:"),
    "how": st.Page("views/how.py", title="How it works", icon=":material/schema:"),
}
st.session_state["pages"] = PAGES

nav = st.navigation({
    "Get started": [PAGES["home"], PAGES["tour"]],
    "Use it": [PAGES["run"], PAGES["memory"]],
    "Understand it": [PAGES["results"], PAGES["how"]],
})

nav.run()

with st.sidebar:
    if api_key_present():
        st.markdown(theme.chip("Live mode ready", "green") + "<div class='rd-muted'>OpenAI key found in .env</div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(theme.chip("Offline", "amber") + "<div class='rd-muted'>No OpenAI key; the demo and all results "
                    "still work</div>", unsafe_allow_html=True)
