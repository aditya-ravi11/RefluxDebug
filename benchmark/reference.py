"""Reference solutions. Used ONLY to validate the hidden tests (python run_benchmark.py --check-reference)."""

REFERENCE = {}

REFERENCE["semver"] = r'''
import re

_IDENT = re.compile(r"^[0-9A-Za-z-]+$")


def _num(part):
    if not part.isdigit() or (len(part) > 1 and part[0] == "0"):
        raise ValueError(part)
    return int(part)


def _parse(v):
    if not isinstance(v, str):
        raise ValueError(v)
    core, _, build = v.partition("+")
    if "+" in v and (not build or any(not _IDENT.match(x) for x in build.split("."))):
        raise ValueError(v)
    core, dash, pre = core.partition("-")
    parts = core.split(".")
    if len(parts) != 3:
        raise ValueError(v)
    nums = tuple(_num(p) for p in parts)
    ids = []
    if dash:
        for ident in pre.split("."):
            if not ident or not _IDENT.match(ident):
                raise ValueError(v)
            if ident.isdigit():
                ids.append((0, _num(ident), ""))
            else:
                ids.append((1, 0, ident))
    return nums, ids


def compare_versions(a, b):
    na, pa = _parse(a)
    nb, pb = _parse(b)
    if na != nb:
        return -1 if na < nb else 1
    if not pa and not pb:
        return 0
    if not pa:
        return 1
    if not pb:
        return -1
    for x, y in zip(pa, pb):
        if x != y:
            return -1 if x < y else 1
    if len(pa) == len(pb):
        return 0
    return -1 if len(pa) < len(pb) else 1
'''

REFERENCE["csv_line"] = r'''
def parse_csv_line(line):
    fields, i, n = [], 0, len(line)
    while True:
        if i < n and line[i] == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise ValueError("unterminated quote")
                if line[i] == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(line[i])
                i += 1
            fields.append("".join(buf))
            if i == n:
                return fields
            if line[i] != ",":
                raise ValueError("text after closing quote")
            i += 1
        else:
            j = line.find(",", i)
            if j == -1:
                fields.append(line[i:])
                return fields
            fields.append(line[i:j])
            i = j + 1
'''

REFERENCE["calc"] = r'''
import re

_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|(\*\*|[-+*/()]))")


def _tokens(expr):
    pos, out = 0, []
    expr = expr.rstrip()
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError("bad character")
        out.append(("num", float(m.group(1))) if m.group(1) else ("op", m.group(2)))
        pos = m.end()
    return out


def evaluate(expr):
    toks = _tokens(expr)
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else (None, None)

    def take():
        nonlocal pos
        tok = peek()
        pos += 1
        return tok

    def expr_():
        val = term()
        while peek() in (("op", "+"), ("op", "-")):
            op = take()[1]
            rhs = term()
            val = val + rhs if op == "+" else val - rhs
        return val

    def term():
        val = unary()
        while peek() in (("op", "*"), ("op", "/")):
            op = take()[1]
            rhs = unary()
            if op == "*":
                val *= rhs
            else:
                if rhs == 0:
                    raise ZeroDivisionError("division by zero")
                val /= rhs
        return val

    def unary():
        if peek() in (("op", "+"), ("op", "-")):
            op = take()[1]
            v = unary()
            return -v if op == "-" else v
        return power()

    def power():
        base = atom()
        if peek() == ("op", "**"):
            take()
            exp = unary()
            return base ** exp
        return base

    def atom():
        kind, val = take()
        if kind == "num":
            return val
        if (kind, val) == ("op", "("):
            v = expr_()
            if take() != ("op", ")"):
                raise ValueError("expected )")
            return v
        raise ValueError("unexpected token")

    if not toks:
        raise ValueError("empty")
    result = expr_()
    if pos != len(toks):
        raise ValueError("trailing tokens")
    return float(result)
'''

REFERENCE["path_norm"] = r'''
def normalize_path(path):
    if not path.startswith("/"):
        raise ValueError(path)
    stack = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if stack:
                stack.pop()
        else:
            stack.append(part)
    return "/" + "/".join(stack)
'''

REFERENCE["intervals"] = r'''
def merge_intervals(intervals):
    items = sorted(tuple(i) for i in intervals)
    for s, e in items:
        if s > e:
            raise ValueError((s, e))
    out = []
    for s, e in items:
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
'''

REFERENCE["roman"] = r'''
_PAIRS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _to_roman(n):
    out = []
    for v, sym in _PAIRS:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def from_roman(s):
    if not isinstance(s, str) or not s or any(ch not in _VALUES for ch in s):
        raise ValueError(s)
    total = 0
    for i, ch in enumerate(s):
        v = _VALUES[ch]
        if i + 1 < len(s) and _VALUES[s[i + 1]] > v:
            total -= v
        else:
            total += v
    if not 1 <= total <= 3999 or _to_roman(total) != s:
        raise ValueError(s)
    return total
'''

