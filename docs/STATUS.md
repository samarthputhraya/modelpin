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

`modelpin/providers/openai.py` and `anthropic.py` are still `NotImplementedError` stubs.
Until they exist we cannot replay on real models, cannot record real traces, and
therefore cannot calibrate the diff thresholds or measure the real false-positive rate.

## Next steps (priority order)

1. **Provider adapters — the milestone blocker. Build OpenAI FIRST** (an OpenAI key
   is available; an Anthropic key is not, so the OpenAI adapter is the one we can run
   live against two real models). Then build the Anthropic adapter too (it can be
   written + mock-tested for $0, but stays dormant until an `ANTHROPIC_API_KEY` exists).
   Read the END USER's key from env (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`); never
   hardcode/ship/log a key. Capture `messages`, `tool_calls` (name+args),
   `final_output`, `refused`, `tokens{in,out}`, `latency_ms` into a `Trace`.
   Keep the SDK import inside `run()`. **Verify SDK shapes against official docs
   (OpenAI) / the `claude-api` skill (Anthropic) — do not write them from memory.**
   Modern Claude models (Opus 4.6+/Sonnet 4.6) reject `temperature`/`top_p`/`budget_tokens`.
   **Cost note:** building + unit-testing with a mocked client = $0 (no key, no network).
   Tests stay on `FakeProvider` / mocks — NO live paid calls in CI. The only spend is a
   real `mp check` run: the bundled example is ~30 short completions (a few thousand
   tokens) = pennies on OpenAI.
2. **Record a real baseline + candidate** on the example agent across **two real OpenAI
   models** (e.g. an older vs a newer GPT); measure the FP rate on a held-out set (closes the DoD).
3. **Calibrate the diff thresholds** (`MIN_TOOL_TVD`, `MIN_REFUSAL_DELTA`, `ALPHA`) on
   those real traces — replaces today's defensible-but-uncalibrated defaults.
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
