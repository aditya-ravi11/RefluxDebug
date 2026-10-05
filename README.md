# ReflexDebug: Debugger-Grounded Self-Healing Code Agent

Generative AI Laboratory, Lab CA (Self-healing code: ReAct + Reflexion loops)

**Team:** Aditya Ravi (B2, 16014223004) and Dirshak Deepak Patro (B3, 16014223033)

ReflexDebug takes a natural-language programming task, writes Python for it, runs the code in a sandbox, and
repairs it over several iterations until it works. Most self-healing loops only feed a traceback back to the
model. ReflexDebug adds four things on top of that:

1. **A spec written first.** Before any code exists, the task becomes an executable specification: example tests
   plus Hypothesis property-based tests. The loop can then catch silent logic bugs, not just crashes. The spec is
   validated against a stub, and an independent review pass fixes or removes tests that contradict the task.
2. **Feedback grounded in the debugger.** Every failure comes back with the Hypothesis falsifying example and the
   **local variables of the frame that crashed**. The agent can also evaluate expressions inside that frame
   (`eval_at_crash`), much like a post-mortem debugger.
3. **ReAct tool use with surgical patches.** The agent reasons in Thought / Action / Observation steps. Every
   tool has a required `thought` argument, so the reasoning is never skipped. The tools include a REPL-style
   `run_snippet`, `inspect_failure`, a whitespace-tolerant `apply_patch` (edits that would not parse are refused),
   `rewrite_code`, and `dispute_test`, which is settled by an independent arbiter.
4. **Reflexion with long-term memory.** A trial that fails produces a verbal self-reflection, and that reflection
   seeds the next trial. After each task a reusable lesson is distilled, embedded and stored, so that it can be
   retrieved for future tasks.

A loop guard spots oscillation. It compares an AST-normalised hash of each code state, and watches for the same
error signature repeating and for the same tool call being made twice. Every piece of generated code first passes an AST safety gate, then runs in a
resource-limited, isolated subprocess.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your OPENAI_API_KEY into .env
```

## Usage

```bash
python cli.py demo                                  # offline scripted demo, no key needed
python cli.py solve "Write is_leap(year: int) -> bool ..."   # live agent
python cli.py solve --file task.txt --save results/run.json
python cli.py memory list                           # show long-term lessons
python cli.py check                                 # validate hidden benchmark tests
python cli.py bench                                 # full ablation benchmark (needs a key)
python -m benchmark.mutation_study                  # LLM-free feedback-channel study
python -m benchmark.safety_eval                     # sandbox safety evaluation
python -m benchmark.spec_audit                      # audit synthesised specs against reference solutions
streamlit run app.py                                # web UI
python report/build_report.py                       # regenerate the PDF lab report
pytest                                              # offline test suite
```

## Project structure

```
reflexdebug/
  agent.py       orchestrator: spec -> Reflexion trials -> ReAct loop -> reflection -> lesson
  spec.py        spec synthesis, validation against a stub, vacuity check, self-repair
  tools.py       ReAct tool schemas and implementations, observation formatting
  sandbox.py     isolated subprocess runner with resource limits
  harness.py     in-sandbox test runner: crash-frame locals, Hypothesis examples, post-mortem eval
  safety.py      AST safety gate (import allowlist, blocked builtins and dunder escapes)
  loopguard.py   oscillation and repeated-error detection
  memory.py      Reflexion short-term reflections and long-term embedded lessons
  strategies.py  ablation arms: one_shot, traceback_loop, rich_feedback, reflexdebug
  llm.py         OpenAI wrapper with token and cost accounting, scripted offline LLM
  prompts.py     every prompt used by the system
  demo.py        offline scripted demonstration
benchmark/       14 tasks, hidden tests, reference solutions, ablation runner,
                 mutation study and safety evaluation
report/          PDF report generator and output
tests/           offline pytest suite
cli.py           command line interface
app.py           web UI entry point (Streamlit): pages in views/, design system and timeline renderer in ui/
views/           Start here, Guided tour, Run the agent, Memory, Results, How it works
ui/              theme (colours, typography, cards), timeline renderer, charts, cached data access
```

## Ablation arms

| Arm | Spec | Feedback | Repair | Reflexion + memory |
|-----|------|----------|--------|--------------------|
| One-shot | none | none | none | no |
| Traceback loop | 3 to 5 plain asserts | raw traceback | full rewrite | no |
| Rich feedback | reviewed examples + properties | traceback + locals + falsifying example | full rewrite | no |
| ReflexDebug | reviewed examples + properties | same, plus debugger tools | ReAct tools, patches | yes |

Every arm is scored on **hidden tests** that it never sees.

## Offline results (reproducible without an API key)

| Experiment | Result |
|------------|--------|
| Unit tests | 37 of 37 pass |
| Hidden tests vs reference solutions | 14 of 14 tasks, 99 test cases, all pass |
| Mutation study | 213 mutants, 199 detected (93.4%) |
| Silent logic bugs among detected mutants | 42.7%, and the plain traceback never mentions solution.py for any of them |
| Crash-frame line equals the faulty line | 33.0% of exceptions |
| Shrunk Hypothesis counterexample available | 91.4% of property-test failures |
| Safety gate | 26 of 26 hostile samples blocked, 31 of 31 benign programs accepted |
| Resource abuse (loop, memory bomb, recursion, output flood, exponential work) | 5 of 5 contained, each within 3.3 s |

## Live results (gpt-4o-mini, 20 LLM calls per task, 14 tasks, scored on hidden tests)

| Arm | Solved | Mean hidden pass | LLM calls per task | Total cost (USD) |
|-----|--------|------------------|--------------------|------------------|
| One-shot | 6/14 | 72.9% | 1.0 | 0.003 |
| Traceback loop | 5/14 | 75.6% | 7.2 | 0.030 |
| Rich feedback | 5/14 | 81.6% | 11.1 | 0.063 |
| ReflexDebug (full) | 5/14 | 77.0% | 13.5 | 0.105 |

Every loop raises partial correctness above one-shot, but none solves more tasks outright with this model and
budget. The spec audit (`python -m benchmark.spec_audit`) explains why: self-written specifications often contain
tests that the correct reference solution fails. Evidence-based triage raised the number of fully consistent specs
from 4 to 7 of 14 and cut wasted calls, but only 14 of its 27 amendments were justified. The report discusses this
in detail, together with the v1 and v2 development runs (`results/benchmark_v1.json`, `results/benchmark_v2.json`).

## Report

`report/ReflexDebug_Lab_Report.pdf` is generated by `python report/build_report.py`. It runs the unit tests, the
reference check and the scripted case study, and reads the JSON outputs in `results/`.
