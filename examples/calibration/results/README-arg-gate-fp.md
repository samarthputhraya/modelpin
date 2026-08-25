# Argument-gate false-positive run — 2026-08-25

`[M]` The first live measurement of MP-04's argument gate. Both transcripts in this directory
are verbatim stdout, unedited.

    scripts/fp_measurement.py --provider google --model gemini-2.5-flash --runs 5 \
        --no-judge --scenarios-dir examples/calibration --role score --repeats 10

Billed to Google Cloud credit via Vertex (MP-104) — no API key. `--no-judge`, because the
argument gate is structural: invoking the semantic judge would have billed a second provider
and added a channel this run is not measuring.

## Headline

```
70 trials attempted
  53  could not have fired at ALPHA   (excluded, ADR-0022)
  10  provider errors                 (a network outage mid-run; never reached a verdict)
   7  SCORED

False-positive rate: 0/7 = 0%
95% upper bound on the true rate: 34.8% (one-sided Clopper-Pearson, n=7)
```

## Read the denominator before the rate

**`[M]` All 7 scored trials are the SAME scenario, `arg_freetext_note`.** Every other `arg_*`
scenario was excluded on every repeat:

| scenario | scored | excluded |
|---|---|---|
| `arg_freetext_note` | **7** | 2 |
| `arg_enum_phrasing` | 0 | 8 |
| `arg_key_order` | 0 | 9 |
| `arg_list_order` | 0 | 9 |
| `arg_multistep_carry` | 0 | 9 |
| `arg_numeric_rounding` | 0 | 8 |
| `arg_optional_fields` | 0 | 8 |

So `0/7` is **seven repeats of one scenario**, not seven scenarios, and the 34.8% bound is not
a scenario-level false-positive rate. More repeats cannot fix this: they add more of the same
scenario. This is the exchangeability caveat MP-82 prints beside the detection bound, in its
sharpest possible form.

**`[M]` It is not a corpus bug — and the reason is not the one first published here.**

> **Corrected 2026-08-25 (MP-105).** This paragraph previously read: *"At temperature 0.7,
> `gemini-2.5-flash` emits **byte-identical tool arguments** for six of seven argument shapes —
> enum choice, key order, list order, numeric rounding and optional fields are all
> schema-constrained, so the model is deterministic regardless of temperature. Only free text
> varies."* **That is refuted by the transcript in this directory.** `[M]` Recounting the
> per-side repertoire columns of
> [`arg-gate-fp-2026-08-25-gemini-2.5-flash.txt`](arg-gate-fp-2026-08-25-gemini-2.5-flash.txt),
> `arg_numeric_rounding` printed `args 1|2` or `2|1` on **5 of its 8** scored-or-excluded
> trials and `arg_optional_fields` on **3 of 8**. The model varied on **three** of seven
> shapes, not one. The claim was inferred from the exclusion table above rather than read off
> the rows underneath it.

All seven scenarios declare `temperature: 0.7` and `providers/google.py:210-211` passes it
through. `[M]` The reason six shapes never scored is **pool overlap, not determinism**: a side
that emitted one payload sits *inside* a side that emitted two, so every channel returns
`p = 1.00` and ADR-0022 excludes the trial as one that could not have fired. **That is the
gate's false-positive defence working exactly as designed.** A scenario needs *disjoint* pools
to score, and low-rate variance produces overlapping ones far more often than disjoint ones.

`[M]` What a different candidate changes is the **rate**, not the kind: on the same seven files
unchanged, `arg_numeric_rounding` emits 1 distinct payload in 16 runs on `gpt-4o-mini` and 7–9
on `gpt-4.1-mini`. See `examples/calibration/README-arguments.md` and the
`arg-repertoire-*.json` artifacts beside this file.

## What this DOES support

- `[M]` **Zero false positives in 7 scored trials**, on the one shape that varies. The gate saw
  genuine run-to-run variance (`args 5|3`, `4|5`, `3|4`) and stayed `unchanged` every time: the
  disjointness requirement held against real model output, not just synthetic pools.
- `[M]` **Schema-constrained arguments rarely reach disjoint pools on this model**, so they
  seldom fire the gate — a narrower blast radius than the synthetic analysis feared. Stated as
  a rate, not an absolute: each of those six scenarios contributed only 8–9 trials here, and
  `[M]` two of them *did* emit a second payload. "Never fires" is not what n≈8 can support.

## What this does NOT support, and must not be quoted as

- A false-positive rate for the argument gate. `n=7` from one scenario is not that.
- Anything about a model other than `gemini-2.5-flash`, or a temperature other than 0.7.
- #38's condition 6. It remains **open** — but `[M]` **not for the reason first published
  here.** The corpus does not need replacing: it varies on three shapes, and MP-54 delivered
  what it was asked for. What blocks the number is that a scenario must reach *disjoint* pools
  to score, which at these variance rates is rare. Pricing condition 6 needs a candidate
  measured to vary more (`gpt-4.1-mini`, per MP-105) and enough repeats to reach disjointness —
  and it can only be run **after this PR merges**, since `main` has no argument signal at all.
- Any conclusion that a higher-variance candidate is straightforwardly better. `[M]` This
  repository already records disjoint rounding jitter (`3.36` vs `3.357` kg) scoring
  `regression` at confidence 0.992 — a **false positive**. More scorable trials is not a lower
  rate, and the rate is the north-star metric.
