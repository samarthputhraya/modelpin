"""The canonical argument key itself (MP-04).

``tests/test_tool_arguments.py`` pins the VERDICT behaviour; this file pins the encoder that
produces it. The distinction matters because the encoder is where this fix spends or protects
the north-star metric, and [M] the rest of the suite is blind to it: every existing fixture is
argument-free, so `canonical_arguments` could be replaced with `lambda a: ""` and 252 tests
would still pass.

Each test below corresponds to a way a naive encoding turns provider jitter into a false
positive, or turns two different behaviours into one key (a silent false NEGATIVE).
"""

from __future__ import annotations

import math

import pytest

from modelpin.diff import ALPHA, MIN_TOOL_ARG_TVD, diff_scenario
from modelpin.diff.argkey import canonical_arguments, describe_argument_change
from modelpin.diff.stats import permutation_pvalue_distribution, total_variation_distance
from modelpin.diff.structural import name_trajectory_is_stable, tool_arg_sequence
from modelpin.models import DiffVerdict, ToolCall, Trace


def _trace(model: str, calls: list[tuple[str, dict]], idx: int = 0) -> Trace:
    return Trace(
        scenario_id="s",
        model_id=model,
        run_idx=idx,
        tool_calls=[ToolCall(name=n, arguments=a) for n, a in calls],
        final_output="x",
    )


# --- false-positive channels: these MUST collapse to one key ----------------------------


def test_key_order_does_not_change_the_key():
    """providers/openai.py json.loads() preserves the model's emission order, so the same
    payload can arrive keyed differently across runs of the SAME side. That is jitter."""
    assert canonical_arguments({"amount": 49.99, "order_id": "A1"}) == canonical_arguments(
        {"order_id": "A1", "amount": 49.99}
    )


def test_nested_key_order_does_not_change_the_key():
    """sort_keys=True is not enough on its own -- it has to reach every nesting level."""
    assert canonical_arguments({"o": {"a": 1, "b": 2}, "l": [{"x": 1, "y": 2}]}) == (
        canonical_arguments({"l": [{"y": 2, "x": 1}], "o": {"b": 2, "a": 1}})
    )


def test_int_and_float_spellings_collapse():
    """openai.py json.loads() yields int where google.py's SDK dict yields float, so the
    spelling is an artefact of which adapter saw the call, not of the model's behaviour."""
    assert canonical_arguments({"qty": 1}) == canonical_arguments({"qty": 1.0})


def test_a_non_finite_float_matches_its_persisted_baseline():
    """A baseline round-trips through model_dump(mode="json"), which turns nan/inf into None.
    If the live candidate keyed them differently it could never equal its own baseline."""
    assert canonical_arguments({"x": float("nan")}) == canonical_arguments({"x": None})
    assert canonical_arguments({"x": math.inf}) == canonical_arguments({"x": None})


# --- false-NEGATIVE channels: these must stay DISTINCT -----------------------------------


def test_a_bool_never_collides_with_an_int():
    """LOAD-BEARING, and the one a tidy-up pass would break: isinstance(True, int) is True,
    True == 1, and hash(True) == hash(1) -- so if the bool check moved below the int check,
    a FLAG and a QUANTITY would merge inside the Counter in stats.py. Silent false negative."""
    assert canonical_arguments({"f": True}) != canonical_arguments({"f": 1})
    assert canonical_arguments({"f": False}) != canonical_arguments({"f": 0})


def test_large_ints_beyond_float_precision_stay_distinct():
    """Above 2**53 a float cannot represent an int exactly, so int/float unification has to
    stop there or two distinct large arguments would collide into one key."""
    assert canonical_arguments({"n": 2**53 + 1}) != canonical_arguments({"n": 2**53 + 2})


def test_a_dropped_argument_key_changes_the_key():
    """A candidate that stops passing dry_run is executing for real."""
    assert canonical_arguments({"a": 1, "dry_run": True}) != canonical_arguments({"a": 1})


def test_colliding_nested_keys_keep_both_entries():
    """Two distinct keys can collide under str(). A dict comprehension would silently DROP
    one of them; the pair-list fallback keeps both."""
    key = canonical_arguments({"k": {1: "a", "1": "b"}})
    assert "a" in key and "b" in key


def test_a_list_and_its_reordering_stay_distinct():
    """Argument ORDER inside a list is the model's choice and can be behavioural (a sequence
    of steps). Only DICT key order is jitter."""
    assert canonical_arguments({"steps": [1, 2]}) != canonical_arguments({"steps": [2, 1]})


