"""Hidden evaluation tests. Never shown to any agent; used only to score final code."""

HIDDEN = {}

HIDDEN["semver"] = r'''
import pytest
from solution import compare_versions


def test_core_numeric():
    assert compare_versions("1.0.0", "2.0.0") == -1
    assert compare_versions("2.1.0", "2.0.9") == 1
    assert compare_versions("1.10.0", "1.9.0") == 1
    assert compare_versions("3.4.5", "3.4.5") == 0


def test_prerelease_lower_than_release():
    assert compare_versions("1.0.0-alpha", "1.0.0") == -1
    assert compare_versions("1.0.0", "1.0.0-rc.1") == 1


def test_spec_precedence_chain():
    chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
             "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
    for a, b in zip(chain, chain[1:]):
        assert compare_versions(a, b) == -1, (a, b)
        assert compare_versions(b, a) == 1, (b, a)


def test_numeric_vs_alpha_identifiers():
    assert compare_versions("1.0.0-1", "1.0.0-a") == -1
    assert compare_versions("1.0.0-10", "1.0.0-9") == 1
    assert compare_versions("1.0.0-a10", "1.0.0-a9") == -1


def test_build_metadata_ignored():
    assert compare_versions("1.0.0+build.1", "1.0.0+other") == 0
    assert compare_versions("1.0.0-rc.1+b.7", "1.0.0-rc.1") == 0


def test_hyphen_inside_prerelease():
    assert compare_versions("1.0.0-x-y", "1.0.0-x-z") == -1


@pytest.mark.parametrize("bad", ["1.0", "1.0.0.0", "01.0.0", "1.0.0-01", "1.0.0-", "1.0.0-alpha..1", "a.b.c", "", "1.0.0-al$pha"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        compare_versions(bad, "1.0.0")
'''

HIDDEN["csv_line"] = r'''
import pytest
from solution import parse_csv_line


def test_plain():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]


def test_quoted_comma_and_escaped_quote():
    assert parse_csv_line('"a,b",c') == ["a,b", "c"]
    assert parse_csv_line('"he said ""hi""",x') == ['he said "hi"', "x"]


def test_empty_fields():
    assert parse_csv_line("") == [""]
    assert parse_csv_line("a,") == ["a", ""]
    assert parse_csv_line(",,") == ["", "", ""]
    assert parse_csv_line('""') == [""]
    assert parse_csv_line('"x",""') == ["x", ""]


def test_whitespace_preserved():
    assert parse_csv_line(" a , b ") == [" a ", " b "]


def test_quote_inside_unquoted_field_is_literal():
    assert parse_csv_line('a"b,c') == ['a"b', "c"]


def test_errors():
    for bad in ['"a', '"a"b,c', '"abc""', 'x,"y']:
        with pytest.raises(ValueError):
            parse_csv_line(bad)
'''

HIDDEN["calc"] = r'''
import pytest
from solution import evaluate


def approx(a, b):
    return abs(a - b) < 1e-9


def test_precedence():
    assert approx(evaluate("1+2*3"), 7)
    assert approx(evaluate("(1+2)*3"), 9)
    assert approx(evaluate("7-2-1"), 4)
    assert approx(evaluate("8/4/2"), 1)


def test_power_rules():
    assert approx(evaluate("2**3**2"), 512)
    assert approx(evaluate("-2**2"), -4)
    assert approx(evaluate("(-2)**2"), 4)
    assert approx(evaluate("2**-1"), 0.5)


def test_unary_and_decimals():
    assert approx(evaluate("2*-3"), -6)
    assert approx(evaluate("--3"), 3)
    assert approx(evaluate(" 1.5 * 2 "), 3)
    assert approx(evaluate("10/4"), 2.5)
    assert isinstance(evaluate("3"), float)


def test_division_by_zero():
    with pytest.raises(ZeroDivisionError):
        evaluate("1/0")


def test_malformed():
    for bad in ["", "(1+2", "1+", "2 3", "abc", "1+2)", "()", "3..2", "*3"]:
        with pytest.raises(ValueError):
            evaluate(bad)
'''

HIDDEN["path_norm"] = r'''
import pytest
from solution import normalize_path


def test_examples():
    assert normalize_path("/a/./b/../../c/") == "/c"
    assert normalize_path("/../") == "/"
    assert normalize_path("/home//foo/") == "/home/foo"
    assert normalize_path("/") == "/"


def test_special_names():
    assert normalize_path("/a/.../b") == "/a/.../b"
    assert normalize_path("/...") == "/..."
    assert normalize_path("/.hidden/./x/..") == "/.hidden"
    assert normalize_path("/a/..x/") == "/a/..x"


def test_errors():
    for bad in ["a/b", "", "./a"]:
        with pytest.raises(ValueError):
            normalize_path(bad)
'''

