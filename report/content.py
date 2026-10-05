"""Static prose for the lab report. Numbers are NOT written here; build_report.py fills them from results/."""

TITLE = "ReflexDebug: Debugger-Grounded Self-Healing Code Agent"
SUBTITLE = "Generative AI Laboratory, Lab CA"
THEME = "Self-healing code with ReAct (Reason + Act) and Reflexion loops"
AUTHORS = [
    ("Aditya Ravi", "B2", "16014223004"),
    ("Dirshak Deepak Patro", "B3", "16014223033"),
]

AIM = (
    "To design and build a Python agent that takes a programming task written in plain English, writes code for "
    "it, runs that code in a safe sandbox, and keeps repairing it from execution feedback until it is correct. "
    "The agent follows the ReAct and Reflexion patterns and grounds every repair in debugger-level evidence "
    "rather than in the traceback alone."
)

OBJECTIVES = [
    "Build a sandbox that runs untrusted, model-written code with a static safety gate and OS-level resource "
    "limits, and reports failures in structured form.",
    "Turn each task into an executable specification (example tests plus property-based tests) before any code "
    "is written, so that wrong answers are caught, not only crashes.",
    "Capture the local variables of the failing frame and the shrunk counterexample for every failure, and let "
    "the agent query the crashed frame the way a person uses a post-mortem debugger.",
    "Implement a ReAct loop with tool calling (probe, inspect, patch, rewrite, dispute, finish), a loop guard "
    "against oscillation, and Reflexion trials driven by verbal self-reflection.",
    "Keep a long-term memory of debugging lessons, retrieved by embedding similarity for new tasks.",
    "Measure, with experiments that can be reproduced, how much diagnostic information each feedback channel "
    "carries, how safe the sandbox is, and how the full agent compares with simpler baselines.",
]

THEORY = [
    ("Why generated code needs a feedback loop",
     "Large language models write plausible code quickly, but a single sample is often wrong on edge cases: "
     "empty inputs, boundaries, validation rules, operator precedence. People fix such code by running it, reading "
     "the error, forming a hypothesis and trying again. A self-healing agent automates that cycle. The quality of "
     "the loop depends almost entirely on the quality of the feedback: a model can only fix what the feedback "
     "lets it see."),
    ("ReAct: reasoning and acting",
     "ReAct (Yao et al., 2023) interleaves free-text reasoning (Thought) with tool use (Action) and the result of "
     "that tool (Observation). The reasoning trace lets the model plan and update its beliefs; the actions let it "
     "gather facts from the environment instead of guessing. In ReflexDebug, actions are debugging operations on "
     "a live program, and observations are structured test and debugger output."),
    ("Reflexion: learning from failed trials",
     "Reflexion (Shinn et al., 2023) adds a verbal reinforcement signal. After a failed attempt the model writes a "
     "short self-reflection about what went wrong and what to do differently. That reflection is placed into the "
     "context of the next attempt, which acts like an episodic memory without any weight updates. We use it at "
     "two time scales: short-term reflections between trials of one task, and distilled lessons stored across "
     "tasks."),
    ("Self-debugging with execution feedback",
     "Self-Debugging (Chen et al., 2024) showed that models improve when shown execution results of their own "
     "code, and LDB (Zhong et al., 2024) showed that runtime values of intermediate variables help more than the "
     "final error. This project follows the second idea: every failure is reported with the variables of the "
     "frame where it happened, and the agent can evaluate new expressions inside that frame."),
    ("Property-based testing",
     "Example tests check a handful of inputs. Property-based testing, introduced by QuickCheck (Claessen and "
     "Hughes, 2000) and implemented in Python by Hypothesis (MacIver et al., 2019), states a rule that must hold "
     "for all inputs (a round trip, an invariant, agreement with a brute-force oracle) and searches for a "
     "counterexample. When one is found it is shrunk to a minimal failing input, which is exactly the kind of "
     "evidence a debugger wants."),
    ("Sandboxing untrusted code",
     "Model-written code must be treated as untrusted. Static analysis of the syntax tree can reject dangerous "
     "imports and known escape routes, but Python is too dynamic for static checks alone to be a security "
     "boundary. A second layer therefore runs the code in a separate, isolated interpreter process with CPU, "
     "memory, file-size and wall-clock limits."),
]

