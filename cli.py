"""ReflexDebug command line interface.

  python cli.py solve "Write is_palindrome(s: str) -> bool that ..."
  python cli.py solve --file task.txt --save results/run.json
  python cli.py demo                      # offline, no API key needed
  python cli.py bench [--strategies ...] [--tasks ...]
  python cli.py check                     # validate hidden benchmark tests
  python cli.py memory list | clear
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from reflexdebug import ReflexDebugAgent, Settings
from reflexdebug.events import Event
from reflexdebug.memory import ReflexionMemory

console = Console()


def _json_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        text = str(v)
        if "\n" in text or len(text) > 70:
            text = text.replace("\n", "\\n")[:70] + "..."
        parts.append(f"{k}={text!r}")
    return ", ".join(parts)


def render(event: Event) -> None:
    d = event.data
    k = event.kind
    if k == "info":
        console.print(f"[dim]> {event.title}[/]")
    elif k == "memory":
        console.print(f"[bold magenta]MEMORY[/] {event.title}")
        for lesson in d.get("lessons", []):
            console.print(f"   [magenta]- ({lesson['score']:.2f}) {lesson['lesson']}[/]")
    elif k == "spec":
        extra = f"  (vacuous: {', '.join(d['vacuous'])})" if d.get("vacuous") else ""
        for r in d.get("review") or []:
            console.print(f"[yellow]Spec review: {r['verdict']} {r['test']}: {r['reason']}[/]")
        console.print(Panel(Syntax(d["tests"], "python", line_numbers=True, word_wrap=True),
                            title=f"[bold]{event.title}[/]{extra}", subtitle=" | ".join(d["functions"]),
                            border_style="cyan"))
    elif k == "trial":
        console.rule(f"[bold]{event.title}")
    elif k == "code":
        console.print(Panel(Syntax(d["code"], "python", line_numbers=True), title=event.title, border_style="blue"))
    elif k == "thought":
        console.print(f"[bold cyan]{event.title}[/]\n[cyan]{d['text']}[/]")
    elif k == "tool":
        console.print(f"[bold yellow]Action:[/] [yellow]{d['name']}({_json_args(d['args'])})[/]")
    elif k == "observation":
        ok = d.get("total") and d.get("passed") == d.get("total")
        console.print(Panel(d["text"], title=event.title, border_style="green" if ok else "red"))
    elif k == "guard":
        console.print(Panel(d["text"], title="Loop guard", border_style="magenta"))
    elif k == "dispute":
        console.print(Panel(f"Test: {d['test']}\nArgument: {d['argument']}\nVerdict: {d['verdict'].upper()}\n"
                            f"Reason: {d['reason']}", title="Test dispute", border_style="yellow"))
    elif k == "reflection":
        console.print(Panel(d["text"], title="Self-reflection (Reflexion)", border_style="bright_blue"))
    elif k == "lesson":
        console.print(f"[bold green]LESSON STORED:[/] {d['lesson']}  [dim]{d.get('tags')}[/]")
    elif k == "done":
        style = "bold green" if d["solved"] else "bold red"
        console.rule(f"[{style}]{event.title}")


def summary_table(result) -> Table:
    table = Table(title="Run summary", show_header=False)
    table.add_column("metric")
    table.add_column("value")
    rows = [
        ("solved (all spec tests)", str(result.solved)),
        ("spec pass rate", f"{result.pass_rate:.0%}"),
        ("trials", str(result.trials)),
        ("ReAct steps", str(result.steps)),
        ("tool usage", ", ".join(f"{k}x{v}" for k, v in result.tool_counts.items()) or "-"),
        ("loop guard triggers", str(result.loop_guard_triggers)),
        ("test disputes", str(len(result.disputes))),
        ("LLM calls", str(result.usage["llm_calls"])),
        ("tokens (prompt / completion)", f"{result.usage['prompt_tokens']} / {result.usage['completion_tokens']}"),
        ("estimated cost (USD)", f"{result.usage['cost_usd']:.5f}"),
        ("wall time (s)", str(result.wall_time)),
    ]
    for r in rows:
        table.add_row(*r)
    return table


def cmd_solve(args) -> None:
    from reflexdebug.llm import LLM

    task = Path(args.file).read_text() if args.file else " ".join(args.task)
    if not task.strip():
        console.print("[red]Provide a task string or --file.")
        sys.exit(2)
    settings = Settings()
    if args.model:
        settings.model = args.model
    settings.max_trials = args.max_trials
    settings.max_steps_per_trial = args.max_steps
    try:
        llm = LLM(settings)
    except RuntimeError as err:
        console.print(f"[red]{err}[/]")
        sys.exit(1)
    agent = ReflexDebugAgent(llm, settings, sink=render, use_memory=not args.no_memory)
    console.print(Panel(task, title=f"Task  (model: {settings.model})", border_style="white"))
    result = agent.solve(task)
    console.print(Panel(Syntax(result.code, "python", line_numbers=True), title="Final solution.py",
                        border_style="green" if result.solved else "red"))
    console.print(summary_table(result))
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(result.to_dict(), indent=1))
        console.print(f"Saved full trace to {args.save}")


def cmd_demo(args) -> None:
    from reflexdebug.demo import DEMO_TASK, demo_llm

    settings = Settings()
    settings.max_steps_per_trial = 3
    llm = demo_llm()
    mem = ReflexionMemory(Path(tempfile.mkdtemp()) / "demo_memory.json", llm)
    console.print(Panel(DEMO_TASK + "\n\n[dim]Offline demo: model replies are pre-recorded, every test run is real.[/]",
                        title="Task (scripted demo)"))
    result = ReflexDebugAgent(llm, settings, memory=mem, sink=render).solve(DEMO_TASK)
    console.print(Panel(Syntax(result.code, "python", line_numbers=True), title="Final solution.py", border_style="green"))
    console.print(summary_table(result))


def cmd_memory(args) -> None:
    settings = Settings()
    mem = ReflexionMemory(settings.memory_path)
    if args.action == "clear":
        mem.clear()
        console.print(f"Cleared {settings.memory_path}")
        return
    table = Table(title=f"Long-term lessons ({settings.memory_path})")
    for col in ("id", "lesson", "tags", "outcome"):
        table.add_column(col)
    for l in mem.lessons:
        table.add_row(l.id, l.lesson, ", ".join(l.tags), l.outcome)
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(prog="reflexdebug", description="Debugger-grounded self-healing code agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("solve", help="solve a natural-language coding task")
    p.add_argument("task", nargs="*")
    p.add_argument("--file")
    p.add_argument("--model")
    p.add_argument("--max-trials", type=int, default=Settings().max_trials)
    p.add_argument("--max-steps", type=int, default=Settings().max_steps_per_trial)
    p.add_argument("--no-memory", action="store_true")
    p.add_argument("--save")
    p.set_defaults(fn=cmd_solve)

    p = sub.add_parser("demo", help="offline scripted demonstration")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("memory", help="inspect or clear long-term memory")
    p.add_argument("action", choices=["list", "clear"])
    p.set_defaults(fn=cmd_memory)

    p = sub.add_parser("bench", help="run the ablation benchmark")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=lambda a: __import__("benchmark.run_benchmark", fromlist=["main"]).main(a.rest))

    p = sub.add_parser("check", help="validate hidden benchmark tests against reference solutions")
    p.set_defaults(fn=lambda a: __import__("benchmark.run_benchmark", fromlist=["main"]).main(["--check-reference"]))

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
