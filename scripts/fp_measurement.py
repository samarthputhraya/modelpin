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
import time

try:  # corporate-proxy environments: make the SDK trust the OS cert store
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - best effort; no-op where not needed
    pass

from modelpin.diff import diff_scenario
from modelpin.judge import build_judge
from modelpin.models import DiffVerdict, Scenario
from modelpin.providers.base import ProviderError
from modelpin.providers.openai import OpenAIAdapter
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--judge", default="gpt-4o-mini")
    ap.add_argument("--scenarios-dir", default="examples/suite")
    args = ap.parse_args()

    scenarios = load_scenarios(args.scenarios_dir)
    adapter = OpenAIAdapter()
    adapter.preflight()
    judge = build_judge(args.judge)
    judge.preflight()
    print(
        f"FP measurement: model={args.model} runs={args.runs} judge={args.judge} "
        f"scenarios={len(scenarios)}\n"
    )

    # --- false-positive rate: same model vs itself ---------------------------------
    false_positives = 0
    print("EQUIVALENT PAIRS (same model vs itself) -- any non-`unchanged` is a false alarm")
    for s in scenarios:
        base = _replay_resilient(s, args.model, adapter, args.runs)
        cand = _replay_resilient(s, args.model, adapter, args.runs)
        r = diff_scenario(s.id, args.model, args.model, base, cand, s, judge=judge)
        is_fp = r.verdict != DiffVerdict.unchanged
        false_positives += int(is_fp)
        flag = "  <-- FALSE POSITIVE" if is_fp else ""
        print(f"  {s.id:<22} {r.verdict.value:<14} conf={r.confidence:.2f}{flag}")
    fp_rate = false_positives / len(scenarios) if scenarios else 0.0
    print(f"\n  False-positive rate: {false_positives}/{len(scenarios)} = {fp_rate:.0%}\n")

    # --- detection: injected regressions -------------------------------------------
    detected = 0
    perturbed = [s for s in scenarios if s.id in PERTURBATIONS]
    print("INJECTED REGRESSIONS (perturbed candidate) -- expect regression/changed_minor")
    for s in perturbed:
        base = _replay_resilient(s, args.model, adapter, args.runs)
        cand = _replay_resilient(_perturb(s, PERTURBATIONS[s.id]), args.model, adapter, args.runs)
        r = diff_scenario(s.id, args.model, args.model, base, cand, s, judge=judge)
        caught = r.verdict != DiffVerdict.unchanged
        detected += int(caught)
        print(
            f"  {s.id:<22} {r.verdict.value:<14} conf={r.confidence:.2f}  "
            f"{'detected' if caught else 'MISSED'}  ({r.explanation[:60]})"
        )
    print(f"\n  Detection: {detected}/{len(perturbed)} injected regressions caught")


if __name__ == "__main__":
    try:
        main()
    except ProviderError as exc:
        print(f"\nerror: {exc}\n(network/provider issue — retry when connectivity is stable)")
        raise SystemExit(1)