PROBLEM = (
    "The basic self-healing loop described in the lab brief (generate, execute, capture the traceback, "
    "regenerate) has three weaknesses. First, it only reacts to crashes: code that returns a wrong value raises "
    "nothing, so the loop cannot see the bug at all unless tests exist. Second, a traceback names the line where "
    "an exception surfaced, which is often not the line that is wrong. Third, regenerating the whole program each "
    "time tends to fix one thing and break another, and the loop can oscillate between the same wrong versions. "
    "ReflexDebug addresses each of these with a specific mechanism, summarised below."
)

NOVELTY_ROWS = [
    ("Only crashes are visible", "Spec-first: example tests and Hypothesis properties are synthesised and "
                                 "validated against a stub before code exists"),
    ("Traceback line is not the faulty line", "Crash-frame locals, shrunk counterexamples and an eval_at_crash "
                                              "tool that evaluates expressions inside the failing frame"),
    ("Whole-program rewrites", "apply_patch edits (whitespace-tolerant matching, edits that would not parse are "
                               "rejected); full rewrite only when the design is wrong"),
    ("The spec itself can be wrong", "An independent review before any code is written, and evidence-based "
                                     "triage of failing tests once concrete counterexamples exist"),
    ("Oscillation between wrong versions", "Loop guard on AST-normalised code hashes and repeated error "
                                           "signatures; forces a fresh reflection"),
    ("A wrong test can never be challenged", "dispute_test sends the test, the evidence and the task (never the "
                                             "code) to an independent arbiter"),
    ("Nothing is remembered between tasks", "Reflexion self-reflections within a task and embedded lessons "
                                             "across tasks"),
]

PSEUDOCODE = """procedure REFLEXDEBUG(task T)
    L  <- MEMORY.retrieve(T, k = 3)             # long-term lessons
    S  <- SPEC_SYNTHESIZE(T)                    # examples + Hypothesis properties
    validate S against a stub; self-repair up to 2 times
    S  <- SPEC_REVIEW(T, S)                     # drop / fix tests that contradict T
    (no valid S: return one unverified draft)
    R  <- []                                    # short-term reflections
    for trial t = 1 .. MAX_TRIALS:
        code <- CODER(T, S, L, R, best_code)
        obs  <- SANDBOX.run(code, S)            # gate, isolate, limit, crash-frame locals
        if t = 1 and obs has failures: S <- TRIAGE(T, S, counterexamples); re-run
        if obs.all_pass: break
        for step s = 1 .. MAX_STEPS:
            action(thought, args) <- LLM(REACT_PROMPT, history, TOOLS)
            obs <- EXECUTE(action)              # probe / inspect / patch / dispute ...
            obs <- obs + LOOP_GUARD(code, error_signatures, repeated actions)
            if obs.all_pass or action = finish or guard.stuck: break
        best_code <- argmax over drafts of (all_pass, pass_rate)
        if not solved: R.append(REFLECT(T, trajectory, failures))
    lesson <- DISTIL(T, key events); MEMORY.store(lesson, embed(lesson))
    return best_code"""

MODULES = [
    ("agent.py", "Orchestrator: spec, Reflexion trials, ReAct loop, reflection, lesson distillation; emits an "
                 "event stream consumed by the CLI and the web UI"),
    ("spec.py", "Spec synthesis (JSON mode), validation against a stub, vacuity check, self-repair, "
                "independent review pass, evidence-based triage of failing tests"),
    ("tools.py", "Nine ReAct tools as OpenAI function schemas (each with a required thought argument), "
                 "whitespace-tolerant patching, and the observation formatter"),
    ("sandbox.py", "Temporary directory, isolated interpreter, empty environment, resource limits, timeouts"),
    ("harness.py", "Runs inside the sandbox: per-test alarms, Hypothesis profile, crash-frame capture, "
                   "post-mortem evaluation, memory watchdog, pytest-style parametrize support"),
    ("safety.py", "AST gate: module allowlist, blocked builtins, dunder and frame attribute escapes"),
    ("loopguard.py", "AST-normalised code hashing, repeated error signatures and repeated identical actions"),
    ("memory.py", "Short-term reflections and long-term lessons with embedding retrieval"),
    ("strategies.py", "The four ablation arms behind a common interface"),
    ("llm.py", "OpenAI wrapper with retries, call budget, token and cost accounting; scripted offline model"),
    ("prompts.py", "Every prompt used by the system, in one auditable file"),
]

