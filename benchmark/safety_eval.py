"""Evaluates the two sandbox defence layers on a corpus of hostile and benign programs.

Layer 1 (static AST gate) should block every hostile sample and accept every benign one.
Layer 2 (resource-limited subprocess) is exercised with resource-abuse programs that are *allowed* by the gate
(infinite loops, memory bombs, deep recursion, output floods) and must be contained without harming the host.

Run:  python -m benchmark.safety_eval
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.hidden_tests import HIDDEN  # noqa: E402
from benchmark.reference import REFERENCE  # noqa: E402
from reflexdebug.config import Settings  # noqa: E402
from reflexdebug.demo import BUGGY, DEMO_TESTS, FIXED  # noqa: E402
from reflexdebug.safety import check_code  # noqa: E402
from reflexdebug.sandbox import Sandbox  # noqa: E402

HOSTILE = {
    "os.system shell": "import os\nos.system('echo hi')",
    "subprocess": "import subprocess\nsubprocess.run(['ls'])",
    "from-import os": "from os import remove\nremove('x')",
    "shutil rmtree": "import shutil\nshutil.rmtree('/tmp/x')",
    "socket exfiltration": "import socket\ns = socket.socket()",
    "urllib network": "import urllib.request\nurllib.request.urlopen('http://example.com')",
    "ctypes": "import ctypes",
    "importlib": "import importlib\nimportlib.import_module('os')",
    "__import__": "m = __import__('os')",
    "eval": "eval('1+1')",
    "exec": "exec('x = 1')",
    "compile": "code = compile('1', 'f', 'eval')",
    "open write": "open('f.txt', 'w').write('x')",
    "open read": "print(open('/etc/passwd').read())",
    "subclasses escape": "().__class__.__bases__[0].__subclasses__()",
    "mro escape": "object.__mro__",
    "globals via function": "def f():\n    pass\nf.__globals__['x'] = 1",
    "builtins dict": "__builtins__['eval']('1')",
    "getattr dunder": "getattr((), '__class__')",
    "getattr computed": "name = '__cla' + 'ss__'\ngetattr((), name)",
    "frame walk": "def g():\n    pass\nx = g.__code__",
    "sys module": "import sys\nsys.modules['os']",
    "pickle": "import pickle\npickle.loads(b'')",
    "relative import": "from . import secrets",
    "breakpoint": "breakpoint()",
    "input": "input()",
}

RESOURCE_ABUSE = {
    "infinite loop": ("def f():\n    while True:\n        pass\n", "from solution import f\n\ndef test_x():\n    f()\n"),
    "memory bomb": ("def f():\n    x = []\n    while True:\n        x.append(' ' * 10**7)\n",
                    "from solution import f\n\ndef test_x():\n    f()\n"),
    "deep recursion": ("def f(n):\n    return f(n + 1)\n", "from solution import f\n\ndef test_x():\n    f(0)\n"),
    "output flood": ("def f():\n    while True:\n        print('x' * 1000)\n",
                     "from solution import f\n\ndef test_x():\n    f()\n"),
    "exponential work": ("def f(n):\n    return 1 if n < 2 else f(n - 1) + f(n - 2)\n",
                         "from solution import f\n\ndef test_x():\n    assert f(60) > 0\n"),
}


def main() -> None:
    hostile = {name: not check_code(src).ok for name, src in HOSTILE.items()}
    benign_sources = {f"reference:{k}": v for k, v in REFERENCE.items()}
    benign_sources |= {f"hidden_tests:{k}": v for k, v in HIDDEN.items()}
    benign_sources |= {"demo:buggy": BUGGY, "demo:fixed": FIXED, "demo:tests": DEMO_TESTS}
    benign = {name: check_code(src).ok for name, src in benign_sources.items()}

    settings = Settings()
    settings.per_test_timeout_s = 3
    sandbox = Sandbox(settings)
    abuse = {}
    for name, (code, tests) in RESOURCE_ABUSE.items():
        start = time.perf_counter()
        r = sandbox.run_tests(code, tests)
        fail = (r.all_failures() or [None])[0]
        abuse[name] = {
            "contained": not r.all_passed,
            "reported_as": fail.error_type if fail else "none",
            "seconds": round(time.perf_counter() - start, 2),
        }

    summary = {
        "hostile_samples": len(hostile),
        "hostile_blocked": sum(hostile.values()),
        "benign_samples": len(benign),
        "benign_accepted": sum(benign.values()),
        "resource_abuse_samples": len(abuse),
        "resource_abuse_contained": sum(v["contained"] for v in abuse.values()),
    }
    out = ROOT / "results" / "safety_eval.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "hostile": hostile, "benign": benign, "abuse": abuse}, indent=1))
    print(json.dumps(summary, indent=1))
    print(json.dumps(abuse, indent=1))
    missed = [k for k, v in hostile.items() if not v]
    rejected = [k for k, v in benign.items() if not v]
    if missed:
        print("NOT BLOCKED:", missed)
    if rejected:
        print("FALSE POSITIVES:", rejected)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
