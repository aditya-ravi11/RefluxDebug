"""Design system for the ReflexDebug web UI: CSS, colour tokens and small HTML building blocks."""

from __future__ import annotations

import html

import streamlit as st

INK, INK2, MUTED, LINE = "#1b1b1a", "#5b5a56", "#8a8983", "#e4e3df"
BLUE, GREEN, RED, AMBER, VIOLET = "#2a78d6", "#1f8a5b", "#d24b4b", "#b7791f", "#5b4bc4"
# categorical order for the four benchmark arms (validated palette, see report/figures.py)
ARM_COLORS = {"one_shot": "#2a78d6", "traceback_loop": "#eb6834", "rich_feedback": "#1baf7a", "reflexdebug": "#eda100"}

STAGES = [
    ("Specify", "Write tests before any code"),
    ("Draft", "Write a first implementation"),
    ("Debug", "Gather evidence and fix, step by step"),
    ("Reflect", "Explain the failure, try again"),
    ("Learn", "Store a lesson for next time"),
]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, .stApp, .stMarkdown, .stMarkdown p, .stMarkdown li, label, p, h1, h2, h3, h4, li, td, th,
button, input, textarea, select, [data-baseweb="tab"] p {
  font-family: 'Inter', system-ui, sans-serif;
}
[data-testid="stSidebarNav"] a span:last-child, [class*="rd-"], [class*="rd-"] div, [class*="rd-"] span:not(.material-symbols-rounded) {
  font-family: 'Inter', system-ui, sans-serif;
}
code, pre, [data-testid="stCode"] code, [data-testid="stCode"] pre { font-family: 'JetBrains Mono', ui-monospace, monospace !important; }
[data-testid="stIconMaterial"], span.material-symbols-rounded { font-family: 'Material Symbols Rounded' !important; }
/* always show every page in the sidebar (no "View more") */
[data-testid="stSidebarNavItems"] { max-height: none !important; }
[data-testid="stSidebarNavViewButton"] { display: none !important; }

[data-testid="stDecoration"] { display: none; }
header[data-testid="stHeader"] { background: transparent; }
.block-container, [data-testid="stMainBlockContainer"] { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }

/* sidebar */
[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e4e3df; }
[data-testid="stSidebarNav"] a span { font-size: 0.93rem; }
[data-testid="stSidebarNavSeparator"] { margin: .4rem 0; }