TOOLS = [
    ("run_tests", "Run the whole specification against the current code"),
    ("inspect_failure", "Full traceback, all captured locals and the falsifying example for one test"),
    ("trace_test", "Re-run a failing test under a line tracer: lines executed, locals that changed at each step, "
                   "and the entry function's return value"),
    ("eval_at_crash", "Evaluate an expression inside solution.py where the exception was raised, or, for "
                      "wrong-value failures, in the entry function's frame at its return"),
    ("run_snippet", "Execute a short probe with every top-level name of the solution available (including "
                    "private helpers); like a REPL, the value of a trailing expression is shown"),
    ("apply_patch", "Replace a snippet that matches once (exactly, or ignoring indentation); edits that would "
                    "not parse are refused; tests re-run automatically"),
    ("rewrite_code", "Replace the whole module when the approach itself is wrong"),
    ("dispute_test", "Ask an independent arbiter to keep, fix or remove a test that contradicts the task"),
    ("finish", "End the trial"),
]

SAFETY_TEXT = (
    "Two independent layers protect the host. Layer 1 parses every solution, test module, probe snippet and "
    "debugger expression and rejects it if it imports a module outside an allowlist (os, sys, subprocess, socket, "
    "shutil, ctypes, importlib, pickle and urllib are all outside it), calls eval, exec, compile, open, "
    "__import__, input or breakpoint, touches attributes used for sandbox escapes (__subclasses__, __globals__, "
    "__mro__, __code__, frame attributes and similar) or calls getattr with a computed or dunder name. Layer 2 "
    "runs whatever passes in a fresh temporary directory with a separate interpreter started in isolated mode "
    "(-I), an empty environment, its own session, and limits on CPU time, file size and core dumps. Each test has "
    "its own alarm inside a time budget for the whole run (tests that cannot be reached are reported as NotRun), "
    "and the process has a hard wall-clock timeout. macOS does not enforce address-space limits, so the "
    "harness also runs a memory watchdog thread that reads the kernel's physical-footprint counter, stops the "
    "process when it passes the limit and reports the exact line that was allocating."
)

ARMS = [
    ("One-shot", "none", "none", "none", "no"),
    ("Traceback loop", "3 to 5 plain asserts", "raw traceback", "full rewrite", "no"),
    ("Rich feedback", "reviewed examples + properties", "traceback, locals, falsifying example", "full rewrite",
     "no"),
    ("ReflexDebug", "reviewed examples + properties", "same, plus debugger tools", "ReAct tools, patches", "yes"),
]

TASK_NOTES = {
    "semver": "pre-release ordering, numeric vs alphanumeric identifiers, strict validation",
    "csv_line": "quote state machine, doubled quotes, text after a closing quote",
    "calc": "precedence, right-associative power, -2**2 = -4, malformed input",
    "path_norm": "'..' at the root, '...' is a name, repeated slashes",
    "intervals": "touching vs adjacent intervals, unsorted input, no mutation",
    "roman": "only canonical numerals are valid (IIII, VX, IC rejected)",
    "isbn": "X only in last position, ignored separators, never raises",
    "flatten": "list indices in paths, empty containers kept as leaves",
    "wrap": "splitting over-long words while keeping the tail on the line",
    "base_conv": "int() accepts '0x', '_', '+' and spaces; the spec forbids them",
    "topo": "lexicographically smallest order, cycle detection, duplicates",
    "duration": "unit order, repeated units, unicode digits",
    "spiral": "single row or column double counting, [[]] and ragged input",
    "rle": "runs longer than 9, digits as data, decode validation",
}

