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

Under the settings above we observed, to date:

| Evidence | Pairs | False positives |
|---|---|---|
| Synthetic noisy-but-equivalent pairs (golden test `test_false_positive_rate_is_zero_on_equivalent_pairs`) | 4 | **0 / 4** |
| Real same-model split-half (captured gpt-4o-mini + gpt-3.5-turbo traces, structural+stats) | 6 | **0 / 6** |
| Real cross-model smoke run, gpt-3.5-turbo → gpt-4o-mini (3 scenarios) | 3 | **0 / 3** |

In the cross-model run, gpt-4o-mini issued a *second* tool call (`issue_refund`) on 1 of 5
`refund_request` runs — a genuine behavioral difference — and the engine correctly treated
that 1-in-5 blip as **noise, not a regression** (effect size below the floor). That is the
distributional test doing its job.

**Status:** the full **judged, 8-scenario, N=5 same-model** run (`scripts/fp_measurement.py`)
is harness-ready and resilient to transient blips, but the live numbers are **pending a
stable network window to `api.openai.com`** (intermittent connectivity at the time of
writing). Re-run the command above to populate them; the methodology and held-out set are
fixed in advance, so the result is reproducible.

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
