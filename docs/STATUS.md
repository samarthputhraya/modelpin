# Modelpin — Phase 0 status & next steps

> Durable handoff so any session can resume from the repo (not from chat memory).
> Read this with `CLAUDE.md` and `docs/Modelpin-Engineering-Context-Pack.md` (the spec).

## Where we are (branch `main`, pushed to GitHub, private)

- **`33d10d0`** — Phase-0 skeleton + **statistically-hardened behavioral diff** (the moat):
  exact two-sample permutation test (`diff/stats.py`, no SciPy, deterministic);
  verdict gated on `p ≤ 0.05` **and** an effect-size floor (`diff/__init__.py`);
  `strict/unordered/subset/superset` match modes; calibrated confidence.
  Cleanups: Python 3.12, full Apache-2.0 LICENSE, current Anthropic model ids.
- **`f24bd90`** — **CLI wired end-to-end** (`scan/init/baseline/check`), **spec §7 reporter**,
  offline fake-provider demo (`examples/traces/demo_traces.json`), `storage.py`
  baseline persistence, fix for a Windows `UnicodeEncodeError` crash.
- A 13-agent adversarial audit of the diff engine found + fixed **1 CRITICAL**
  (sampling fallback returned `p=0.0`); two proposed "fixes" were verified wrong and rejected.
- **31 tests passing; ruff + black clean.**

Run the offline demo:
```
mp baseline --provider fake --fixtures examples/traces/demo_traces.json \
  --model claude-opus-4-6 --scenarios-dir examples/scenarios --config examples/modelpin.yaml
mp check --to claude-opus-4-7 --from claude-opus-4-6 --provider fake \
  --fixtures examples/traces/demo_traces.json --scenarios-dir examples/scenarios --config examples/modelpin.yaml
```

## Milestone (Phase 0 Definition of Done — spec §11)

`mp check` detects a genuine regression **between two REAL models** and prints the
PR-style report, **with a measured low false-positive rate on a held-out set**.

## The one gap that blocks the milestone

`modelpin/providers/openai.py` is **implemented** (Chat Completions API, BYO-key from
`OPENAI_API_KEY`, SDK import kept lazy, dependency-injectable client). `anthropic.py`
is still a `NotImplementedError` stub.