PILOT_INTRO = (
    "We did not tune the agent on the hidden tests. Instead we ran it live, read every step of its traces, and "
    "fixed what the traces showed was broken: first on two hard tasks (strict Roman numerals and the expression "
    "evaluator), then during a first benchmark run (v1) that we stopped after eight tasks once its traces exposed "
    "a design flaw, and finally from an audit of the complete second run (v2). Table 8 lists the {n} changes. They are the most direct evidence we have of how a self-healing "
    "loop behaves with a real model, and the v1 and v2 numbers are reported next to the final ones in Section 10.6."
)

PILOT_FINDINGS = [
    ("Near-miss patches", "The model sent the same apply_patch five times in a row; it never matched because of "
     "indentation and a line-continuation backslash. Fix: whitespace-tolerant, line-level matching that re-indents "
     "the replacement."),
    ("Repeated actions went unnoticed", "The loop guard only watched code states, so repeating a failed action "
     "was invisible to it. Fix: identical tool calls (same tool, same arguments) are now flagged with the result "
     "they produced the first time."),
    ("Reasoning disappeared", "After a few turns gpt-4o-mini stopped writing free-text thoughts next to its tool "
     "calls. Fix: every tool schema has a required thought argument, so the ReAct reasoning trace is always "
     "present and logged."),
    ("Edits that break the syntax", "Patching one line of a multi-line condition produced a SyntaxError and "
     "replaced working code. Fix: an edit that does not parse is refused with the surrounding lines shown, and "
     "the code is left unchanged."),
    ("The specification was wrong", "One synthesised spec asserted that random letter strings are valid Roman "
     "numerals and called from_roman with an integer, so no correct solution could pass. Fix: a minimum number "
     "of single-behaviour tests and an independent review pass that fixes or removes tests that contradict the "
     "task."),
    ("Hangs blinded the whole run", "In the first benchmark attempt a buggy CSV parser looped forever; every test "
     "hit its alarm, the run exceeded the wall-clock limit and was killed, so the agent saw no per-test evidence and "
     "one task took almost ten minutes. Fix: the harness tracks a time budget, shortens the last alarms to fit it, "
     "and reports tests it could not reach as NotRun instead of being killed blind. We restarted the benchmark "
     "from scratch after this fix."),
    ("The debugger was blind to wrong values", "In v1 the agent spent 6 of 13 actions on flatten calling "
     "eval_at_crash for variables such as current_path and always got NameError: for an assertion failure the "
     "failing frame is the test, not the solution. This is the 42.7% silent-bug case from our own mutation study. "
     "Fix: an LDB-style line tracer. trace_test shows the executed lines with changed locals, and eval_at_crash now "
     "evaluates in the entry function's frame at its return."),
    ("Probes could not reach helpers", "run_snippet imported the solution with a star import, which skips "
     "_private helpers, so probing the helper that contained the bug failed. Fix: all top-level names are exposed."),
    ("Reflexion trials repeated themselves", "Trials 2 and 3 produced the same failing draft because the coder "
     "was shown the best code so far and copied it. Fix: later trials write a fresh implementation from the "
     "reflections at a higher temperature, and a draft identical to an earlier failed state is re-sampled."),
    ("Degenerate spec output", "In v1 one spec call produced 16,384 tokens of repetitive text three times, took "
     "almost nine minutes and ended the run. Fix: an output cap on every call; a cut-off reply is rejected without "
     "being fed back, and the spec parser also accepts a test module given as a list of strings."),
    ("Wrong tests survived the review", "The v2 audit (Section 10.7) found that 10 of 14 synthesised specs still "
     "contained at least one test that the reference solution fails, mostly property tests whose generators "
     "produce inputs the task excludes (start > end intervals, ragged matrices, empty keys). A review that only "
     "reads the tests cannot see this. Fix: evidence-based triage. After the first draft runs, the failing tests "
     "and their shrunk counterexamples go to the independent arbiter (without the code), which keeps, fixes or "
     "removes each one. The spec synthesiser also now fails cleanly instead of returning an invalid module."),
    ("Silent probes", "The model called evaluate('2 ** 3') in run_snippet without print and read the empty "
     "output as a bug, wasting four steps. Fix: run_snippet behaves like a REPL and shows the value of a "
     "trailing expression."),
]

