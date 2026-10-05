"""Execution harness that runs INSIDE the sandboxed subprocess.

It is deliberately standalone (standard library + hypothesis only) and never imports the
reflexdebug package. It loads ``solution.py`` and ``spec_tests.py`` from the working directory,
runs every ``test_*`` function under a per-test alarm, and reports a structured JSON record that
includes the crash-frame local variables of each failure. This "debugger view" is what the agent
reasons over instead of a bare traceback.

Usage: python -I harness.py <workdir> <json-config>
Modes (config["mode"]):
  run      run all tests (or only config["only_test"]) and report results
  eval     re-run config["only_test"] and evaluate config["expr"] inside the crash frame (or, for wrong-value
           failures, in the entry function's frame at its return, recorded by a line tracer)
  trace    re-run config["only_test"] under the line tracer and report the execution trace
  snippet  execute config["code"] with the solution module imported, return captured stdout
"""

import contextlib
import importlib
import inspect
import io
import json
import signal
import sys
import time
import traceback

RESULT_MARKER = "__RD_RESULT__"
MAX_REPR = 240
MAX_LOCALS = 25


class TestTimeout(BaseException):
    """Raised by the alarm handler. Derives from BaseException so Hypothesis does not try to shrink it."""


def _alarm_handler(signum, frame):
    raise TestTimeout("test exceeded its time limit (possible infinite loop or very slow algorithm)")


def _make_repr():
    import reprlib

    r = reprlib.Repr()
    r.maxlevel, r.maxlist, r.maxtuple, r.maxdict, r.maxset = 4, 16, 16, 12, 12
    r.maxstring, r.maxlong, r.maxother = 120, 60, 160
    return r


_REPR = _make_repr()


def safe_repr(value):
    """Bounded repr: never materialises a huge string for large containers."""
    try:
        text = _REPR.repr(value)
    except Exception as exc:  # repr itself can fail on half-built objects
        text = f"<unrepresentable {type(value).__name__}: {exc}>"
    if len(text) > MAX_REPR:
        text = text[: MAX_REPR - 15] + f"...<{len(text)} chars>"
    return text


def snapshot_locals(frame):
    out = {}
    for name, value in list(frame.f_locals.items())[:MAX_LOCALS]:
        if name.startswith("__") or inspect.ismodule(value):
            continue
        out[name] = safe_repr(value)
    return out


