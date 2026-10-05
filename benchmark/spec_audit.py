"""Post-hoc audit of the full agent's benchmark runs (no LLM calls).

1. Spec validity: run each synthesised specification against the task's reference solution. A spec test that the
   reference fails is a wrong test, which pushes the repair loop away from correct code.
2. Repair effect: run the first draft and the final code of each run against the hidden tests.

Run:  python -m benchmark.spec_audit
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.hidden_tests import HIDDEN  # noqa: E402
from benchmark.reference import REFERENCE  # noqa: E402
from reflexdebug.config import Settings  # noqa: E402
from reflexdebug.sandbox import Sandbox  # noqa: E402


def main(path: str = "results/benchmark.json", out_name: str = "spec_audit.json") -> None:
    data = json.loads((ROOT / path).read_text())
    settings = Settings()
    settings.per_test_timeout_s, settings.wall_timeout_s = 2, 20
    sb = Sandbox(settings)
    rows = []
    for r in data["rows"]:
        if r["strategy"] != "reflexdebug":
            continue
        events = (r.get("extra") or {}).get("events") or []
        specs = [e["data"]["tests"] for e in events if e["kind"] == "spec"]
        drafts = [e["data"]["code"] for e in events if e["kind"] == "code" and "trial" in e["data"]]
        rec = {"task": r["task"], "final_hidden": r["hidden_pass_rate"], "final_solved": r["hidden_solved"],
               "self_verified": r["self_verified"]}
        if specs:
            first = sb.run_tests(REFERENCE[r["task"]], specs[0])
            rec["spec_wrong_initial"] = [f.test for f in first.all_failures()]
            ref = sb.run_tests(REFERENCE[r["task"]], specs[-1]) if len(specs) > 1 else first
            rec["spec_tests"] = ref.total
            rec["spec_wrong"] = [f.test for f in ref.all_failures()]
            rec["reference_passes_spec"] = ref.all_passed
            triage = (r.get("extra") or {}).get("spec_triage") or []
            wrong_before = set(rec["spec_wrong_initial"])
            rec["triage"] = [{"test": t["test"], "verdict": t["verdict"], "justified": t["test"] in wrong_before}
                             for t in triage]
        else:
            rec["spec_missing"] = True
        if drafts:
            first = sb.run_tests(drafts[0], HIDDEN[r["task"]])
            rec["first_draft_hidden"] = round(first.pass_rate, 4)
            rec["first_draft_solved"] = first.all_passed
        rows.append(rec)
        print(json.dumps(rec))
    n = len(rows)
    wrong_specs = [x for x in rows if x.get("spec_wrong")]
    summary = {
        "runs": n,
        "specs_consistent_with_reference": sum(x.get("reference_passes_spec", False) for x in rows),
        "spec_tests_total": sum(x.get("spec_tests", 0) for x in rows),
        "spec_tests_wrong": sum(len(x.get("spec_wrong", [])) for x in rows),
        "spec_tests_wrong_before_amendments": sum(len(x.get("spec_wrong_initial", [])) for x in rows),
        "specs_consistent_before_amendments": sum(bool(x.get("spec_tests")) and not x.get("spec_wrong_initial")
                                                  for x in rows),
        "runs_without_spec": sum(bool(x.get("spec_missing")) for x in rows),
        "triage_amendments": sum(len(x.get("triage", [])) for x in rows),
        "triage_justified": sum(t["justified"] for x in rows for t in x.get("triage", [])),
        "first_draft_solved": sum(x.get("first_draft_solved", False) for x in rows),
        "final_solved": sum(x["final_solved"] for x in rows),
        "mean_first_draft_hidden": round(sum(x.get("first_draft_hidden", 0) for x in rows) / (n or 1), 4),
        "mean_final_hidden": round(sum(x["final_hidden"] for x in rows) / (n or 1), 4),
        "repair_improved": sum(x["final_hidden"] > x.get("first_draft_hidden", 0) + 1e-9 for x in rows),
        "repair_hurt": sum(x["final_hidden"] < x.get("first_draft_hidden", 0) - 1e-9 for x in rows),
        "hurt_with_wrong_spec": sum(x["final_hidden"] < x.get("first_draft_hidden", 0) - 1e-9
                                    for x in wrong_specs),
        "tasks_with_wrong_spec": [x["task"] for x in wrong_specs],
    }
    out = ROOT / "results" / out_name
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
