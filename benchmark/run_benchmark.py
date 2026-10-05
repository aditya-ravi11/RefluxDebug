"""Ablation benchmark: every strategy on every task, scored on hidden tests.

Examples:
  python -m benchmark.run_benchmark --check-reference
  python -m benchmark.run_benchmark                       # all strategies, all tasks
  python -m benchmark.run_benchmark --strategies one_shot,reflexdebug --tasks semver,calc
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from benchmark.hidden_tests import HIDDEN  # noqa: E402
from benchmark.reference import REFERENCE  # noqa: E402
from benchmark.tasks import TASKS  # noqa: E402
from reflexdebug.config import Settings  # noqa: E402
from reflexdebug.llm import LLM  # noqa: E402
from reflexdebug.memory import ReflexionMemory  # noqa: E402
from reflexdebug.sandbox import Sandbox  # noqa: E402
from reflexdebug.strategies import RUNNERS, STRATEGIES, STRATEGY_LABELS  # noqa: E402

console = Console()
RESULTS = ROOT / "results"


def check_reference() -> bool:
    sandbox = Sandbox(Settings())
    table = Table(title="Reference solutions vs hidden tests")
    for col in ("task", "passed", "total", "status"):
        table.add_column(col)
    ok = True
    for task in TASKS:
        r = sandbox.run_tests(REFERENCE[task["id"]], HIDDEN[task["id"]])
        good = r.all_passed
        ok &= good
        table.add_row(task["id"], str(len(r.passed)), str(r.total), "[green]OK" if good else "[red]FAIL")
    console.print(table)
    return ok


def evaluate_hidden(sandbox: Sandbox, task_id: str, code: str) -> dict:
    if not code.strip():
        return {"hidden_solved": False, "hidden_pass_rate": 0.0, "hidden_passed": 0, "hidden_total": 0}
    r = sandbox.run_tests(code, HIDDEN[task_id])
    total = r.total
    return {
        "hidden_solved": r.all_passed,
        "hidden_pass_rate": round(r.pass_rate, 4),
        "hidden_passed": len(r.passed),
        "hidden_total": total,
        "hidden_failures": [f"{f.test}: {f.error_type}: {f.message[:120]}" for f in r.all_failures()][:6],
    }


def summarise(rows: list[dict]) -> list[dict]:
    out = []
    for strat in STRATEGIES:
        rs = [r for r in rows if r["strategy"] == strat]
        if not rs:
            continue
        n = len(rs)
        solved = sum(r["hidden_solved"] for r in rs)
        verified = sum(r["self_verified"] for r in rs)
        false_conf = sum(r["self_verified"] and not r["hidden_solved"] for r in rs)
        out.append({
            "strategy": strat,
            "label": STRATEGY_LABELS[strat],
            "tasks": n,
            "solved": solved,
            "solve_rate": round(solved / n, 4),
            "mean_hidden_pass_rate": round(sum(r["hidden_pass_rate"] for r in rs) / n, 4),
            "self_verified": verified,
            "false_confidence": false_conf,
            "mean_llm_calls": round(sum(r["usage"]["llm_calls"] for r in rs) / n, 2),
            "mean_tokens": round(sum(r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"] for r in rs) / n),
            "total_cost_usd": round(sum(r["usage"]["cost_usd"] for r in rs), 4),
            "mean_wall_time_s": round(sum(r["wall_time"] for r in rs) / n, 1),
            "mean_iterations": round(sum(r["iterations"] for r in rs) / n, 2),
        })
    return out


def print_summary(summary: list[dict]) -> None:
    table = Table(title="Ablation summary (hidden tests)")
    for col in ("strategy", "solved", "solve rate", "hidden pass", "false conf.", "LLM calls", "tokens", "cost $", "time s"):
        table.add_column(col, justify="right" if col != "strategy" else "left")
    for s in summary:
        table.add_row(s["label"], f"{s['solved']}/{s['tasks']}", f"{s['solve_rate']:.0%}",
                      f"{s['mean_hidden_pass_rate']:.0%}", str(s["false_confidence"]), str(s["mean_llm_calls"]),
                      str(s["mean_tokens"]), f"{s['total_cost_usd']:.4f}", str(s["mean_wall_time_s"]))
    console.print(table)


def run(strategies: list[str], task_ids: list[str], model: str, max_calls: int, out: Path, resume: bool,
        max_steps: int = 6) -> None:
    settings = Settings()
    settings.model = model
    settings.max_llm_calls = max_calls
    settings.max_steps_per_trial = max_steps
    settings.per_test_timeout_s, settings.wall_timeout_s = 2, 20  # hangs are common in buggy drafts; fail fast
    settings.memory_path = RESULTS / "benchmark_memory.json"
    RESULTS.mkdir(exist_ok=True)

    rows: list[dict] = []
    if resume and out.exists():
        rows = json.loads(out.read_text()).get("rows", [])
    elif settings.memory_path.exists():
        settings.memory_path.unlink()
    done = {(r["task"], r["strategy"]) for r in rows}

    memory = ReflexionMemory(settings.memory_path, LLM(settings))
    sandbox = Sandbox(settings)
    tasks = [t for t in TASKS if t["id"] in task_ids]
    started = time.time()

    def one(task: dict, strat: str) -> dict:
        llm = LLM(settings)
        memory.llm = llm if strat == "reflexdebug" else memory.llm
        res = RUNNERS[strat](llm, task["prompt"], settings, memory=memory)
        row = {
            "task": task["id"], "title": task["title"], "strategy": strat, "model": model,
            "self_verified": res.self_verified, "self_pass_rate": res.self_pass_rate,
            "iterations": res.iterations, "usage": res.usage, "wall_time": res.wall_time,
            "spec_tests": res.spec_tests, "error": res.error, "code": res.code, "extra": res.extra,
        }
        row.update(evaluate_hidden(sandbox, task["id"], res.code))
        return row

    for task in tasks:
        todo = [s for s in strategies if (task["id"], s) not in done]
        if not todo:
            continue
        console.rule(f"[bold]{task['id']}[/] {task['title']}")
        with ThreadPoolExecutor(max_workers=len(todo)) as pool:
            futures = {s: pool.submit(one, task, s) for s in todo}
            for strat, fut in futures.items():
                try:
                    row = fut.result()
                except Exception as exc:  # record and continue
                    row = {"task": task["id"], "title": task["title"], "strategy": strat, "model": model,
                           "self_verified": False, "self_pass_rate": 0.0, "iterations": 0,
                           "usage": {"llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                     "embedding_tokens": 0, "cost_usd": 0.0},
                           "wall_time": 0.0, "spec_tests": 0, "error": f"{type(exc).__name__}: {exc}", "code": "",
                           "extra": {}, "hidden_solved": False, "hidden_pass_rate": 0.0,
                           "hidden_passed": 0, "hidden_total": 0}
                rows.append(row)
                mark = "[green]SOLVED" if row["hidden_solved"] else "[red]not solved"
                console.print(f"  {STRATEGY_LABELS[strat]:<20} {mark}[/]  hidden {row['hidden_pass_rate']:.0%}  "
                              f"calls {row['usage']['llm_calls']}  {row['wall_time']}s"
                              + (f"  [yellow]{row['error']}" if row.get("error") else ""))
        summary = summarise(rows)
        out.write_text(json.dumps({"model": model, "max_llm_calls": max_calls, "max_steps": max_steps,
                                   "summary": summary, "rows": rows, "tasks": [t["id"] for t in tasks],
                                   "strategies": strategies}, indent=1))

    summary = summarise(rows)
    out.write_text(json.dumps({"model": model, "max_llm_calls": max_calls, "max_steps": max_steps,
                               "summary": summary, "rows": rows, "tasks": [t["id"] for t in tasks],
                               "strategies": strategies,
                               "elapsed_s": round(time.time() - started, 1)}, indent=1))
    with open(out.with_suffix(".csv"), "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["task", "strategy", "hidden_solved", "hidden_pass_rate", "self_verified", "llm_calls",
                         "prompt_tokens", "completion_tokens", "cost_usd", "wall_time", "iterations"])
        for r in rows:
            writer.writerow([r["task"], r["strategy"], r["hidden_solved"], r["hidden_pass_rate"], r["self_verified"],
                             r["usage"]["llm_calls"], r["usage"]["prompt_tokens"], r["usage"]["completion_tokens"],
                             r["usage"]["cost_usd"], r["wall_time"], r["iterations"]])
    print_summary(summary)
    console.print(f"Saved {out} and {out.with_suffix('.csv')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ReflexDebug ablation benchmark")
    parser.add_argument("--check-reference", action="store_true", help="validate hidden tests with reference solutions")
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    parser.add_argument("--tasks", default=",".join(t["id"] for t in TASKS))
    parser.add_argument("--model", default=Settings().model)
    parser.add_argument("--max-calls", type=int, default=20, help="LLM call budget per task per strategy")
    parser.add_argument("--max-steps", type=int, default=6, help="ReAct steps per Reflexion trial")
    parser.add_argument("--out", default=str(RESULTS / "benchmark.json"))
    parser.add_argument("--resume", action="store_true", help="skip task/strategy pairs already in --out")
    args = parser.parse_args(argv)

    if args.check_reference:
        sys.exit(0 if check_reference() else 1)
    try:
        Settings().require_key()
    except RuntimeError as err:
        console.print(f"[red]{err}[/]")
        sys.exit(1)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = set(strategies) - set(STRATEGIES)
    if unknown:
        parser.error(f"unknown strategies: {unknown}")
    run(strategies, [t.strip() for t in args.tasks.split(",")], args.model, args.max_calls, Path(args.out), args.resume,
        args.max_steps)


if __name__ == "__main__":
    main()