HIDDEN["intervals"] = r'''
import pytest
from hypothesis import given, strategies as st
from solution import merge_intervals


def test_examples():
    assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]
    assert merge_intervals([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]
    assert merge_intervals([(5, 8), (1, 2), (2, 3), (7, 10)]) == [(1, 3), (5, 10)]
    assert merge_intervals([]) == []
    assert merge_intervals([(4, 4), (4, 4)]) == [(4, 4)]
    assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]


def test_invalid():
    with pytest.raises(ValueError):
        merge_intervals([(3, 1)])


def test_input_not_modified_and_tuples():
    data = [(5, 6), (1, 2)]
    out = merge_intervals(data)
    assert data == [(5, 6), (1, 2)]
    assert all(isinstance(t, tuple) for t in out)


@given(st.lists(st.tuples(st.integers(0, 30), st.integers(0, 6)).map(lambda t: (t[0], t[0] + t[1])), max_size=10))
def test_covers_same_points(items):
    out = merge_intervals(items)
    pts = {x for s, e in items for x in range(s, e + 1)}
    assert {x for s, e in out for x in range(s, e + 1)} == pts
    for (s1, e1), (s2, e2) in zip(out, out[1:]):
        assert e1 < s2
'''

HIDDEN["roman"] = r'''
import pytest
from solution import from_roman


def test_values():
    assert from_roman("I") == 1
    assert from_roman("IV") == 4
    assert from_roman("IX") == 9
    assert from_roman("XLII") == 42
    assert from_roman("XCIX") == 99
    assert from_roman("CDXLIV") == 444
    assert from_roman("MCMXCIV") == 1994
    assert from_roman("MMMCMXCIX") == 3999


@pytest.mark.parametrize("bad", ["", "iv", "IIII", "VX", "IC", "XM", "IIV", "MMMM", "VV", "LL", "DD", "IXIX", "XCX", "CMM", "IL", "ABC"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        from_roman(bad)
'''

HIDDEN["isbn"] = r'''
from solution import is_valid_isbn


def test_isbn10():
    assert is_valid_isbn("0-306-40615-2")
    assert not is_valid_isbn("0306406153")
    assert is_valid_isbn("080442957X")
    assert is_valid_isbn("080442957x")
    assert is_valid_isbn("0 8044 2957 X")


def test_isbn13():
    assert is_valid_isbn("978-0-306-40615-7")
    assert is_valid_isbn("978 0 306 40615 7")
    assert not is_valid_isbn("9780306406158")


def test_rejects_bad_shapes():
    for bad in ["", "X804429570", "97803064061X7", "12345678901234", "030640615", "0-306-40615-2a", "978030640615X",
                "0.306.40615.2", "０306406152"]:
        assert is_valid_isbn(bad) is False, bad
'''

HIDDEN["flatten"] = r'''
import copy
from solution import flatten


def test_nested():
    data = {"a": {"b": 1, "c": [1, {"d": 2}]}, "e": []}
    assert flatten(data) == {"a.b": 1, "a.c.0": 1, "a.c.1.d": 2, "e": []}


def test_empty_containers_and_scalars():
    assert flatten({}) == {}
    assert flatten({"x": {}}) == {"x": {}}
    assert flatten({"a": None, "b": False, "c": "s"}) == {"a": None, "b": False, "c": "s"}
    assert flatten({"a": [[1, 2], []]}) == {"a.0.0": 1, "a.0.1": 2, "a.1": []}


def test_not_modified():
    data = {"a": {"b": [1, {"c": {}}]}}
    snap = copy.deepcopy(data)
    flatten(data)
    assert data == snap
'''

HIDDEN["wrap"] = r'''
import pytest
from solution import wrap


def test_basic():
    assert wrap("the quick brown fox", 10) == ["the quick", "brown fox"]
    assert wrap("a b c", 3) == ["a b", "c"]
    assert wrap("abcd efgh", 4) == ["abcd", "efgh"]


def test_whitespace():
    assert wrap("", 5) == []
    assert wrap("   \n\t ", 5) == []
    assert wrap("  one\n\ntwo   three ", 9) == ["one two", "three"]


def test_long_words():
    assert wrap("abcdefghij x", 4) == ["abcd", "efgh", "ij x"]
    assert wrap("abcdefghij xyz", 4) == ["abcd", "efgh", "ij", "xyz"]
    assert wrap("a abcdefgh", 4) == ["a", "abcd", "efgh"]
    assert wrap("abcdefgh", 4) == ["abcd", "efgh"]


def test_width_one_and_errors():
    assert wrap("ab c", 1) == ["a", "b", "c"]
    with pytest.raises(ValueError):
        wrap("x", 0)
'''

