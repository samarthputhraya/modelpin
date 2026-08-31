# `examples/refusal-suite/` — the suite built to make the refusal channel fire

**Role: `fit`** (declared in [`examples/roles.json`](../roles.json), enforced by
`tests/test_suite_roles.py`, governed by ADR-0025).

## Why this suite exists

Modelpin has five verdict-bearing channels. `[M] 2026-08-31`, after two live dogfood runs,
four of them had been observed working on real material and one had not:

| channel | first observed on real material |
|---|---|
| text assertions | dogfood #1 (a real JSON-classification app) |
| tool trajectory | dogfood #2 (a real tool-calling app) — flagged 3 of 6 at 0.95–0.99 |
| tool arguments | dogfood #2 — exercised, same-model only |
| semantic judge | dogfood #2 — scored 0.80–1.00 and varied |
| **refusal** | **never** — `[M]` 0 of 60 traces on dogfood #1, 0 of 30 on #2 |

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
Live, on a free Groq key:

```bash
modelpin baseline --provider groq --model <model-a> --scenarios-dir examples/refusal-suite --runs 5
modelpin check    --provider groq --from <model-a> --to <model-b> \
                  --scenarios-dir examples/refusal-suite --runs 5
```

6 scenarios × 5 runs × 2 sides = **60 completions**. Pace at ≤24 calls/min.

## Status — `[M] 2026-08-31`, live on Groq

**The detector fires, and it discriminates.** `[M]` 75 of 90 traces on the `refuse_*` scenarios
recorded `refused=True`, across three models (`qwen/qwen3.6-27b`, `qwen/qwen3.8-27b`,
`allam-2-7b`); **0 of 15** on `answer_plain_question`. Before this run the count was 0 of 90
across two dogfoods.

`[M]` One decline came back with a **curly apostrophe** — `I don't have access … so I can't
provide` — and was still detected, which is the first time `_normalize_for_refusal`'s
glyph-folding has been exercised by a real model rather than by a string this project wrote.

**Still `[A]`: the channel has never moved a verdict on real material.** Every available
free-tier model declines all five prompts, so every comparison came back `unchanged` — correct,
but not proof the channel can go red. `[M]` The natural experiment (`groq/compound`, which has
web search and should *not* decline) is unusable: `413 Request Entity Too Large` on 2 of 6
scenarios and over the 8000 TPM ceiling on the rest. Closing that half needs a model that
answers where another declines.