/* headings */
h1, h2, h3 { letter-spacing: -0.01em; color: #1b1b1a; }
.rd-eyebrow { font-size: .74rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: #2a78d6; margin-bottom: .25rem; }
.rd-title { font-size: 2rem; font-weight: 700; line-height: 1.2; margin: 0 0 .5rem 0; color: #1b1b1a; }
.rd-sub { font-size: 1.02rem; color: #5b5a56; line-height: 1.6; max-width: 760px; margin-bottom: 1.4rem; }
.rd-h2 { font-size: 1.15rem; font-weight: 650; margin: 1.6rem 0 .6rem 0; color: #1b1b1a; }
.rd-muted { color: #8a8983; font-size: .88rem; }

/* cards */
.rd-card { background: #ffffff; border: 1px solid #e4e3df; border-radius: 12px; padding: 1rem 1.15rem; margin-bottom: .8rem; }
.rd-card h4 { margin: 0 0 .35rem 0; font-size: 1rem; font-weight: 650; }
.rd-card p { margin: 0; color: #5b5a56; line-height: 1.55; font-size: .93rem; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px !important; border-color: #e4e3df !important; }

/* stat tiles */
.rd-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: .75rem; margin: .4rem 0 1rem 0; }
.rd-stat { background: #ffffff; border: 1px solid #e4e3df; border-radius: 12px; padding: .85rem 1rem; }
.rd-stat .l { font-size: .78rem; color: #8a8983; font-weight: 500; }
.rd-stat .v { font-size: 1.6rem; font-weight: 700; color: #1b1b1a; line-height: 1.25; margin-top: .15rem; }
.rd-stat .s { font-size: .8rem; color: #5b5a56; margin-top: .15rem; }
.rd-stat.good .v { color: #1f8a5b; } .rd-stat.bad .v { color: #d24b4b; } .rd-stat.accent .v { color: #2a78d6; }

/* pipeline / stage tracker */
.rd-pipe { display: grid; grid-template-columns: repeat(5, 1fr); gap: .5rem; margin: .4rem 0 1.2rem 0; }
.rd-stage { background: #ffffff; border: 1px solid #e4e3df; border-radius: 12px; padding: .7rem .8rem; position: relative; }
.rd-stage .n { width: 1.55rem; height: 1.55rem; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
               font-size: .78rem; font-weight: 700; background: #efeeea; color: #5b5a56; margin-bottom: .35rem; }
.rd-stage .t { font-weight: 650; font-size: .93rem; color: #1b1b1a; }
.rd-stage .d { font-size: .78rem; color: #8a8983; line-height: 1.35; margin-top: .15rem; }
.rd-stage.done { border-color: #bfe3d2; background: #f3fbf7; } .rd-stage.done .n { background: #1f8a5b; color: #fff; }
.rd-stage.active { border-color: #2a78d6; box-shadow: 0 0 0 3px rgba(42,120,214,.12); } .rd-stage.active .n { background: #2a78d6; color: #fff; }
@media (max-width: 760px) { .rd-pipe { grid-template-columns: repeat(2, 1fr); } }

/* chips and badges */
.rd-chip { display: inline-block; font-size: .76rem; font-weight: 600; padding: .16rem .55rem; border-radius: 999px; margin: 0 .3rem .3rem 0;
           background: #efeeea; color: #5b5a56; border: 1px solid transparent; }
.rd-chip.blue { background: #eaf2fc; color: #1f5fae; } .rd-chip.green { background: #e8f6ef; color: #17724a; }
.rd-chip.red { background: #fcecec; color: #b13a3a; } .rd-chip.amber { background: #fbf3e2; color: #8a5a10; }
.rd-chip.violet { background: #efedfb; color: #4a3aa7; }

/* timeline */
.rd-trial { display: flex; align-items: center; gap: .6rem; margin: 1.3rem 0 .6rem 0; }
.rd-trial .b { background: #1b1b1a; color: #fff; font-size: .75rem; font-weight: 700; padding: .2rem .6rem; border-radius: 999px; }
.rd-trial .x { color: #5b5a56; font-size: .88rem; }
.rd-trial:after { content: ""; flex: 1; height: 1px; background: #e4e3df; }
.rd-evhead { display: flex; align-items: center; gap: .55rem; margin-bottom: .35rem; flex-wrap: wrap; }
.rd-evhead .ic { width: 1.8rem; height: 1.8rem; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-size: .95rem; }
.rd-evhead .tt { font-weight: 650; font-size: .96rem; color: #1b1b1a; }
.rd-evhead .st { color: #8a8983; font-size: .8rem; }
.ic.blue { background: #eaf2fc; color: #1f5fae; } .ic.green { background: #e8f6ef; color: #17724a; } .ic.amber { background: #fbf3e2; color: #8a5a10; }
.ic.violet { background: #efedfb; color: #4a3aa7; } .ic.gray { background: #efeeea; color: #5b5a56; } .ic.red { background: #fcecec; color: #b13a3a; }
.rd-thought { border-left: 3px solid #d7d6d1; padding: .15rem 0 .15rem .75rem; color: #3d3c39; font-size: .92rem; line-height: 1.55; margin: .2rem 0 .5rem 0; }
.rd-kv { font-size: .84rem; color: #5b5a56; margin: .15rem 0; }
.rd-kv b { color: #1b1b1a; font-weight: 600; }
.rd-fail { background: #fdf6f6; border: 1px solid #f3dcdc; border-radius: 10px; padding: .55rem .75rem; margin: .35rem 0; font-size: .86rem; }
.rd-fail .n { font-weight: 600; color: #1b1b1a; } .rd-fail .m { color: #7a3030; }
.rd-fail .x { color: #5b5a56; margin-top: .15rem; } .rd-fail code { font-size: .8rem; background: #fff; }
.rd-bar { height: 8px; background: #efeeea; border-radius: 999px; overflow: hidden; margin: .3rem 0 .25rem 0; }
.rd-bar > div { height: 100%; border-radius: 999px; }
.rd-banner { border-radius: 12px; padding: 1rem 1.2rem; margin: .8rem 0; display: flex; gap: .9rem; align-items: flex-start; }
.rd-banner.good { background: #eef8f3; border: 1px solid #bfe3d2; } .rd-banner.bad { background: #fdf3f3; border: 1px solid #f0cfcf; }
.rd-banner.info { background: #f0f5fc; border: 1px solid #cfe0f6; } .rd-banner.violet { background: #f4f2fd; border: 1px solid #dcd7f5; }
.rd-banner.warn { background: #fdf8ec; border: 1px solid #f0dfb6; }
.rd-banner .t { font-weight: 650; color: #1b1b1a; margin-bottom: .2rem; } .rd-banner .d { color: #3d3c39; font-size: .92rem; line-height: 1.55; }

.rd-ic { font-family: 'Material Symbols Rounded' !important; font-weight: normal; font-style: normal; line-height: 1;
          letter-spacing: normal; text-transform: none; display: inline-block; white-space: nowrap; direction: ltr;
          -webkit-font-feature-settings: 'liga'; font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased;
          font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; vertical-align: middle; }
.rd-banner-ic { line-height: 1; padding-top: .05rem; }
.rd-banner.good .rd-ic { color: #1f8a5b; } .rd-banner.bad .rd-ic { color: #d24b4b; } .rd-banner.info .rd-ic { color: #2a78d6; }
.rd-banner.violet .rd-ic { color: #5b4bc4; } .rd-banner.warn .rd-ic { color: #b7791f; }

/* tour */
.rd-dots { display: flex; gap: .35rem; margin: .2rem 0 1rem 0; }
.rd-dots span { height: 6px; flex: 1; border-radius: 999px; background: #e4e3df; }
.rd-dots span.on { background: #2a78d6; }
.rd-why { background: #f0f5fc; border-radius: 10px; padding: .75rem .9rem; font-size: .9rem; color: #1f3f66; line-height: 1.55; margin-top: .6rem; }
.rd-why b { color: #1f3f66; }

/* per-task grid */
.rd-grid { width: 100%; border-collapse: separate; border-spacing: 4px; font-size: .86rem; }
.rd-grid th { text-align: left; color: #5b5a56; font-weight: 600; font-size: .78rem; padding: .2rem .4rem; }
.rd-grid td { padding: .45rem .55rem; border-radius: 8px; text-align: center; font-weight: 600; }
.rd-grid td.task { text-align: left; background: transparent; color: #1b1b1a; font-weight: 500; }
.rd-grid, .rd-grid tr, .rd-grid th, .rd-grid td { border: none !important; }
.rd-grid tr:nth-child(even) { background: transparent !important; }
.rd-grid th { background: transparent !important; }
.rd-tools, .rd-tools tr, .rd-tools td { border: none !important; background: transparent !important; }
.rd-tools tr + tr td { border-top: 1px solid #efeeea !important; }

/* widgets */
.stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 600; padding: .45rem 1rem; }
[data-testid="stExpander"] details { border-radius: 10px; border-color: #e4e3df; background: #ffffff; }
[data-testid="stExpander"] summary p { font-size: .88rem; font-weight: 500; }
textarea { border-radius: 10px !important; }
[data-baseweb="textarea"], [data-baseweb="textarea"] textarea, [data-baseweb="select"] > div,
[data-baseweb="input"], [data-baseweb="input"] input { background: #ffffff !important; }
[data-baseweb="textarea"], [data-baseweb="select"] > div, [data-baseweb="input"] { border-color: #dcdbd6 !important; border-radius: 10px !important; }
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


_EMOJI = None


def clean(text: object) -> str:
    """House style for anything shown in the dashboard: no em or en dashes, no emoji (model text included)."""
    import re

    global _EMOJI
    if _EMOJI is None:
        _EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
    s = str(text).replace(" \u2014 ", ", ").replace("\u2014", ", ").replace("\u2013", "-")
    return _EMOJI.sub("", s)


def esc(text: object) -> str:
    return html.escape(clean(text))


def rich(text: object) -> str:
    """Escape text, then render `inline code` spans the way markdown would."""
    import re

    return re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(text))


def header(eyebrow: str, title: str, subtitle: str = "") -> None:
    st.markdown(
        f"<div class='rd-eyebrow'>{esc(eyebrow)}</div><div class='rd-title'>{esc(title)}</div>"
        + (f"<div class='rd-sub'>{subtitle}</div>" if subtitle else ""),
        unsafe_allow_html=True,
    )


def h2(text: str) -> None:
    st.markdown(f"<div class='rd-h2'>{esc(text)}</div>", unsafe_allow_html=True)


def stats(items: list[tuple[str, str, str, str]]) -> None:
    """items: (label, value, sub, tone) with tone in {'', 'good', 'bad', 'accent'}."""
    cells = "".join(
        f"<div class='rd-stat {tone}'><div class='l'>{esc(l)}</div><div class='v'>{esc(v)}</div>"
        f"<div class='s'>{esc(s)}</div></div>"
        for l, v, s, tone in items
    )
    st.markdown(f"<div class='rd-stats'>{cells}</div>", unsafe_allow_html=True)


def pipeline_html(active: int | None = None, done: int = 0, compact: bool = False) -> str:
    cells = []
    for i, (name, desc) in enumerate(STAGES):
        cls = "done" if i < done else ("active" if active == i else "")
        mark = icon("check", ".95rem") if i < done else str(i + 1)
        d = "" if compact else f"<div class='d'>{esc(desc)}</div>"
        cells.append(f"<div class='rd-stage {cls}'><div class='n'>{mark}</div><div class='t'>{esc(name)}</div>{d}</div>")
    return f"<div class='rd-pipe'>{''.join(cells)}</div>"


def pipeline(active: int | None = None, done: int = 0, compact: bool = False) -> None:
    st.markdown(pipeline_html(active, done, compact), unsafe_allow_html=True)


def icon(name: str, size: str = "1.15rem") -> str:
    """A Material Symbols line icon (the font Streamlit already ships), never an emoji."""
    return f"<span class='material-symbols-rounded rd-ic' style='font-size:{size}'>{esc(name)}</span>"


def banner(tone: str, title: str, body: str = "", icon_name: str = "") -> None:
    ic = f"<div class='rd-banner-ic'>{icon(icon_name, '1.35rem')}</div>" if icon_name else ""
    st.markdown(
        f"<div class='rd-banner {tone}'>{ic}<div><div class='t'>{esc(title)}</div>"
        f"<div class='d'>{body}</div></div></div>",
        unsafe_allow_html=True,
    )


def chip(text: str, tone: str = "") -> str:
    return f"<span class='rd-chip {tone}'>{esc(text)}</span>"


def card(title: str, body: str) -> str:
    return f"<div class='rd-card'><h4>{esc(title)}</h4><p>{body}</p></div>"


def bar(fraction: float, color: str = BLUE) -> str:
    pct = max(0.0, min(1.0, fraction)) * 100
    return f"<div class='rd-bar'><div style='width:{pct:.1f}%;background:{color}'></div></div>"