MUTATION_METHOD = (
    "A live LLM experiment tells us how well a particular model uses feedback. This experiment asks an earlier, "
    "model-independent question: when code is wrong, how much does each feedback channel actually reveal? We "
    "injected bugs into the 14 reference solutions with classic mutation operators (relational operator swap, "
    "arithmetic operator swap, integer constant off by one, and/or swap), keeping up to 24 mutants per task, and "
    "ran every mutant against the hidden tests in the real sandbox. For each detected mutant we recorded what a "
    "repair loop would be shown."
)

DISCUSSION = [
    ("Silent bugs are common, and a traceback does not see them",
     "Across the detected mutants, {silent} showed up as a wrong value with no exception at all. For every one of "
     "those, the plain traceback pointed only at the test's assert statement and never mentioned solution.py. A "
     "loop that reacts to crashes alone cannot find these bugs, and a loop that shows only tracebacks gives the "
     "model no location to start from. This is why the specification is written first, why it includes property "
     "tests, and why the final agent traces wrong-value failures line by line."),
    ("The line in a traceback is usually not the faulty line",
     "Even when an exception was raised inside the solution, the crash-frame line matched the mutated line in only "
     "{exact} of cases. A wrong comparison upstream often surfaces as a ValueError or IndexError several lines "
     "later, so evidence tools are needed before patching."),
    ("Repair raised partial correctness, not the number of solved tasks",
     "On the live benchmark every feedback loop raised the mean hidden pass rate above one-shot generation "
     "({one_hidden} for one-shot against {tb_hidden}, {rich_hidden} and {rd_hidden} for the three loops), but none "
     "solved more tasks outright ({one_solved} for one-shot, {tb_solved}, {rich_solved} and {rd_solved} for the "
     "loops). With gpt-4o-mini and 20 calls, the loops mostly turn half-right code into mostly-right code. Tasks "
     "that the model gets wrong conceptually (the expression evaluator, the strict ISBN rules) stayed wrong under "
     "every strategy."),
    ("The self-written specification is the bottleneck",
     "The audit in Section 10.7 shows why. In the v2 run, 10 of 14 synthesised specifications contained at least one "
     "test that the correct reference solution fails. A loop that trusts such a spec can never accept correct "
     "code, so it keeps editing until the budget runs out: in v2 the full agent spent {v2_calls} calls per task on "
     "average even on tasks its first draft had already solved. Evidence-based triage raised the number of fully "
     "consistent specs from {v2_consistent} to {final_consistent} of 14, cut the average to {final_calls} calls and "
     "the total cost from {v2_cost} to {final_cost} USD, and the share of runs in which repair improved the hidden "
     "result went from {v2_improved} to {final_improved}, with no run made worse in either version."),
    ("The arbiter is only as good as the model behind it",
     "Triage has a price. Only {triage_just} of the {triage_total} tests it amended were really wrong; the rest were "
     "correct tests that gpt-4o-mini blamed for the code's failure, for example three valid example tests on the "
     "expression evaluator. Every wrongly removed test weakens the specification and can create false confidence. "
     "A stronger model as arbiter, or requiring several independent drafts to fail a test before it may be "
     "amended, are the obvious next steps."),
    ("Rich evidence helped most when paired with simple edits",
     "The rich-feedback arm, which sees the same counterexamples and crash-frame locals but simply rewrites the "
     "whole module, reached the highest hidden pass rate at about half the cost of the full agent. The traces "
     "explain this: with the tracer the small model usually found the right evidence (for flatten the trace showed "
     "the empty list being skipped), but it often applied the fix in the wrong branch. For a small model, rich "
     "observations matter more than a large action space."),
]

