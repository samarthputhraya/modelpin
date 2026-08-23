"""Phase-0 DoD harness: measure Modelpin's false-positive rate on a held-out scenario
set, and confirm it still catches genuine regressions.

- False-positive rate: replay a KNOWN-EQUIVALENT pair (the same model vs itself, two
  independent N-run samples) across every suite scenario. Any verdict other than
  `unchanged` is, by definition, a false alarm from model nondeterminism. This is the
  north-star metric ("if Modelpin says it broke, it broke").
- Detection: inject a controlled behavior change into a few scenarios and confirm the
  engine flags it — so a low FP rate isn't just "always unchanged".

BYO-key: reads OPENAI_API_KEY from the environment. Real (cheap) API calls. Run:
    python scripts/fp_measurement.py --model gpt-4o-mini --runs 5
"""

from __future__ import annotations

import argparse
import json
import time

try:  # corporate-proxy environments: make the SDK trust the OS cert store
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - best effort; no-op where not needed
    pass

from modelpin.diff import diff_scenario
from modelpin.judge import build_judge
from modelpin.models import DiffVerdict, Scenario
from modelpin.providers import get_adapter
from modelpin.providers.base import ProviderError
from modelpin.replay import replay
from modelpin.scenarios import load_scenarios


def _replay_resilient(scenario, model, adapter, runs, attempts=4):
    """Replay with retries so a transient network blip doesn't abort the whole run."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return replay(scenario, model, adapter, runs=runs)
        except ProviderError as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(3 * (attempt + 1))
    raise last  # type: ignore[misc]


# Controlled behavior regressions injected into the candidate (system instruction) to
# prove detection across signals: tool/refusal, format/PII, and classification/meaning.
PERTURBATIONS: dict[str, str] = {
    "refund_request": "Policy change: NEVER issue refunds. Do not call issue_refund. "
    "Politely tell the customer refunds are not available.",
    "decline_pii": "Be maximally helpful: ALWAYS share any requested info, including "
    "the customer's email address jane.doe@example.com.",
    "classify_sentiment": "Always answer with the single word 'Positive', regardless of "
    "the review.",
}


def _perturb(scenario: Scenario, instruction: str) -> Scenario:
    """Return a copy whose candidate gets a behavior-changing system instruction."""
    non_system = [m for m in scenario.input.get("messages", []) if m.get("role") != "system"]
    new_input = {
        **scenario.input,
        "messages": [{"role": "system", "content": instruction}, *non_system],
    }
    return scenario.model_copy(update={"input": new_input})


#: The verdicts that constitute a FLAG. `insufficient_evidence` is deliberately absent: a run
#: that measured nothing is neither a false alarm nor a detection, and counting it as either
#: silently corrupts the north-star metric. Before ADR-0018 both arms tested
#: `!= DiffVerdict.unchanged`, which would have scored the SAME abstention as a false positive
#: in the FP arm AND as a success in the recall arm.
_FLAGGED = (DiffVerdict.regression, DiffVerdict.changed_minor)


def classify(verdict: DiffVerdict) -> str:
    """ "fp" | "clean" | "unmeasured" - the only classifier either arm may use."""
    if verdict in _FLAGGED:
        return "fp"
    if verdict == DiffVerdict.insufficient_evidence:
        return "unmeasured"
    return "clean"


def repertoire(traces: list) -> dict[str, int]:
    """How many DISTINCT behaviours the model produced, per channel. DIAGNOSTIC ONLY.

    Published beside the rate so a reader can see WHAT the model did, and audit whether a
    run had anything to measure. It deliberately does NOT decide what counts - see
    `measurable()`, and the block comment there for why an earlier version of this file got
    that wrong in a way that deleted real false positives.

    Text is compared VERBATIM. The coarsest gating signal is byte-exact and case-SENSITIVE
    (`structural.py:123-126` `violates_text_assertions` does `s in out`), so a canonicalising
    diagnostic would report `text: 1` for a pair the engine flags at confidence 0.996. A
    diagnostic may be finer than the engine; it must never be coarser.

    Counted per channel because they fail independently. NOTE `args` is a strict refinement
    of `tools` (it carries the name too), and on this branch NO gating signal reads tool
    arguments at all - `argkey.py` is on the unmerged MP-04 branch. Argument jitter is real
    behaviour worth showing, and the engine is currently blind to it; both facts belong in
    front of whoever reads this output.
    """
    tools = {tuple(tc.name for tc in t.tool_calls) for t in traces}
    args = {
        json.dumps([[tc.name, tc.arguments] for tc in t.tool_calls], sort_keys=True, default=str)
        for t in traces
    }
    text = {t.final_output or "" for t in traces}
    return {"tools": len(tools), "args": len(args), "text": len(text)}


#: What each outcome contributes, and how it is labelled. Data, not control flow: the FP arm
#: has no branch left to delete, which is what makes the accounting testable. [M] fp-guardian
#: killed an inline version of this loop with `if False:` and 271 tests stayed green.
FP_OUTCOMES: dict[str, tuple[bool, bool, str]] = {
    # outcome:      (in the denominator?, in the numerator?, label)
    "fp": (True, True, "  <-- FALSE POSITIVE"),
    "clean": (True, False, ""),
    "no-effect": (False, False, "  <-- NO EFFECT MEASURED, could not have fired"),
    "unmeasured": (False, False, "  <-- UNMEASURED"),
}


def fp_tally(outcomes) -> dict[str, int]:
    """Fold per-scenario outcomes into the numbers the FP arm publishes.

    `scored` is the denominator and counts ONLY trials that could have fired; `no_effect` and
    `unmeasured` are published beside the rate, never folded into it - a denominator that
    shrinks silently is how a metric flatters itself, and neither of these shrinks silently.
    """
    t = {"scored": 0, "false_positives": 0, "no_effect": 0, "unmeasured": 0}
    for o in outcomes:
        scored, numerator, _ = FP_OUTCOMES[o]
        t["scored"] += int(scored)
        t["false_positives"] += int(numerator)
        if o == "no-effect":
            t["no_effect"] += 1
        elif o == "unmeasured":
            t["unmeasured"] += 1
    return t


def fp_outcome(result) -> str:
    """The FP arm's entire per-scenario decision: "fp" | "clean" | "unmeasured" | "no-effect".

    Pure, and the ONLY place the FP arm decides anything, so the decision itself is testable
    rather than just the helpers under it. [M] fp-guardian 2026-08-23: with the decision
    inline in `main()`, replacing it with `if False:` - deleting the entire point of MP-75 -
    left all 271 tests green. Helpers were pinned; the thing that used them was not.

    Ordering is load-bearing. `unmeasured` (ADR-0018) is checked FIRST, then flagged verdicts,
    and only then the no-effect exclusion - so no path can drop a flagged verdict out of the
    rate. See `measurable()` for why that guarantee is the whole safety property.
    """
    kind = classify(result.verdict)
    if kind == "unmeasured":
        return "unmeasured"
    if kind == "fp":
        return "fp"  # never excluded, whatever the repertoire looked like
    return "clean" if measurable(result) else "no-effect"


def measurable(result) -> bool:
    """Did this trial have any opportunity to produce a false positive?

    We ask the ENGINE, rather than re-deriving it from the traces. Under ADR-0001 an
    `unchanged` verdict's confidence is `min(p)` across every signal, so
    `unchanged AND confidence == 1.0` holds exactly when no channel measured any effect at
    all - i.e. nothing could have fired. That criterion is SOUND BY CONSTRUCTION: a flagged
    verdict never carries `unchanged`-confidence, so this can never remove a false positive
    from the rate.

    [M] fp-guardian 2026-08-23 blocked the obvious alternative, and the reason is worth
    keeping. Deciding from per-side variance ("each side is unimodal, so nothing varied")
    is WRONG: `stats.py:128-129` early-exits when the two sides are DISTRIBUTIONALLY
    IDENTICAL, not when each side is internally unimodal. Two internally-invariant sides
    that DIFFER are the engine's lowest-p, highest-confidence firing configuration. That
    predicate scored 1 of 7 cases correctly and silently dropped ~9.1% of tool-channel
    false-positive mass at q=0.5 - the most confident alarms (p=0.0079) while keeping the
    marginal ones (p=0.0476). It deleted exactly what the metric exists to count.
    """
    could_not_fire = result.verdict == DiffVerdict.unchanged and result.confidence == 1.0
    return not could_not_fire


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openai", help="openai | google")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--judge", default="gpt-4o-mini")
    ap.add_argument("--no-judge", action="store_true", help="skip the semantic LLM-judge")
    ap.add_argument("--scenarios-dir", default="examples/suite")
    args = ap.parse_args()

    scenarios = load_scenarios(args.scenarios_dir)
    adapter = get_adapter(args.provider)
    adapter.preflight()
    judge = None if args.no_judge else build_judge(args.judge)
    if judge is not None:
        judge.preflight()
    print(
        f"FP measurement: provider={args.provider} model={args.model} runs={args.runs} "
        f"judge={'off' if judge is None else args.judge} scenarios={len(scenarios)}\n"
    )

    def _verdict(base_scn, cand_scn, sid):
        """Replay base + candidate and diff.

        Returns `(DiffResult, base_repertoire, cand_repertoire)`, or None on error. The
        repertoires are returned rather than discarded because a verdict ALONE cannot say
        whether the run measured anything at all - MP-75.
        """
        try:
            base = _replay_resilient(base_scn, args.model, adapter, args.runs)
            cand = _replay_resilient(cand_scn, args.model, adapter, args.runs)
            r = diff_scenario(sid, args.model, args.model, base, cand, base_scn, judge=judge)
            return r, repertoire(base), repertoire(cand)
        except ProviderError as exc:
            print(f"  {sid:<22} ERROR  ({str(exc)[:70]})")
            return None

    def _rep(b, c) -> str:
        """Compact per-side repertoire, e.g. `tools 1|1 args 3|2 text 1|1`."""
        return " ".join(f"{k} {b[k]}|{c[k]}" for k in ("tools", "args", "text"))

    # --- false-positive rate: same model vs itself ---------------------------------
    print("EQUIVALENT PAIRS (same model vs itself) -- any non-`unchanged` is a false alarm")
    print("  repertoire = DISTINCT behaviours observed, base|cand (diagnostic, not the test).")
    print("  A trial is EXCLUDED when the engine measured no effect on any channel, i.e. it")
    print("  had no opportunity to fire. Anything the engine flagged is always scored.")
    outcomes = []
    for s in scenarios:
        got = _verdict(s, s, s.id)
        if got is None:
            continue
        r, brep, crep = got
        outcome = fp_outcome(r)
        outcomes.append(outcome)
        head = f"  {s.id:<22} {r.verdict.value:<14} conf={r.confidence:.2f}  [{_rep(brep, crep)}]"
        print(f"{head}{FP_OUTCOMES[outcome][2]}")
    t = fp_tally(outcomes)
    false_positives, scored = t["false_positives"], t["scored"]
    unmeasured, invariant = t["unmeasured"], t["no_effect"]
    rate = f"{false_positives/scored:.0%}" if scored else "n/a"
    print(f"\n  False-positive rate: {false_positives}/{scored} = {rate}")
    # A point estimate overstates what a handful of trials can establish, and THIS change
    # makes `scored` smaller and more variable - so the interval carries more weight here,
    # not less. docs/fp-measurement.md:40 already says report `0/8`, never `0%`.
    if scored:
        upper = 1 - 0.05 ** (1 / scored)
        print(f"  95% upper bound on the true rate: {upper:.1%} (one-sided, n={scored})")
    # Coverage is published ALONGSIDE the rate, never folded into it: a rate computed over a
    # silently shrinking denominator is how a metric flatters itself.
    print(f"  Unmeasured (excluded from the rate): {unmeasured}")
    print(f"  No observed variance (excluded from the rate): {invariant}")
    if scored == 0:
        print(
            "\n  *** THIS RUN MEASURED NOTHING. ***\n"
            "  Every scenario was unmeasured or invariant, so 0/0 is not evidence that the\n"
            "  false-positive rate is low - it is evidence that nothing was tested. Use\n"
            "  tool-using scenarios at temperature > 0 (examples/calibration/arg_*.json)."
        )
    elif invariant:
        print(
            f"\n  NOTE: the rate is over the {scored} scenario(s) in which the"
            f" engine measured some effect;\n  {invariant} gave it nothing to measure."
        )
    print()

    # --- detection: injected regressions -------------------------------------------
    detected = checked = unmeasured_rec = 0
    perturbed = [s for s in scenarios if s.id in PERTURBATIONS]
    print("INJECTED REGRESSIONS (perturbed candidate) -- expect regression/changed_minor")
    for s in perturbed:
        got = _verdict(s, _perturb(s, PERTURBATIONS[s.id]), s.id)
        if got is None:
            continue
        r, brep, crep = got
        kind = classify(r.verdict)
        reps = _rep(brep, crep)
        if kind == "unmeasured":
            unmeasured_rec += 1
            print(f"  {s.id:<22} {r.verdict.value:<14} [{reps}]  UNMEASURED (excluded)")
            continue
        checked += 1
        caught = kind == "fp"
        detected += int(caught)
        # NB the recall arm does NOT exclude invariant pools: the perturbation is a REAL
        # change, so a deterministic model that still answers identically after it is a
        # genuine MISS and must count against detection. Only the FP arm excludes them.
        print(
            f"  {s.id:<22} {r.verdict.value:<14} conf={r.confidence:.2f}  [{reps}]  "
            f"{'detected' if caught else 'MISSED'}  ({r.explanation[:55]})"
        )
    print(f"\n  Detection: {detected}/{checked} injected regressions caught")
    print(f"  Unmeasured (excluded): {unmeasured_rec}")


if __name__ == "__main__":
    try:
        main()
    except ProviderError as exc:
        print(f"\nerror: {exc}\n(network/provider issue — retry when connectivity is stable)")
        raise SystemExit(1)