# --- totality: the contract is "never raises" -------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"b": b"\x00\xff"},
        {"s": {1, 2, 3}},
        {"t": (1, 2)},
        {"deep": None},
        {"cjk": "漢字"},
        {"none": None},
        {"nested": [[[{"a": [1, {"b": 2}]}]]]},
    ],
    ids=["bytes", "set", "tuple", "none-value", "unicode", "none", "deeply-nested"],
)
def test_never_raises_on_awkward_payloads(payload):
    key = canonical_arguments(payload)
    assert isinstance(key, str)
    hash(key)


def test_never_raises_on_a_self_referential_payload():
    """Depth-bounded rather than recursion-bounded, so it terminates instead of raising."""
    d: dict = {}
    d["self"] = d
    assert isinstance(canonical_arguments(d), str)


def test_never_raises_on_an_object_whose_repr_raises():
    class Hostile:
        def __repr__(self):
            raise RuntimeError("nope")

        def __str__(self):
            raise RuntimeError("nope")

    assert isinstance(canonical_arguments({"x": Hostile()}), str)


def test_an_unknown_type_does_not_mint_a_fresh_key_every_run():
    """A default repr embeds a memory address. If one leaked into the key, an unrecognised
    argument type would become a PERMANENT false positive -- every run a distinct key."""

    class Opaque:
        pass

    assert canonical_arguments({"x": Opaque()}) == canonical_arguments({"x": Opaque()})
    assert "0x" not in canonical_arguments({"x": Opaque()})


def test_none_and_empty_arguments_encode_alike():
    assert canonical_arguments(None) == canonical_arguments({})


# --- the explanation is a PR-comment surface --------------------------------------------


def test_the_explanation_never_prints_a_string_argument_value():
    """Argument values are model-authored and land in a PR comment -- exactly where a customer
    email, an order id or a key-shaped token lives. Numbers and booleans are diagnostic and
    safe; strings are not."""
    base = (("send", canonical_arguments({"to": "alice@example.com", "amount": 5})),)
    cand = (("send", canonical_arguments({"to": "sk-live-000111222", "amount": 500})),)
    text = describe_argument_change(base, cand)
    assert "@" not in text
    assert "sk-" not in text
    assert "amount 5->500" in text  # the useful half survives


def test_the_explanation_cannot_inject_rich_markup():
    """report/__init__.py interpolates the explanation into Rich markup. A model-authored
    "[/]" once crashed `mp check` while it was rendering its own regression."""
    base = (("search", canonical_arguments({"[/]": 1})),)
    cand = (("search", canonical_arguments({"[/]": 2})),)
    assert "[" not in describe_argument_change(base, cand)


# --- the gate's two structural properties ------------------------------------------------


def test_the_argument_gate_is_skipped_when_the_name_trajectory_is_unstable():
    """The precondition that keeps this fix false-positive-neutral. When names are jittery
    the NAME gate is the responsible signal; refining the key would only add noise."""
    base = [_trace("o", [("web_search", {"q": f"q{i}"})], i) for i in range(5)]
    cand = [_trace("n", [("sql_query", {"q": f"s{i}"})], i) for i in range(5)]
    assert not name_trajectory_is_stable(base, cand)
    result = diff_scenario("s", "o", "n", base, cand)
    # The NAME signal must still fire at full strength -- folding arguments into one key
    # instead of gating them separately is what silences this case.
    assert result.verdict == DiffVerdict.regression
    assert result.signals.tool_arg_match is None, "the gate ran when it should have been skipped"


def test_min_tool_arg_tvd_means_disjoint_at_every_supported_n():
    """MIN_TOOL_ARG_TVD = 1.0 is a structural rule, not a fitted dial, and its meaning must
    not drift with N. The rejected alternative -- halving ALPHA -- is [M] DEAD at N=4: a
    fully disjoint change scores p = 0.028571, which clears ALPHA but not ALPHA/2.
    """
    for n in range(4, 9):
        base, cand = ["A"] * n, ["B"] * n
        tvd = total_variation_distance(base, cand)
        p = permutation_pvalue_distribution(base, cand)
        assert tvd >= MIN_TOOL_ARG_TVD and p <= ALPHA, f"disjoint change does not fire at N={n}"
    # ... and the N=4 trap that ruled the alternative out.
    p4 = permutation_pvalue_distribution(["A"] * 4, ["B"] * 4)
    assert p4 <= ALPHA and p4 > ALPHA / 2


def test_arguments_are_anchored_to_their_tool_name():
    """f(x=1), g(y=2) must never compare equal to f(y=2), g(x=1)."""
    a = tool_arg_sequence(_trace("m", [("f", {"x": 1}), ("g", {"y": 2})]))
    b = tool_arg_sequence(_trace("m", [("f", {"y": 2}), ("g", {"x": 1})]))
    assert a != b
