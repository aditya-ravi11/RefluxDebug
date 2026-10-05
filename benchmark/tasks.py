"""Benchmark tasks. Each prompt is a precise natural-language specification.

The prompts are the ONLY thing the agents see. Hidden evaluation tests live in hidden_tests.py and
reference solutions (used only to validate those tests) live in reference.py.
"""

TASKS = [
    {
        "id": "semver",
        "title": "Semantic version comparison",
        "prompt": (
            "Write compare_versions(a: str, b: str) -> int that compares two Semantic Versioning 2.0.0 strings and "
            "returns -1 if a < b, 0 if they have equal precedence, 1 if a > b. A version is MAJOR.MINOR.PATCH "
            "(exactly three non-negative integers without leading zeros, so '0' is fine but '01' is not), optionally "
            "followed by '-' and a pre-release made of one or more dot-separated identifiers, optionally followed by "
            "'+' and build metadata. Identifiers are non-empty and use only [0-9A-Za-z-]; numeric pre-release "
            "identifiers must not have leading zeros. Build metadata is ignored for precedence. Precedence rules: "
            "compare MAJOR, MINOR, PATCH numerically; a version with a pre-release has lower precedence than the same "
            "version without one; pre-release identifiers are compared left to right, numeric identifiers "
            "numerically, alphanumeric identifiers lexically in ASCII order, numeric identifiers always have lower "
            "precedence than alphanumeric ones, and if all shared identifiers are equal the longer list wins. Raise "
            "ValueError for any string that is not a valid version."
        ),
    },
    {
        "id": "csv_line",
        "title": "CSV line parser",
        "prompt": (
            "Write parse_csv_line(line: str) -> list[str] that splits one CSV line into fields. Fields are separated "
            "by commas. A field that starts with a double quote is a quoted field: it ends at the next double quote "
            "that is not part of a doubled pair \"\", commas inside it are literal, and \"\" inside it stands for one "
            "double quote character. After the closing quote of a quoted field the next character must be a comma or "
            "the end of the line, otherwise raise ValueError. An unterminated quoted field raises ValueError. In an "
            "unquoted field every character except the comma is literal (including double quotes and spaces; nothing "
            "is stripped). The empty string returns [''] and a trailing comma produces a trailing empty field. Do not "
            "use the csv module."
        ),
    },
    {
        "id": "calc",
        "title": "Arithmetic expression evaluator",
        "prompt": (
            "Write evaluate(expr: str) -> float that evaluates an arithmetic expression and returns a float. Supported: "
            "non-negative number literals made of digits with an optional single decimal part (for example 3, 42, "
            "3.25), binary + - * / and ** (power), unary + and -, and parentheses. Whitespace between tokens is "
            "ignored. Use Python's precedence and associativity for these operators: ** binds tighter than unary minus "
            "on its left (-2**2 == -4), ** is right-associative (2**3**2 == 512) and its right operand may carry a "
            "unary sign (2**-1 == 0.5); * and / bind tighter than + and -, which are left-associative. Division by "
            "zero raises ZeroDivisionError. Any malformed input (empty string, unbalanced parentheses, dangling "
            "operator, two numbers in a row, any other character) raises ValueError. eval and exec are not allowed."
        ),
    },
    {
        "id": "path_norm",
        "title": "Unix path normalisation",
        "prompt": (
            "Write normalize_path(path: str) -> str that simplifies an absolute Unix path. The input must start with "
            "'/', otherwise raise ValueError (this includes the empty string). Repeated slashes count as one, a '.' "
            "component is removed, a '..' component removes the previous component (at the root it does nothing). Any "
            "other component, including '...', '.hidden' or '..x', is an ordinary name. The result starts with '/', "
            "has no trailing slash, and is '/' when nothing remains."
        ),
    },
    {
        "id": "intervals",
        "title": "Closed interval merging",
        "prompt": (
            "Write merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]] that merges closed "
            "integer intervals (start, end). Two intervals are merged when they overlap or touch (one ends exactly "
            "where the other starts, e.g. (1, 3) and (3, 5) become (1, 5)); intervals like (1, 2) and (3, 4) are NOT "
            "merged. The input may be in any order and may contain duplicates or single points (start == end). If any "
            "interval has start > end raise ValueError. Return tuples sorted by start. The input list must not be "
            "modified."
        ),
    },
    {
        "id": "roman",
        "title": "Strict Roman numeral parser",
        "prompt": (
            "Write from_roman(s: str) -> int that converts a Roman numeral to an integer in the range 1..3999. Only the "
            "canonical modern form is valid: uppercase letters I V X L C D M, subtractive pairs only IV IX XL XC CD "
            "CM, I X C M repeated at most three times in a row, V L D never repeated, and symbols in non-increasing "
            "value order apart from those subtractive pairs. In other words a string is valid exactly when it equals "
            "the standard Roman representation of the number it denotes. Raise ValueError for anything else, including "
            "the empty string, lowercase letters, 'IIII', 'VX', 'IC', 'XM', 'IIV' and 'MMMM'."
        ),
    },
    {
        "id": "isbn",
        "title": "ISBN-10 / ISBN-13 validator",
        "prompt": (
            "Write is_valid_isbn(s: str) -> bool. Hyphens and spaces anywhere in s are ignored; after removing them "
            "the remaining characters must form either an ISBN-10 or an ISBN-13, otherwise return False. ISBN-10: nine "
            "digits followed by a check character that is a digit or 'X'/'x' (meaning 10); valid when the sum of "
            "(10 - i) * value_i over positions i = 0..9 is divisible by 11. 'X' is only allowed in the last position. "
            "ISBN-13: exactly thirteen digits, valid when the sum of digits weighted alternately 1, 3, 1, 3, ... from "
            "the left is divisible by 10. The function never raises; any other input returns False."
        ),
    },
    {
        "id": "flatten",
        "title": "Nested JSON flattening",
        "prompt": (
            "Write flatten(obj: dict) -> dict that flattens nested JSON-like data into a single-level dict whose keys "
            "are paths joined with '.'. Dict keys are used as-is (they never contain '.'), list elements use their "
            "index, e.g. {'a': [{'b': 1}]} becomes {'a.0.b': 1}. Scalars (numbers, strings, booleans, None) are leaf "
            "values. An empty dict or empty list nested inside is kept as a leaf value at its path ({} or []). "
            "flatten({}) returns {}. The input must not be modified."
        ),
    },
    {
        "id": "wrap",
        "title": "Greedy word wrap",
        "prompt": (
            "Write wrap(text: str, width: int) -> list[str] that word-wraps text greedily. Words are the result of "
            "text.split() (any whitespace separates words and is collapsed). Words are placed on a line separated by "
            "single spaces as long as the line length stays <= width; otherwise the word starts a new line. A word "
            "longer than width always starts on a new line and is cut into pieces of exactly width characters, each "
            "piece on its own line, except the final piece, which stays on the current line so that following words "
            "may be appended to it if they fit. Return [] for empty or whitespace-only text. Raise ValueError if "
            "width < 1."
        ),
    },
    {
        "id": "base_conv",
        "title": "Strict base conversion",
        "prompt": (
            "Write to_base(n: int, base: int) -> str and from_base(s: str, base: int) -> int for bases 2 to 36 "
            "(inclusive) using digits 0-9 then letters a-z. to_base returns lowercase digits, no leading zeros "
            "('0' for zero), and a leading '-' for negative numbers. from_base accepts an optional single leading "
            "'-' followed by one or more digits valid for the base, with letters in either case; nothing else is "
            "accepted: no whitespace, no '+', no underscores, no prefixes like '0x'. Both functions raise ValueError "
            "for a base outside 2..36, and from_base raises ValueError for any invalid string."
        ),
    },
    {
        "id": "topo",
        "title": "Deterministic topological order",
        "prompt": (
            "Write topo_order(deps: dict[str, list[str]]) -> list[str]. deps maps each task to the list of tasks that "
            "must come before it. Tasks that appear only inside the lists are also tasks. Return every task exactly "
            "once in an order where each prerequisite comes before its dependents; whenever several tasks are "
            "available, always take the lexicographically smallest one next, so the answer is unique. Duplicate "
            "prerequisites are allowed. Raise ValueError if there is a cycle (a task depending on itself is a cycle)."
        ),
    },
    {
        "id": "duration",
        "title": "Strict duration parser",
        "prompt": (
            "Write parse_duration(s: str) -> int that converts a compact duration to seconds. The string is one or more "
            "components with no separators; each component is a non-negative integer (digits only) immediately "
            "followed by a unit: d (86400 s), h (3600 s), m (60 s) or s (1 s). Units must appear in the order d, h, m, "
            "s, each at most once, but any may be omitted, e.g. '1h30m', '90m', '2d4s', '0s'. Values are not limited "
            "(e.g. '90m' is fine). Raise ValueError for anything else: empty string, repeated or out-of-order units, "
            "missing number or unit, uppercase units, decimals, signs, spaces."
        ),
    },
    {
        "id": "spiral",
        "title": "Spiral matrix traversal",
        "prompt": (
            "Write spiral(matrix: list[list[int]]) -> list[int] that returns the elements of a rectangular matrix in "
            "clockwise spiral order starting at the top-left corner and moving right first. It must work for any "
            "rectangular shape, including a single row, a single column and 1x1. [] and [[]] return []. Raise "
            "ValueError if the rows do not all have the same length. The input must not be modified."
        ),
    },
    {
        "id": "rle",
        "title": "Run-length codec with bounded runs",
        "prompt": (
            "Write rle_encode(s: str) -> str and rle_decode(code: str) -> str. Encoding replaces each maximal run of a "
            "repeated character with the run length followed by the character, where the length is always a single "
            "digit 1-9: runs longer than 9 are split into chunks of 9 followed by the remainder, e.g. 'aaab' -> '3a1b' "
            "and 12 'z' characters -> '9z3z'. Any character may appear in s, including digits ('112' -> '2112'). "
            "rle_encode('') == ''. rle_decode reverses this: code is a sequence of pairs (digit 1-9, any character) "
            "and must satisfy rle_decode(rle_encode(s)) == s. rle_decode raises ValueError when code has odd length or "
            "a count character is not a digit 1-9."
        ),
    },
]

TASK_BY_ID = {t["id"]: t for t in TASKS}
