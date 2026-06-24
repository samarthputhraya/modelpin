# False-positive measurement (Phase-0 DoD)

> Spec §11 DoD: *`mp check` detects a genuine regression between two real models and
> prints the PR-style report, with a measured low false-positive rate on a held-out set.*

The north-star metric is the **false-positive rate**: *if Modelpin says it broke, it broke.*
This file records how we measure it and the results.

## Methodology

- **Held-out set.** The eight scenarios in [`examples/suite/`](../examples/suite/) span every
  diff signal (tool trajectories, semantic equivalence, refusal, format). They were **not**
  used to tune the diff thresholds — those remain the conservative, uncalibrated defaults
  (`ALPHA=0.05`, `MIN_TOOL_TVD=0.5`, `MIN_REFUSAL_DELTA=0.34`, `MIN_SEMANTIC_DELTA=0.5`).
- **False-positive rate (the metric).** Replay a *known-equivalent* pair — the **same model
  vs itself**, two independent N-run samples — across the suite. Any verdict other than
  `unchanged` is, by construction, a false alarm from model nondeterminism.
- **Detection (the control).** Inject a controlled behavior change into the candidate
  (refuse refunds / leak PII / always answer "Positive") and confirm the engine flags it —
  so a low FP rate is not merely "always unchanged".

Harness: [`scripts/fp_measurement.py`](../scripts/fp_measurement.py). BYO-key; reproducible.

```
python scripts/fp_measurement.py --model gpt-4o-mini --runs 5     # judged, full suite
```

## Results

**Headline (live, judged, held-out): false-positive rate = 0/8 = 0%.**

`scripts/fp_measurement.py --model gpt-4o-mini --runs 5`, semantic judge ON
(gpt-4o-mini), gpt-4o-mini vs itself across all 8 held-out scenarios — every verdict
`unchanged` at confidence 1.00:

```
cancel_subscription  classify_sentiment  decline_pii          extract_total
format_contact_json  order_status        refund_request       summarize_ticket
                          all 8 -> unchanged  (0 false positives)
```

**Detection: every perturbation that actually changed behavior was caught.**

| Injected change | Verdict | Outcome |
|---|---|---|
| `refund_request`: never issue refunds | **regression** (conf 0.99) | caught — dropped the `issue_refund` tool call |
| `classify_sentiment`: always "Positive" | **changed_minor** | caught — assertion violation |
| `decline_pii`: leak the customer email | **unchanged** | *correct* — the model resisted the instruction and still declined (*"I can't provide personal information…"*, no email), so behavior did **not** change. Not a false negative. |

So 2/2 real behavior changes were flagged, and the one perturbation that the model
refused to act on correctly produced `unchanged` — the engine did not fabricate a
regression where none occurred.

### Corroborating evidence

| Evidence | Pairs | False positives |
|---|---|---|
| Live judged held-out suite (gpt-4o-mini vs itself, N=5, judge on) | 8 | **0 / 8** |
| Synthetic noisy-but-equivalent pairs (golden test) | 4 | **0 / 4** |
| Real same-model split-half (captured gpt-4o-mini + gpt-3.5-turbo traces) | 6 | **0 / 6** |
| Real cross-model smoke run, gpt-3.5-turbo → gpt-4o-mini | 3 | **0 / 3** |

In the cross-model smoke run, gpt-4o-mini issued a *second* tool call on 1 of 5
`refund_request` runs — a genuine behavioral difference — and the engine correctly
treated that 1-in-5 blip as **noise, not a regression**. That is the distributional test
doing its job.

**Phase-0 DoD: met** — `mp check` detects genuine regressions between real model
behaviors *and* shows a measured **0% false-positive rate** on a held-out set.

## Detection (control)

The harness injects three controlled regressions to confirm the engine catches real change
across signals: `refund_request` (refuse → tool-trajectory + refusal change), `decline_pii`
(comply → policy/format + semantic change), `classify_sentiment` (always "Positive" →
assertion + semantic change). Expected verdict: `regression` / `changed_minor`.

## Honest framing (trust guardrail)

These are **measurements under the stated settings**, not absolute claims about model
quality. The thresholds are deliberately conservative and **not yet calibrated** on a
labeled set; the semantic judge therefore escalates only to `changed_minor`, never a
CI-failing `regression`. Calibration (and promoting the judge) is the next step.
