"""Altair charts in the house style: thin marks, recessive axes, direct labels, colour follows the entity."""

from __future__ import annotations

import altair as alt
import pandas as pd

from .theme import ARM_COLORS, BLUE, INK, INK2, LINE


def _axis():
    return dict(labelColor=INK2, titleColor=INK2, gridColor=LINE, domainColor=LINE, tickColor=LINE,
                labelFont="Inter", titleFont="Inter", labelFontSize=12, titleFontSize=12)


def arm_bars(summary: list[dict], field: str, title: str) -> alt.Chart:
    df = pd.DataFrame([{"arm": s["label"], "key": s["strategy"], "value": s[field]} for s in summary])
    order = [s["label"] for s in summary]
    color = alt.Color("key:N", scale=alt.Scale(domain=list(ARM_COLORS), range=list(ARM_COLORS.values())), legend=None)
    base = alt.Chart(df).encode(
        y=alt.Y("arm:N", sort=order, title=None,
                axis=alt.Axis(**_axis(), ticks=False, domain=False, labelLimit=220, labelPadding=8)),
        x=alt.X("value:Q", title=title, scale=alt.Scale(domain=[0, 1.12]),
                axis=alt.Axis(format="%", values=[0, 0.25, 0.5, 0.75, 1], **_axis())),
        tooltip=[alt.Tooltip("arm:N", title="Strategy"), alt.Tooltip("value:Q", title=title, format=".1%")],
    )
    bars = base.mark_bar(cornerRadiusEnd=4, height=22).encode(color=color)
    labels = base.mark_text(align="left", dx=6, font="Inter", fontSize=12, fontWeight=600, color=INK).encode(
        text=alt.Text("value:Q", format=".0%"))
    return (bars + labels).properties(height=170).configure_view(strokeWidth=0)


def healing(points: list[tuple[str, float]]) -> alt.Chart:
    df = pd.DataFrame({"step": [p[0] for p in points], "i": range(len(points)), "value": [p[1] for p in points]})
    base = alt.Chart(df).encode(
        x=alt.X("i:O", title=None, axis=alt.Axis(labelExpr=f"{[p[0] for p in points]}[datum.value]",
                                                   labelAngle=0, **_axis())),
        y=alt.Y("value:Q", title="spec tests passing", scale=alt.Scale(domain=[0, 1.05]),
                axis=alt.Axis(format="%", tickCount=4, **_axis())),
        tooltip=[alt.Tooltip("step:N", title="Point"), alt.Tooltip("value:Q", title="Passing", format=".0%")],
    )
    line = base.mark_line(color=BLUE, strokeWidth=2)
    dots = base.mark_circle(color=BLUE, size=70, opacity=1)
    text = base.mark_text(dy=-12, font="Inter", fontSize=11, color=INK).encode(text=alt.Text("value:Q", format=".0%"))
    return (line + dots + text).properties(height=210).configure_view(strokeWidth=0)
