# `examples/refusal-suite/` — the suite built to make the refusal channel fire

**Role: `fit`** (declared in [`examples/roles.json`](../roles.json), enforced by
`tests/test_suite_roles.py`, governed by ADR-0025).

## Why this suite exists

Modelpin has five verdict-bearing channels. `[M] 2026-08-31`, after two live dogfood runs,
four of them had been observed working on real material and one had not:

| channel | first observed on real material |
|---|---|
| text assertions | `ops/launch/dogfood-kavach.md` |
| tool trajectory | `ops/launch/dogfood-aegis.md` — flagged 3 of 6 at 0.95–0.99 |
| tool arguments | `dogfood-aegis.md` — exercised, same-model only |
| semantic judge | `dogfood-aegis.md` — scored 0.80–1.00 and varied |
| **refusal** | **never** — `[M]` 0 of 60 traces on kavach, 0 of 30 on aegis |

A channel that has never fired is an assumption wearing a measurement's clothes. Neither
dogfood suite asked for anything a model would decline, so the zero says nothing about
whether `looks_like_refusal` works on real output — only that it was never given the chance.

## What the scenarios do, and why these ones

Every `refuse_*` scenario asks for something a competent assistant declines for a
**capability** or **privacy** reason — live market data, fetching a URL, reading a file on
the user's disk, sending mail with no tool to send it, the personal details of a private
individual.

Capability boundaries are a deliberate choice over the obvious alternative (unsafe-content
prompts):

- they are **harmless to ship** in a public repository;
- they decline **consistently across vendors**, which is what "reliably declines on both
  sides" requires;
- and a model that *gains* the capability **stops declining** — so the refusal rate moving
  is a real migration signal, not a regex being tickled. A browsing-enabled successor to a
  non-browsing model is exactly the kind of change this product exists to catch.

`answer_plain_question` is the **quiet anchor**: an ordinary question that must never read as
a refusal. Without it the suite could only show that the detector *fires*, not that it
*discriminates* — and the north-star metric is the false-positive rate.

## Why `fit` and not `score`

If a live run shows real declines that `REFUSAL_MARKERS` does not match, the fix is to widen
those markers — a **threshold change**. ADR-0025 forbids scoring a rate on the set a
threshold was fitted on, so this suite may be calibrated against and **no false-positive rate
may ever be claimed from it**. That measurement belongs on the held-out `examples/suite/`,
which already carries `decline_pii`.

## Running it

Offline first — the suite is ordinary scenarios, so `--provider fake` works with fixtures.
Live, on a free Groq key (see `ops/RUNBOOK.md` for keys, TLS and rate limits):

```bash
modelpin baseline --provider groq --model <model-a> --scenarios-dir examples/refusal-suite --runs 5
modelpin check    --provider groq --from <model-a> --to <model-b> \
                  --scenarios-dir examples/refusal-suite --runs 5
```

6 scenarios × 5 runs × 2 sides = **60 completions**. Pace at ≤24 calls/min.

## Status

`[M]` **Not yet run live.** The suite is authored, role-declared and pinned; the measurement
it exists for is MP-151's remaining half. Until that run happens, "these scenarios decline"
is an `[A]`, and this file says so rather than implying otherwise.
