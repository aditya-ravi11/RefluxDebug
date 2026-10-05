"""Matplotlib figures for the lab report. All numbers come from files in results/ or from real runs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.dpi": 200,
})


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def architecture(path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.set_xlim(-4, 100)
    ax.set_ylim(0, 64)
    ax.axis("off")

    def box(x, y, w, h, title, sub, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.6",
                                    linewidth=1.2, edgecolor=color, facecolor=color + "18"))
        ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=8.2, weight="bold", color=INK)
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=6.6, color=INK2)

    def arrow(x1, y1, x2, y2, text="", curve=0.0):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9, color=INK2,
                                     linewidth=1.0, connectionstyle=f"arc3,rad={curve}"))
        if text:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.6, text, ha="center", fontsize=6.3, color=INK2)

    box(1, 50, 18, 10, "Task (NL)", "signature + edge cases", INK2)
    box(25, 50, 22, 10, "Spec Synthesizer", "properties + review + triage", BLUE)
    box(53, 50, 20, 10, "Memory retrieval", "top-k lessons (embeddings)", AQUA)
    box(79, 50, 20, 10, "Coder", "draft solution.py", BLUE)

    box(1, 27, 22, 13, "AST safety gate", "imports, builtins,\ndunder escapes", ORANGE)
    box(29, 27, 22, 13, "Sandbox + harness", "subprocess, CPU/mem/time\nlimits, crash-frame locals", ORANGE)
    box(57, 27, 20, 13, "ReAct debugger", "Thought -> Action ->\nObservation (9 tools)", BLUE)
    box(81, 27, 18, 13, "Loop guard", "AST hash +\nerror signatures", YELLOW)

    box(12, 4, 24, 12, "Reflexion", "self-reflection seeds\nthe next trial", AQUA)
    box(42, 4, 24, 12, "Lesson distillation", "store embedded lesson\nin long-term memory", AQUA)
    box(72, 4, 26, 12, "Output", "best code + trace\n+ cost metrics", INK2)

    arrow(19.5, 55, 24.5, 55)
    arrow(47.5, 55, 52.5, 55)
    arrow(73.5, 55, 78.5, 55)
    arrow(92, 49.5, 92, 40.5)
    ax.text(93, 44.5, "draft", fontsize=6.3, color=INK2)
    arrow(80.5, 33.5, 77.5, 33.5)
    arrow(56.5, 31, 51.5, 31, "edit / probe")
    arrow(28.5, 33.5, 23.5, 33.5)
    arrow(23.5, 37.5, 28.5, 37.5)
    arrow(51.5, 36.5, 56.5, 36.5, "observation")
    arrow(60, 26.5, 30, 16.5)
    ax.text(38, 22.5, "trial failed", fontsize=6.3, color=INK2)
    # next-trial loop: Reflexion -> left margin -> gap between rows -> Coder
    ax.plot([12, -2.5, -2.5, 84], [10, 10, 45, 45], color=INK2, linewidth=1.0)
    arrow(84, 45, 84, 49.5)
    ax.text(40, 46.2, "next trial: reflection + best code so far", ha="center", fontsize=6.3, color=INK2)
    arrow(72, 26.5, 56, 16.5)
    ax.text(66.5, 22.5, "solved / budget", fontsize=6.3, color=INK2)
    arrow(66.5, 10, 71.5, 10)
    return _save(fig, path)


def feedback_channels(summary: dict, path: Path) -> Path:
    labels = [
        "Plain traceback names a line in solution.py",
        "Crash-frame line is the mutated line\n(exceptions only)",
        "Local variables captured for the failure",
        "Shrunk falsifying example available\n(property-test failures)",
    ]
    values = [
        summary["traceback_mentions_solution_pct"],
        summary["crash_line_exact_pct_of_exceptions"],
        summary["locals_captured_pct"],
        summary["falsifying_example_pct_of_property_failures"],
    ]
    fig, ax = plt.subplots(figsize=(6.6, 2.7))
    y = range(len(labels))[::-1]
    ax.barh(list(y), [v * 100 for v in values], color=BLUE, height=0.52)
    for yi, v in zip(y, values):
        ax.text(v * 100 + 1.2, yi, f"{v:.1%}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=7.8, color=INK)
    ax.set_xlim(0, 105)
    ax.set_xlabel("share of detected mutants (%)")
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    return _save(fig, path)


def failure_categories(summary: dict, path: Path) -> Path:
    cats = summary["first_failure_categories"]
    names = {"exception": "Exception raised\ninside solution", "assertion": "Silent logic bug\n(wrong value)",
             "timeout": "Timeout /\nnon-termination", "import": "Import / syntax"}
    keys = [k for k in ("exception", "assertion", "timeout", "import") if cats.get(k)]
    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    bars = ax.bar([names[k] for k in keys], [cats[k] for k in keys], color=[BLUE, ORANGE, YELLOW, INK2][: len(keys)],
                  width=0.55)
    total = sum(cats.values())
    for b, k in zip(bars, keys):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, f"{cats[k]} ({cats[k] / total:.0%})",
                ha="center", fontsize=8.2, color=INK)
    ax.set_ylabel("detected mutants")
    ax.set_ylim(0, max(cats.values()) * 1.2)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=7.8, colors=INK)
    return _save(fig, path)


def healing_curve(points: list[tuple[str, float]], trial_starts: list[int], path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6.2, 2.5))
    xs = list(range(1, len(points) + 1))
    ax.plot(xs, [p[1] * 100 for p in points], color=BLUE, linewidth=2, marker="o", markersize=5)
    for x, (label, v) in zip(xs, points):
        ax.text(x, v * 100 + 6, f"{v:.0%}", ha="center", fontsize=7.8, color=INK)
    for t in trial_starts:
        ax.axvline(t - 0.5, color=GRID, linewidth=1, linestyle="--")
        ax.text(t - 0.42, 4, f"trial {trial_starts.index(t) + 1}", fontsize=7, color=INK2)
    ax.set_xticks(xs)
    ax.set_xticklabels([p[0] for p in points], fontsize=7, color=INK)
    ax.set_ylim(0, 115)
    ax.set_ylabel("spec tests passing (%)")
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    return _save(fig, path)


def strategy_bars(summary: list[dict], key: str, ylabel: str, path: Path, pct: bool = True) -> Path:
    fig, ax = plt.subplots(figsize=(5.8, 2.6))
    labels = [s["label"] for s in summary]
    vals = [s[key] * (100 if pct else 1) for s in summary]
    bars = ax.bar(labels, vals, color=BLUE, width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.01 + (1 if pct else 0),
                f"{v:.0f}%" if pct else f"{v:.4f}", ha="center", fontsize=8.2, color=INK)
    ax.set_ylabel(ylabel)
    if pct:
        ax.set_ylim(0, 110)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=7.8, colors=INK)
    return _save(fig, path)