**Phase A — live-path hardening: DONE.** A two-workflow adversarial sweep (40-agent
discovery + 22-agent review) found 32 confirmed ungraceful-failure modes on the real
`mp baseline`/`mp check` path; the 13 must-fix-before-live-run items are fixed and the
fixes adversarially re-verified (APPROVE). Highlights: every live `openai.*`/adapter
error now becomes a friendly, **key-safe** `ProviderError` (auth errors never echo the
key; all error text is scrubbed of `sk-`/`Bearer` tokens) instead of a raw traceback;
zero-config no longer routes to the Anthropic stub; `--runs <2` is rejected (a single
run can't form a distribution → false confidence); malformed scenario/YAML/baseline
files fail with named, friendly errors; baseline writes are atomic; the CI exit code is
computed before the (now-guarded) report write; skipped no-baseline scenarios are
surfaced, not hidden. **78 tests pass; ruff + black clean.** The 7 deferred items
(stale `regression_threshold`/`judge_model` knobs, mid-run resume, `--fail-on` knob,
baseline model/provider validation, latency/token deltas in CLI output) are Phase B/C.

**Phase A — live smoke run: DONE (first real two-model run).** Ran the full pipeline
live: `mp baseline` on **gpt-3.5-turbo** then `mp check --to gpt-4o-mini` over the 3
bundled scenarios ×5 runs each (BYO-key from a gitignored `.env.local`, ~45 short
completions, pennies). Verdict: 3/3 **unchanged**, PR-style report written. Real traces
for both models are persisted under `.modelpin/` (calibration data). Findings:
- **No false positives on real data (north-star holds).** gpt-4o-mini fired a 2nd tool
  call (`issue_refund`) in 1/5 `refund_request` runs — a real difference — and the engine
  correctly treated the 1-in-5 blip as noise (TVD 0.2 < the 0.5 floor), not a regression.
- **The semantic blind spot is now empirically proven.** On `invoice_parse` both models
  were semantically identical but textually different ("The total amount is $5." vs "5
  dollars."); the structural diff can't see equivalence → **the LLM-judge is the #1 next
  build**, not a nice-to-have. (The bundled `must_contain:["$"]` assertion is noise — "$"
  appeared in 1/5 of gpt-3.5's outputs and 0/5 of gpt-4o-mini's, yet both are correct.)
- **Single-turn replay can't realize multi-step agent trajectories.** `refund_request`
  expects `[lookup_order, issue_refund]` but replay stops after turn 1 (no tool-result
  loop), so the 2nd call rarely appears. Either make agent scenarios single-step or add a
  (mocked) tool-execution loop to replay.
- **Env/ops:** corporate-proxy TLS — the openai SDK (httpx+certifi) fails with
  `CERTIFICATE_VERIFY_FAILED`; fixed safely with `truststore.inject_into_ssl()` (uses the
  OS trust store; verification stays ON). Worth a built-in opt-in for corporate users.

The DoD is **not fully closed**: still need a held-out FP measurement (known-equivalent
pairs → false-alarm rate; a known-regression pair → confirmed detection) and the judge.

## Next steps (priority order — re-ordered after the live smoke run)

1. **Semantic LLM-judge (`diff/semantic.py`) — now the #1 build, empirically justified.**
   The smoke run proved the structural diff is blind to "same meaning, different words"
   (`invoice_parse`). Implement + wire `semantic_score` into the verdict (low-temp,
   BYO-key, reuse the OpenAI client; calibrate it as a *downgrading* signal first, not a
   lone escalator, to protect the FP north-star). Wire the dormant `judge_model` config
   field; retire the stale `regression_threshold` field.
2. **Replay depth for agent scenarios.** Single-turn replay can't reach multi-step
   trajectories (`refund_request` never reaches `issue_refund`). Decide: keep scenarios
   single-step, or add a (mocked) tool-result loop so full trajectories emerge. Pick
   before authoring the real scenario set.
3. **6–8 real scenarios** spanning structural / semantic / refusal failure modes — and
   drop noisy assertions like bare `must_contain:["$"]` (the smoke run showed it flags
   formatting, not behavior).
4. **Close the DoD: held-out FP measurement.** Known-equivalent model pairs → measure the
   false-alarm rate; a known-regression pair → confirm detection. (The OpenAI adapter,
   `truststore` TLS path, and persisted `.modelpin/` baselines for gpt-3.5-turbo +
   gpt-4o-mini are all in place to build on.)
5. **Calibrate the diff thresholds** (`MIN_TOOL_TVD`, `MIN_REFUSAL_DELTA`, `ALPHA`) on the
   real traces — replaces today's defensible-but-uncalibrated defaults.
6. **Anthropic adapter — deferred (no key). Prefer a Google/Gemini adapter first**: the
   user has OpenAI ✅ + a **Gemini** key but **no** Anthropic key, so — by the same
   "build what we can run live" logic that put OpenAI first — Google/Gemini is the next
   *runnable* adapter and unlocks the first true **cross-vendor** comparison (the core of
   the wedge + the independent public Report). Mirror the OpenAI adapter's contract
   (lazy SDK import, BYO-key from env, injectable client, key-safe `ProviderError`).
   Anthropic stays a $0 mock-tested stub until an `ANTHROPIC_API_KEY` appears.
7. **Corporate-proxy TLS:** consider an opt-in `truststore.inject_into_ssl()` at CLI
   startup (or honor `SSL_CERT_FILE`) so devs behind an intercepting proxy don't hit a
   `CERTIFICATE_VERIFY_FAILED` on first run. Verification stays ON (OS trust store).
4. **Diff deepening (offline-doable now):** cost (token) regression as `changed_minor`
   (gate via the permutation test; latency is jittery — handle carefully); an
   "inconclusive / underpowered → re-run" surface (spec §6C); wire `subset/superset`
   + `expected_tool_calls`/`output_schema` assertions into the verdict.
5. **GitHub Action** polish (`actions/action.yml`) for CI usage.
6. **Smaller audit items:** 6–8 example scenarios; scenario-JSON error handling;
   detector registry-validation (cut regex false positives); remove/clarify the now-stale
   `regression_threshold` config field; add the missing per-module tests already covered
   for watcher/config/report/cli.

## Design guardrails (do NOT undo — see also `~/.claude` project memory)

- Diff confidence for an `unchanged` verdict = `min(p)` is **intentional** (identical
  traces → 1.0; near-α miss → low). Do **not** invert it to `1 − p`.
- The conservative effect-size floors are deliberate for the **false-positive north-star**;
  tune them only with real-trace calibration data, never by guessing.
- BYO-key everywhere; no live paid API calls in tests.
- Public reports are framed as measurement/opinion, never "Model X is worse." Apache-2.0 core.

## Completion & roadmap (estimate — part-time solo dev + AI pair; full-time ~2-3x faster)

- **MVP (Phase 0): ~55-60% done.** Built: full offline pipeline + the hardened, audited
  diff engine + CLI + §7 reporter. Remaining ~40% is the *proof-of-value*: real
  OpenAI/Anthropic adapters, the LLM-judge, a **real two-model run with a measured low
  false-positive rate on a held-out set** (the DoD), 6-8 real scenarios, and Report #1.
- **Public OSS launch (early Phase 1): ~30% done.** pipx/PyPI, a real GitHub Action,
  Watcher automation, the public report site + cadence, and hosted Pro are barely started.

| Milestone | Remaining | Calendar (from now) |
|---|---|---|
| MVP (Phase 0 DoD) | OpenAI adapter -> Anthropic adapter -> LLM-judge -> real 2-model run + FP measurement + threshold calibration -> 6-8 scenarios | ~2-4 weeks |
| Modelpin Report #1 | run open suite on a real model launch, write up, post | overlaps; gated by an actual model launch |
| OSS public launch | pipx/PyPI, real GitHub Action (PR comment via API), docs/DX | ~6-8 weeks |
| First dollars (full Phase 1) | Watcher automation, report site + cadence, hosted Pro | ~3-6 months (~$1.5k MRR) |
| Phase 2 (GitHub App + teams) | FastAPI+Postgres, auto-PR App, dashboard, Stripe | ~6-14 months (~$10k MRR) |
| Phase 3 (business + scale) | managed auto-fix PRs, SSO, more providers | ~14-30 months ($1M ARR) |

Caveats: scales with hours/week; Report #1 is gated by a real provider model launch;
hosted tiers are the heavy lifts. Mirrors the spec's phasing (§11).
