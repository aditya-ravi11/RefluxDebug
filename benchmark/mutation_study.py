"""LLM-free mutation study: how much diagnostic information does each feedback channel carry?

Bugs are injected into the reference solutions with classic mutation operators (relational operator swap,
arithmetic operator swap, constant off-by-one, boolean operator swap). Each mutant runs against the hidden tests
in the sandbox. For every mutant that is detected (at least one failing test) we record what the agent would see:

  * does the plain traceback mention solution.py at all (the only location signal of a traceback-only loop)?
  * does the crash frame point at the exact mutated line (fault localisation)?
  * are local variables captured for the failing frame?
  * does a property-test failure come with a shrunk Hypothesis falsifying example?

Run:  python -m benchmark.mutation_study
"""

from __future__ import annotations

import ast
import copy
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.hidden_tests import HIDDEN  # noqa: E402
from benchmark.reference import REFERENCE  # noqa: E402
from benchmark.tasks import TASKS  # noqa: E402
from reflexdebug.config import Settings  # noqa: E402
from reflexdebug.sandbox import Sandbox  # noqa: E402

MAX_MUTANTS_PER_TASK = 24

SWAP_CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
SWAP_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.FloorDiv: ast.Div, ast.Div: ast.FloorDiv, ast.Mult: ast.Add}
SWAP_BOOL = {ast.And: ast.Or, ast.Or: ast.And}


def mutation_sites(tree: ast.AST) -> list[tuple[str, int, int]]:
    """Return (operator, node index, line) for every mutable site, in a deterministic walk order."""
    sites = []
    for idx, node in enumerate(ast.walk(tree)):
        if isinstance(node, ast.Compare) and type(node.ops[0]) in SWAP_CMP:
            sites.append(("relational", idx, node.lineno))
        elif isinstance(node, ast.BinOp) and type(node.op) in SWAP_BIN:
            sites.append(("arithmetic", idx, node.lineno))
        elif isinstance(node, ast.BoolOp) and type(node.op) in SWAP_BOOL:
            sites.append(("boolean", idx, node.lineno))
        elif (isinstance(node, ast.Constant) and type(node.value) is int and 0 <= node.value <= 10
              and not isinstance(getattr(node, "parent", None), ast.Subscript)):
            sites.append(("constant", idx, node.lineno))
    return sites


def apply_mutation(source: str, kind: str, target: int) -> str:
    tree = ast.parse(source)
    for idx, node in enumerate(ast.walk(tree)):
        if idx != target:
            continue
        if kind == "relational":
            node.ops[0] = SWAP_CMP[type(node.ops[0])]()
        elif kind == "arithmetic":
            node.op = SWAP_BIN[type(node.op)]()
        elif kind == "boolean":
            node.op = SWAP_BOOL[type(node.op)]()
        elif kind == "constant":
            node.value = node.value + 1
        break
    return ast.unparse(tree) + "\n"


def pick(sites: list, k: int) -> list:
    if len(sites) <= k:
        return sites
    step = len(sites) / k
    return [sites[int(i * step)] for i in range(k)]


def analyse(task_id: str, sandbox: Sandbox) -> list[dict]:
    source = ast.unparse(ast.parse(REFERENCE[task_id])) + "\n"  # normalise line numbers
    tree = ast.parse(source)
    records = []
    for kind, idx, line in pick(mutation_sites(tree), MAX_MUTANTS_PER_TASK):
        mutant = apply_mutation(copy.copy(source), kind, idx)
        if mutant == source:
            continue
        result = sandbox.run_tests(mutant, HIDDEN[task_id])
        failures = result.all_failures()
        rec = {"task": task_id, "operator": kind, "line": line, "detected": bool(failures) or result.killed,
               "failures": []}
        for f in failures:
            mentions_solution = "solution.py" in f.traceback
            crash = f.crash_frame or {}
            rec["failures"].append({
                "test": f.test,
                "error_type": f.error_type,
                "category": ("timeout" if f.error_type in {"TestTimeout", "SandboxKilled"}
                             else "import" if f.test.startswith("<")
                             else "assertion" if f.error_type == "AssertionError" and not crash
                             else "exception"),
                "traceback_mentions_solution": mentions_solution,
                "crash_line_exact": crash.get("line") == line,
                "locals_captured": bool((crash.get("locals") or {}) or ((f.test_frame or {}).get("locals") or {})),
                "has_falsifying_example": any("Falsifying" in n or "Failing test case" in n for n in f.notes),
                "is_property_test": bool(f.notes) or "round_trip" in f.test or "covers" in f.test,
            })
        records.append(rec)
    return records


def summarise(records: list[dict]) -> dict:
    detected = [r for r in records if r["detected"]]
    firsts = [r["failures"][0] for r in detected if r["failures"]]
    allf = [f for r in detected for f in r["failures"]]
    cats = Counter(f["category"] for f in firsts)
    n = len(firsts) or 1
    exc = [f for f in firsts if f["category"] == "exception"]
    prop = [f for f in allf if f["is_property_test"]]
    per_task = {}
    for t in TASKS:
        rs = [r for r in records if r["task"] == t["id"]]
        if rs:
            per_task[t["id"]] = {"mutants": len(rs), "detected": sum(r["detected"] for r in rs)}
    return {
        "mutants": len(records),
        "detected": len(detected),
        "mutation_score": round(len(detected) / (len(records) or 1), 4),
        "first_failure_categories": dict(cats),
        "traceback_mentions_solution_pct": round(sum(f["traceback_mentions_solution"] for f in firsts) / n, 4),
        "silent_logic_bug_pct": round(cats.get("assertion", 0) / n, 4),
        "locals_captured_pct": round(sum(f["locals_captured"] for f in firsts) / n, 4),
        "crash_line_exact_pct_of_exceptions": round(sum(f["crash_line_exact"] for f in exc) / (len(exc) or 1), 4),
        "property_failures": len(prop),
        "falsifying_example_pct_of_property_failures": round(
            sum(f["has_falsifying_example"] for f in prop) / (len(prop) or 1), 4),
        "operators": dict(Counter(r["operator"] for r in records)),
        "per_task": per_task,
    }


def main() -> None:
    settings = Settings()
    settings.per_test_timeout_s = 2
    sandbox = Sandbox(settings)
    with ThreadPoolExecutor(max_workers=6) as pool:
        chunks = list(pool.map(lambda t: analyse(t["id"], sandbox), TASKS))
    records = [r for chunk in chunks for r in chunk]
    summary = summarise(records)
    out = ROOT / "results" / "mutation_study.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "records": records}, indent=1))
    print(json.dumps(summary, indent=1))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