LIMITATIONS = [
    "Each arm ran once per task with one model (gpt-4o-mini) and a budget of 20 calls. Model sampling is not "
    "deterministic, so differences of one task between arms are within run-to-run noise; several seeds and a "
    "stronger model would be needed for firm conclusions.",
    "The benchmark has 14 function-level tasks. It is designed to be tricky rather than large, so the results are a "
    "focused ablation, not a general leaderboard.",
    "The design was improved between runs using the traces of earlier runs (Section 10.4). We never looked at the "
    "hidden tests while doing this, but the final version was still shaped by experience on the same 14 tasks.",
    "The synthesised specification can be wrong, and the arbiter that corrects it is right only about half the "
    "time with this model. Hidden tests are used for evaluation precisely because self-verification is not "
    "trustworthy.",
    "The AST gate is a blocklist plus an allowlist, not a proof of safety; that is why the process layer exists. "
    "A production system should add a container or an OS sandbox profile with no network access.",
    "The memory watchdog samples every 20 ms, so a very fast allocation can briefly overshoot the limit. Output "
    "floods are held in memory and are stopped by the memory limit rather than by a dedicated output cap.",
    "Cost figures are estimates from published per-token prices.",
]

CONCLUSION = (
    "ReflexDebug turns the basic generate, run, repair loop into an agent that writes its tests first, reads "
    "program state when something fails, edits surgically, notices when it is going in circles, reflects on failed "
    "trials and carries lessons forward. The offline experiments show why each mechanism exists: almost half of "
    "real bugs are silent, the traceback line is usually not the faulty line, and shrunk counterexamples are "
    "available for nearly every property failure. The sandbox blocked every hostile sample in our corpus without "
    "rejecting any legitimate code. The live experiments give a more sober picture than we expected. With a small "
    "model and a tight budget, feedback loops raise partial correctness but do not solve more tasks than a single "
    "sample, and the quality of the self-written specification decides how much the loop can achieve. Measuring "
    "that directly, by testing each specification against a known-correct solution, was the most useful thing we "
    "built: it explained the benchmark results, guided the triage mechanism, and showed exactly where the next "
    "improvement has to come from."
)

FUTURE = [
    "A stronger model (or a panel of models) as the spec arbiter, and amending a test only when several independent "
    "drafts fail it.",
    "An adaptive controller that switches between whole-module rewrites and surgical patches depending on how "
    "localised the evidence is.",
    "Repeat the ablation with several seeds and a stronger model to separate method effects from sampling noise.",
    "Tree search over repair candidates (in the style of LATS) instead of a single trajectory per trial.",
    "Score synthesised specs automatically with the mutation harness, so weak specs are detected before repair.",
    "Run the sandbox in a container with no network namespace, and add an explicit output cap.",
]

REFERENCES = [
    "S. Yao, J. Zhao, D. Yu, N. Du, I. Shafran, K. Narasimhan, Y. Cao. ReAct: Synergizing Reasoning and Acting in "
    "Language Models. ICLR 2023.",
    "N. Shinn, F. Cassano, A. Gopinath, K. Narasimhan, S. Yao. Reflexion: Language Agents with Verbal "
    "Reinforcement Learning. NeurIPS 2023.",
    "X. Chen, M. Lin, N. Schaerli, D. Zhou. Teaching Large Language Models to Self-Debug. ICLR 2024.",
    "L. Zhong, Z. Wang, J. Shang. Debug like a Human: A Large Language Model Debugger via Verifying Runtime "
    "Execution Step by Step (LDB). Findings of ACL 2024.",
    "A. Zhou, K. Yan, M. Shlapentokh-Rothman, H. Wang, Y. Wang. Language Agent Tree Search Unifies Reasoning, "
    "Acting, and Planning in Language Models (LATS). ICML 2024.",
    "B. Chen, F. Zhang, A. Nguyen, D. Zan, Z. Lin, J. Lou, W. Chen. CodeT: Code Generation with Generated Tests. "
    "ICLR 2023.",
    "K. Claessen, J. Hughes. QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs. ICFP 2000.",
    "D. R. MacIver, Z. Hatfield-Dodds, et al. Hypothesis: A new approach to property-based testing. Journal of "
    "Open Source Software 4(43), 2019.",
    "Y. Jia, M. Harman. An Analysis and Survey of the Development of Mutation Testing. IEEE Transactions on "
    "Software Engineering 37(5), 2011.",
    "OpenAI. Function calling and Embeddings API documentation. platform.openai.com/docs, accessed 2026.",
]
