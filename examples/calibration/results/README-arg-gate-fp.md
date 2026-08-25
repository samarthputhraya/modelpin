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

**`[M]` It is not a corpus bug.** All seven declare `temperature: 0.7` and
`providers/google.py:210-211` passes it through. At temperature 0.7, `gemini-2.5-flash` emits
**byte-identical tool arguments** for six of seven argument shapes — enum choice, key order,
list order, numeric rounding and optional fields are all schema-constrained, so the model is
deterministic regardless of temperature. Only free text varies.

## What this DOES support

- `[M]` **Zero false positives in 7 scored trials**, on the one shape that varies. The gate saw
  genuine run-to-run variance (`args 5|3`, `4|5`, `3|4`) and stayed `unchanged` every time: the
  disjointness requirement held against real model output, not just synthetic pools.
- `[M]` **Schema-constrained arguments cannot fire the gate at all** on this model, because the
  pools are never disjoint. That is a narrower blast radius than the synthetic analysis feared.

## What this does NOT support, and must not be quoted as

- A false-positive rate for the argument gate. `n=7` from one scenario is not that.
- Anything about a model other than `gemini-2.5-flash`, or a temperature other than 0.7.
- #38's condition 6. It remains **open**. The corpus needs argument-*varying* scenarios, not
  merely argument-*bearing* ones — MP-54 delivered the latter.