REFERENCE["isbn"] = r'''
def is_valid_isbn(s):
    if not isinstance(s, str):
        return False
    t = s.replace("-", "").replace(" ", "")
    if len(t) == 10:
        if not t[:9].isdigit() or not (t[9].isdigit() or t[9] in "Xx"):
            return False
        if not all(c.isascii() for c in t):
            return False
        vals = [int(c) for c in t[:9]] + [10 if t[9] in "Xx" else int(t[9])]
        return sum((10 - i) * v for i, v in enumerate(vals)) % 11 == 0
    if len(t) == 13:
        if not (t.isascii() and t.isdigit()):
            return False
        return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(t)) % 10 == 0
    return False
'''

REFERENCE["flatten"] = r'''
def flatten(obj):
    out = {}

    def walk(value, prefix):
        if isinstance(value, dict):
            if not value and prefix:
                out[prefix] = {}
            for k, v in value.items():
                walk(v, f"{prefix}.{k}" if prefix else str(k))
        elif isinstance(value, list):
            if not value:
                out[prefix] = []
            for i, v in enumerate(value):
                walk(v, f"{prefix}.{i}" if prefix else str(i))
        else:
            out[prefix] = value

    walk(obj, "")
    return out
'''

REFERENCE["wrap"] = r'''
def wrap(text, width):
    if width < 1:
        raise ValueError(width)
    lines, cur = [], ""
    for word in text.split():
        if len(word) > width:
            if cur:
                lines.append(cur)
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            cur = word
            continue
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines
'''

REFERENCE["base_conv"] = r'''
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _check(base):
    if not isinstance(base, int) or not 2 <= base <= 36:
        raise ValueError(base)


def to_base(n, base):
    _check(base)
    if n == 0:
        return "0"
    sign, n = ("-", -n) if n < 0 else ("", n)
    out = []
    while n:
        n, r = divmod(n, base)
        out.append(_DIGITS[r])
    return sign + "".join(reversed(out))


def from_base(s, base):
    _check(base)
    if not isinstance(s, str):
        raise ValueError(s)
    neg = s.startswith("-")
    body = s[1:] if neg else s
    if not body:
        raise ValueError(s)
    total = 0
    for ch in body.lower():
        idx = _DIGITS.find(ch)
        if idx == -1 or idx >= base:
            raise ValueError(s)
        total = total * base + idx
    return -total if neg else total
'''

REFERENCE["topo"] = r'''
import heapq


def topo_order(deps):
    nodes = set(deps)
    for pres in deps.values():
        nodes.update(pres)
    indeg = {n: 0 for n in nodes}
    children = {n: set() for n in nodes}
    for task, pres in deps.items():
        for p in set(pres):
            if task not in children[p]:
                children[p].add(task)
                indeg[task] += 1
    heap = [n for n in nodes if indeg[n] == 0]
    heapq.heapify(heap)
    out = []
    while heap:
        n = heapq.heappop(heap)
        out.append(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                heapq.heappush(heap, c)
    if len(out) != len(nodes):
        raise ValueError("cycle")
    return out
'''

REFERENCE["duration"] = r'''
import re

_RE = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def parse_duration(s):
    if not isinstance(s, str) or not s:
        raise ValueError(s)
    m = _RE.fullmatch(s)
    if not m or not any(m.groups()) or not s.isascii():
        raise ValueError(s)
    d, h, mi, se = (int(g) if g else 0 for g in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se
'''

REFERENCE["spiral"] = r'''
def spiral(matrix):
    if not matrix or all(len(r) == 0 for r in matrix):
        if any(len(r) != len(matrix[0]) for r in matrix):
            raise ValueError("ragged")
        return []
    width = len(matrix[0])
    if any(len(r) != width for r in matrix):
        raise ValueError("ragged")
    top, bottom, left, right = 0, len(matrix) - 1, 0, width - 1
    out = []
    while top <= bottom and left <= right:
        for c in range(left, right + 1):
            out.append(matrix[top][c])
        for r in range(top + 1, bottom + 1):
            out.append(matrix[r][right])
        if top < bottom:
            for c in range(right - 1, left - 1, -1):
                out.append(matrix[bottom][c])
        if left < right:
            for r in range(bottom - 1, top, -1):
                out.append(matrix[r][left])
        top, bottom, left, right = top + 1, bottom - 1, left + 1, right - 1
    return out
'''

REFERENCE["rle"] = r'''
def rle_encode(s):
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        run = j - i
        while run > 0:
            k = min(run, 9)
            out.append(f"{k}{s[i]}")
            run -= k
        i = j
    return "".join(out)


def rle_decode(code):
    if len(code) % 2:
        raise ValueError("odd length")
    out = []
    for i in range(0, len(code), 2):
        c = code[i]
        if c not in "123456789":
            raise ValueError("bad count")
        out.append(code[i + 1] * int(c))
    return "".join(out)
'''