HIDDEN["base_conv"] = r'''
import pytest
from hypothesis import given, strategies as st
from solution import from_base, to_base


def test_to_base():
    assert to_base(0, 2) == "0"
    assert to_base(255, 16) == "ff"
    assert to_base(-255, 16) == "-ff"
    assert to_base(35, 36) == "z"
    assert to_base(5, 2) == "101"


def test_from_base():
    assert from_base("FF", 16) == 255
    assert from_base("-z", 36) == -35
    assert from_base("0", 7) == 0


@pytest.mark.parametrize("bad", ["", "-", "+7", " 7", "7 ", "1_0", "0x1f", "12", "--1"])
def test_from_base_invalid(bad):
    base = 16 if bad == "0x1f" else (2 if bad == "12" else 10)
    with pytest.raises(ValueError):
        from_base(bad, base)


def test_bad_base():
    for b in (0, 1, 37):
        with pytest.raises(ValueError):
            to_base(5, b)
        with pytest.raises(ValueError):
            from_base("1", b)


@given(st.integers(-10**12, 10**12), st.integers(2, 36))
def test_round_trip(n, b):
    assert from_base(to_base(n, b), b) == n
'''

HIDDEN["topo"] = r'''
import pytest
from solution import topo_order


def test_simple():
    assert topo_order({"b": ["a"], "c": ["b"]}) == ["a", "b", "c"]


def test_lexicographic_tie_break():
    assert topo_order({"d": [], "c": [], "b": [], "a": []}) == ["a", "b", "c", "d"]
    assert topo_order({"z": ["m"], "a": ["m"], "m": []}) == ["m", "a", "z"]
    assert topo_order({"c": ["b"], "a": ["d"]}) == ["b", "c", "d", "a"]


def test_prereq_only_nodes_and_duplicates():
    assert topo_order({"x": ["y", "y"]}) == ["y", "x"]
    assert topo_order({}) == []


def test_cycles():
    for deps in ({"a": ["a"]}, {"a": ["b"], "b": ["a"]}, {"a": ["b"], "b": ["c"], "c": ["a"], "d": []}):
        with pytest.raises(ValueError):
            topo_order(deps)
'''

HIDDEN["duration"] = r'''
import pytest
from solution import parse_duration


def test_valid():
    assert parse_duration("1h30m") == 5400
    assert parse_duration("90m") == 5400
    assert parse_duration("2d4s") == 172804
    assert parse_duration("0s") == 0
    assert parse_duration("1d1h1m1s") == 90061
    assert parse_duration("100s") == 100


@pytest.mark.parametrize("bad", ["", "1h1h", "30m1h", "1.5h", "h", "10", "1H", " 1h", "-1h", "1h 30m", "1h30", "s", "1x", "١h"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)
'''

HIDDEN["spiral"] = r'''
import pytest
from solution import spiral


def test_square_and_rect():
    assert spiral([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [1, 2, 3, 6, 9, 8, 7, 4, 5]
    assert spiral([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]) == [1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7]
    assert spiral([[1, 2], [3, 4], [5, 6], [7, 8]]) == [1, 2, 4, 6, 8, 7, 5, 3]


def test_degenerate():
    assert spiral([]) == []
    assert spiral([[]]) == []
    assert spiral([[7]]) == [7]
    assert spiral([[1, 2, 3]]) == [1, 2, 3]
    assert spiral([[1], [2], [3]]) == [1, 2, 3]
    assert spiral([[1, 2, 3], [4, 5, 6]]) == [1, 2, 3, 6, 5, 4]


def test_ragged_and_not_modified():
    with pytest.raises(ValueError):
        spiral([[1, 2], [3]])
    m = [[1, 2], [3, 4]]
    spiral(m)
    assert m == [[1, 2], [3, 4]]
'''

HIDDEN["rle"] = r'''
import pytest
from hypothesis import given, strategies as st
from solution import rle_decode, rle_encode


def test_encode():
    assert rle_encode("aaab") == "3a1b"
    assert rle_encode("z" * 12) == "9z3z"
    assert rle_encode("112") == "2112"
    assert rle_encode("") == ""
    assert rle_encode("a" * 18) == "9a9a"


def test_decode():
    assert rle_decode("3a1b") == "aaab"
    assert rle_decode("2112") == "112"
    assert rle_decode("") == ""


def test_decode_errors():
    for bad in ["3", "0a", "a3", "3a1"]:
        with pytest.raises(ValueError):
            rle_decode(bad)


@given(st.text(alphabet="ab12 ", max_size=30))
def test_round_trip(s):
    assert rle_decode(rle_encode(s)) == s
'''
