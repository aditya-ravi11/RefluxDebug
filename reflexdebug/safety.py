"""Static AST safety gate.

Every piece of model-written code (solutions, tests and debugger expressions) is parsed and
inspected here before it ever reaches the sandbox. This is the first of two defence layers;
the second is the resource-limited subprocess in ``sandbox.py``. Static checks alone are never a
complete security boundary for Python, which is why both layers exist.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

ALLOWED_MODULES = {
    "abc", "array", "bisect", "calendar", "cmath", "collections", "contextlib", "copy", "csv",
    "dataclasses", "datetime", "decimal", "enum", "fractions", "functools", "graphlib", "heapq",
    "hypothesis", "io", "itertools", "json", "math", "numbers", "operator", "random", "re",
    "statistics", "string", "textwrap", "time", "typing", "unicodedata", "pytest", "solution",
    "numpy", "__future__",
}

BLOCKED_CALLS = {
    "eval", "exec", "compile", "__import__", "open", "input", "breakpoint", "globals",
    "memoryview", "exit", "quit", "help",
}

BLOCKED_ATTRIBUTES = {
    "__subclasses__", "__globals__", "__builtins__", "__bases__", "__base__", "__mro__",
    "__code__", "__closure__", "__getattribute__", "__loader__", "__spec__", "__dict__",
    "__reduce__", "__reduce_ex__", "f_globals", "f_locals", "f_back", "gi_frame", "tb_frame",
    "cr_frame", "co_code", "system", "popen", "spawn", "fork",
}


@dataclass
class SafetyReport:
    ok: bool
    violations: list[str] = field(default_factory=list)
    syntax_error: bool = False

    def __str__(self) -> str:
        if self.ok:
            return "safe"
        return "Blocked by safety gate:\n" + "\n".join(f"  - {v}" for v in self.violations)


class _Checker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def _flag(self, node: ast.AST, msg: str) -> None:
        line = getattr(node, "lineno", "?")
        self.violations.append(f"line {line}: {msg}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_MODULES:
                self._flag(node, f"import of module '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".")[0]
        if node.level and node.level > 0:
            self._flag(node, "relative imports are not allowed")
        elif root not in ALLOWED_MODULES:
            self._flag(node, f"import from module '{node.module}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in BLOCKED_CALLS:
            self._flag(node, f"call to '{func.id}()' is not allowed")
        if isinstance(func, ast.Name) and func.id in {"getattr", "setattr", "delattr", "hasattr"}:
            if len(node.args) >= 2:
                name_arg = node.args[1]
                if not (isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str)):
                    self._flag(node, f"'{func.id}' with a computed attribute name is not allowed")
                elif name_arg.value.startswith("__") or name_arg.value in BLOCKED_ATTRIBUTES:
                    self._flag(node, f"'{func.id}' on '{name_arg.value}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in BLOCKED_ATTRIBUTES:
            self._flag(node, f"access to attribute '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in {"__builtins__", "__loader__", "__spec__"}:
            self._flag(node, f"use of '{node.id}' is not allowed")
        self.generic_visit(node)


def check_code(source: str, mode: str = "exec") -> SafetyReport:
    """Return a SafetyReport for ``source``. ``mode`` is 'exec' for modules, 'eval' for expressions."""
    try:
        tree = ast.parse(source, mode=mode)
    except SyntaxError as exc:
        return SafetyReport(False, [f"line {exc.lineno}: SyntaxError: {exc.msg}"], syntax_error=True)
    checker = _Checker()
    checker.visit(tree)
    return SafetyReport(not checker.violations, checker.violations)