def _frames(tb):
    frames = []
    while tb is not None:
        frames.append((tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next
    return frames


def _is_file(frame, name):
    return frame.f_code.co_filename.endswith(name)


def _source_line(path_suffix, lineno):
    try:
        with open(path_suffix, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
    except OSError:
        return ""


def _primary_exception(exc):
    """Hypothesis may raise an ExceptionGroup when several distinct bugs are found."""
    count = 1
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        count = max(count, len(exc.exceptions))
        exc = exc.exceptions[0]
    return exc, count


class ExecutionTracer:
    """Line-level tracer for solution.py (in the spirit of LDB). Records which lines ran, which locals changed,
    and each top-level solution call's locals and value at return. Used only in eval / trace modes."""

    def __init__(self, keep_first=8, keep_last=30):
        import collections

        self.first, self.keep_first = [], keep_first
        self.last = collections.deque(maxlen=keep_last)
        self.steps = 0
        self.prev = {}
        self.last_top = None  # (function, line, locals dict, globals, return repr) of the latest top-level call

    def __call__(self, frame, event, arg):
        if frame.f_code.co_filename.endswith("solution.py"):
            return self._local
        return None

    def _local(self, frame, event, arg):
        if event == "line":
            snap = snapshot_locals(frame)
            prev = self.prev.get(id(frame), {})
            changed = {k: v for k, v in snap.items() if prev.get(k) != v}
            self.prev[id(frame)] = snap
            self.steps += 1
            rec = [frame.f_code.co_name, frame.f_lineno, _source_line("solution.py", frame.f_lineno), changed]
            if len(self.first) < self.keep_first:
                self.first.append(rec)
            self.last.append([self.steps] + rec)
        elif event == "return":
            self.prev.pop(id(frame), None)
            caller = frame.f_back
            if not (caller and caller.f_code.co_filename.endswith("solution.py")):
                self.last_top = (frame.f_code.co_name, frame.f_lineno, dict(frame.f_locals), frame.f_globals,
                                 safe_repr(arg))
        return self._local

    def summary(self):
        out = {"steps": self.steps, "first": self.first, "last": list(self.last), "entry_return": None}
        if self.last_top:
            fn, line, loc, _, ret = self.last_top
            out["entry_return"] = {"function": fn, "line": line, "returned": ret,
                                   "locals": {k: safe_repr(v) for k, v in list(loc.items())[:MAX_LOCALS]
                                              if not k.startswith("__")}}
        return out


def describe_failure(test_name, exc, eval_expr=None, tracer=None):
    primary, group_size = _primary_exception(exc)
    frames = _frames(primary.__traceback__)
    crash = None
    test_frame = None
    for frame, lineno in frames:
        if _is_file(frame, "solution.py"):
            crash = (frame, lineno)
        elif _is_file(frame, "spec_tests.py"):
            test_frame = (frame, lineno)

    tb_lines = []
    for entry in traceback.extract_tb(primary.__traceback__):
        if entry.filename.endswith(("solution.py", "spec_tests.py")):
            short = entry.filename.rsplit("/", 1)[-1]
            tb_lines.append(f'  File "{short}", line {entry.lineno}, in {entry.name}\n    {entry.line}')
    tb_text = "Traceback (most recent call last):\n" + "\n".join(tb_lines)
    tb_text += f"\n{type(primary).__name__}: {primary}"

    record = {
        "test": test_name,
        "error_type": type(primary).__name__,
        "message": str(primary)[:800],
        "traceback": tb_text,
        "notes": [str(n)[:800] for n in getattr(exc, "__notes__", []) or getattr(primary, "__notes__", [])],
        "distinct_failures": group_size,
        "crash_frame": None,
        "test_frame": None,
    }
    if crash:
        frame, lineno = crash
        record["crash_frame"] = {
            "function": frame.f_code.co_name,
            "line": lineno,
            "source": _source_line("solution.py", lineno),
            "locals": snapshot_locals(frame),
        }
    if test_frame:
        frame, lineno = test_frame
        record["test_frame"] = {
            "function": frame.f_code.co_name,
            "line": lineno,
            "source": _source_line("spec_tests.py", lineno),
            "locals": snapshot_locals(frame),
        }
    if tracer is not None:
        record["trace"] = tracer.summary()
    if eval_expr is not None:
        namespace = where = None
        if crash:
            namespace = (dict(crash[0].f_globals), dict(crash[0].f_locals))
            where = "solution.py"
        elif tracer is not None and tracer.last_top:
            # Wrong-value failure: no solution frame is on the stack, so use the entry function's state at return.
            fn, line, loc, glb, _ = tracer.last_top
            namespace = (dict(glb), dict(loc))
            where = f"solution.py {fn}() at its return (line {line})"
        elif test_frame:
            namespace = (dict(test_frame[0].f_globals), dict(test_frame[0].f_locals))
            where = "spec_tests.py"
        if namespace is None:
            record["eval_result"] = "<no frame from solution.py or spec_tests.py available>"
        else:
            try:
                value = eval(eval_expr, namespace[0], namespace[1])  # noqa: S307
                record["eval_result"] = safe_repr(value)
            except Exception as err:
                record["eval_result"] = f"<evaluation raised {type(err).__name__}: {err}>"
        record["eval_frame"] = where
    return record


def configure_hypothesis(max_examples):
    try:
        from hypothesis import HealthCheck, settings
    except ImportError:
        return
    settings.register_profile(
        "reflexdebug",
        max_examples=max_examples,
        derandomize=True,
        database=None,
        deadline=None,
        print_blob=False,
        suppress_health_check=list(HealthCheck),
    )
    settings.load_profile("reflexdebug")


def _expand_parametrize(name, fn):
    """Support @pytest.mark.parametrize without running pytest: expand into (case_name, callable) pairs."""
    import itertools

    marks = [m for m in getattr(fn, "pytestmark", []) if getattr(m, "name", "") == "parametrize"]
    if not marks:
        return [(name, fn)]
    axes = []
    for mark in reversed(marks):  # decorators apply bottom-up
        argnames, argvalues = mark.args[0], list(mark.args[1])
        names = [a.strip() for a in argnames.split(",")] if isinstance(argnames, str) else list(argnames)
        rows = []
        for value in argvalues:
            if type(value).__name__ == "ParameterSet":  # pytest.param(...)
                value = value.values[0] if len(names) == 1 else value.values
            if len(names) == 1:
                rows.append({names[0]: value})
            else:
                rows.append(dict(zip(names, value)))
        axes.append(rows)
    cases = []
    for combo in itertools.product(*axes):
        kwargs = {}
        for part in combo:
            kwargs.update(part)
        label = "-".join(safe_repr(v)[:20] for v in kwargs.values())
        cases.append((f"{name}[{label}]", (lambda f=fn, kw=kwargs: f(**kw))))
    return cases


def collect_tests(module):
    tests = []
    for name, obj in vars(module).items():
        if name.startswith("test_") and callable(obj):
            code = getattr(obj, "__code__", None)
            inner = getattr(obj, "hypothesis", None)
            if code is None and inner is not None:
                code = getattr(getattr(inner, "inner_test", None), "__code__", None)
            tests.append((getattr(code, "co_firstlineno", 10**9), name, obj))
    tests.sort(key=lambda item: item[0])
    cases = []
    for _, name, obj in tests:
        cases.extend(_expand_parametrize(name, obj))
    return cases


def import_module(name):
    try:
        return importlib.import_module(name), None
    except BaseException as exc:  # noqa: BLE001 - we must report everything, including SyntaxError
        if isinstance(exc, SyntaxError):
            return None, {
                "test": f"<import {name}>",
                "error_type": "SyntaxError",
                "message": f"{exc.msg} (line {exc.lineno})",
                "traceback": f"SyntaxError in {name}.py line {exc.lineno}: {exc.msg}\n    {(exc.text or '').rstrip()}",
                "notes": [],
                "distinct_failures": 1,
                "crash_frame": None,
                "test_frame": None,
            }
        rec = describe_failure(f"<import {name}>", exc)
        return None, rec


_CURRENT = {"test": None, "result": None}


def _make_memory_probe():
    """Return a function giving the process's current memory use in MB.

    On macOS, RSS under-reports because the kernel compresses idle pages, so we read phys_footprint (the figure
    Activity Monitor shows) through libproc. On Linux we read the current RSS from /proc.
    """
    import os

    pid = os.getpid()
    if sys.platform == "darwin":
        try:
            import ctypes

            libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
            buf = ctypes.create_string_buffer(512)

            def probe():
                if libproc.proc_pid_rusage(pid, 2, buf) != 0:  # RUSAGE_INFO_V2
                    return 0.0
                footprint = int.from_bytes(buf.raw[72:80], "little")  # ri_phys_footprint
                return footprint / (1024 * 1024)

            probe()
            return probe
        except (OSError, AttributeError):
            pass
    if os.path.exists("/proc/self/statm"):
        page = os.sysconf("SC_PAGE_SIZE")

        def probe():
            with open("/proc/self/statm") as fh:
                return int(fh.read().split()[1]) * page / (1024 * 1024)

        return probe

    import resource

    return lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def _start_memory_watchdog(limit_mb, real_stdout):
    """Some kernels (e.g. macOS) ignore RLIMIT_AS, so a thread enforces the memory cap and reports where it blew up."""
    import os
    import threading

    main_id = threading.main_thread().ident
    probe = _make_memory_probe()

    def watch():
        while True:
            time.sleep(0.02)
            if probe() <= limit_mb:
                continue
            frame = sys._current_frames().get(main_id)
            crash = None
            while frame is not None:
                if _is_file(frame, "solution.py") and crash is None:
                    crash = frame
                frame = frame.f_back
            record = {
                "test": _CURRENT["test"] or "<import solution>",
                "error_type": "MemoryLimitExceeded",
                "message": f"process exceeded the {limit_mb} MB memory limit",
                "traceback": f"MemoryLimitExceeded: process exceeded the {limit_mb} MB memory limit",
                "notes": [], "distinct_failures": 1, "crash_frame": None, "test_frame": None,
            }
            if crash is not None:
                record["crash_frame"] = {
                    "function": crash.f_code.co_name,
                    "line": crash.f_lineno,
                    "source": _source_line("solution.py", crash.f_lineno),
                    "locals": {k: v[:60] for k, v in snapshot_locals(crash).items()},
                }
            result = _CURRENT["result"] or {"passed": [], "failed": [], "import_error": None, "durations": {}}
            payload = {"passed": list(result["passed"]), "failed": list(result["failed"]) + [record],
                       "import_error": result.get("import_error"), "stdout": "", "durations": {}}
            real_stdout.write(RESULT_MARKER + json.dumps(payload))
            real_stdout.flush()
            os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


def run(config):
    per_test_timeout = int(config.get("per_test_timeout", 4))
    only = config.get("only_test")
    eval_expr = config.get("expr") if config.get("mode") == "eval" else None
    use_tracer = config.get("mode") in ("eval", "trace")
    if use_tracer:
        per_test_timeout = per_test_timeout * 3  # tracing slows execution down
    configure_hypothesis(int(config.get("max_examples", 150)))
    signal.signal(signal.SIGALRM, _alarm_handler)

    result = {"passed": [], "failed": [], "import_error": None, "stdout": "", "durations": {}}
    _CURRENT["result"] = result
    if config.get("memory_mb"):
        _start_memory_watchdog(int(config["memory_mb"]), sys.stdout)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        solution, err = import_module("solution")
        if err:
            result["import_error"] = err
        else:
            tests_mod, err = import_module("spec_tests")
            if err:
                err["test"] = "<import spec_tests>"
                result["import_error"] = err
            else:
                budget_end = time.perf_counter() + float(config.get("time_budget", 10**6))
                for name, fn in collect_tests(tests_mod):
                    if only and name != only and name.split("[", 1)[0] != only:
                        continue
                    remaining = budget_end - time.perf_counter()
                    if remaining < 0.3:
                        # Earlier (hanging) tests used up the sandbox budget: report instead of being killed blind.
                        result["failed"].append({
                            "test": name, "error_type": "NotRun",
                            "message": "not run: earlier tests exhausted the sandbox time budget "
                                       "(several tests hit the per-test time limit)",
                            "traceback": "", "notes": [], "distinct_failures": 1,
                            "crash_frame": None, "test_frame": None,
                        })
                        continue
                    start = time.perf_counter()
                    _CURRENT["test"] = name
                    signal.setitimer(signal.ITIMER_REAL, min(per_test_timeout, remaining))
                    tracer = ExecutionTracer() if use_tracer else None
                    try:
                        if tracer is not None:
                            sys.settrace(tracer)
                        fn()
                        sys.settrace(None)
                        result["passed"].append(name)
                    except BaseException as exc:  # noqa: BLE001
                        sys.settrace(None)
                        signal.setitimer(signal.ITIMER_REAL, 0)
                        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                            exc = RuntimeError(f"code raised {type(exc).__name__}")
                        result["failed"].append(describe_failure(name, exc, eval_expr, tracer))
                    finally:
                        sys.settrace(None)
                        signal.setitimer(signal.ITIMER_REAL, 0)
                        result["durations"][name] = round(time.perf_counter() - start, 4)
    result["stdout"] = captured.getvalue()[-2000:]
    if only and not result["passed"] and not result["failed"] and not result["import_error"]:
        result["import_error"] = {
            "test": only, "error_type": "LookupError", "message": f"no test named {only!r}",
            "traceback": "", "notes": [], "distinct_failures": 1, "crash_frame": None, "test_frame": None,
        }
    return result


def snippet(config):
    captured = io.StringIO()
    out = {"stdout": "", "error": None}
    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(int(config.get("per_test_timeout", 4)))
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        try:
            namespace = {"__name__": "__snippet__"}
            import solution as _solution  # trusted: expose every top-level name, including _private helpers

            namespace.update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
            import ast as _ast

            tree = _ast.parse(config["code"])
            last = tree.body.pop() if tree.body and isinstance(tree.body[-1], _ast.Expr) else None
            exec(compile(tree, "<snippet>", "exec"), namespace)  # noqa: S102 - passed the AST gate
            if last is not None:  # behave like a REPL: show the value of a trailing expression
                value = eval(compile(_ast.Expression(last.value), "<snippet>", "eval"), namespace)  # noqa: S307
                if value is not None:
                    print(safe_repr(value))
        except BaseException as exc:  # noqa: BLE001
            out["error"] = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        finally:
            signal.alarm(0)
    out["stdout"] = captured.getvalue()[-3000:]
    return out


def main():
    workdir = sys.argv[1]
    config = json.loads(sys.argv[2])
    sys.path.insert(0, workdir)
    import os

    os.chdir(workdir)
    if config.get("mode") == "snippet":
        payload = snippet(config)
    else:
        payload = run(config)
    sys.stdout.write(RESULT_MARKER + json.dumps(payload))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
