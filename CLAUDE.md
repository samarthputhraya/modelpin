# CLAUDE.md — Modelpin

> Project memory for Claude Code. Read this first, every session. Full spec: `docs/Modelpin-Engineering-Context-Pack.md`.

## What we're building
**Modelpin = "Dependabot for AI models."** It watches model releases/retirements, replays a developer's app behavior on a new model, detects real regressions despite model randomness, and opens a pull request explaining what changed — so devs find out *before* production breaks. Plus a public "Modelpin Report" on every major model launch (distribution engine).

CLI: `modelpin` (alias `mp`). Tagline: *Know before the model breaks you.* Open-core: free CLI/Action, paid hosted tier later.

## The wedge (never drift from this)
1. The **migration** tool, NOT a general eval platform.
2. **Zero-config + auto-triggered** on providers' release schedule.
3. **Cross-vendor**; the public Report is the independent voice labs can't be.
4. Serve the **solo-dev / small-team long tail** the enterprise tools ignore.

## Non-goals (refuse scope creep toward these)
Not a general eval/observability platform · not prompt management · not a model gateway/host · not an absolute "which model is best" leaderboard. We measure *behavior change relative to the user's app*.

## Tech stack
- **Python 3.12**, single language across CLI/engine/backend.
- **Typer** (CLI) + **Rich** (output) · **pydantic v2** (data models) · **pytest** · **ruff + black** · full type hints.
- Provider SDKs (openai, anthropic, google-genai) behind a thin **adapter interface** in `providers/`. *Verify current SDK/endpoint details when coding — they change.*
- Consider depending on **`agentevals`** (Apache-2.0) for tool-call trajectory matchers — don't reinvent them.
- Phase 1 delivery: **GitHub Action** (no servers). Phase 2+: FastAPI + Postgres + GitHub App + Stripe.

## Repo map
```
modelpin/  cli.py config.py models.py
  watcher/   detector/  scenarios/  replay/  providers/
  diff/      structural.py semantic.py stats.py   ← THE CORE
  report/
actions/  examples/  data/models.json  docs/  tests/
```

## Commands (keep these working)
- `mp init` — scaffold `modelpin.yaml` + `scenarios/` in a repo.
- `mp scan` — detect which models the repo uses.
- `mp baseline` — record current model behavior for the scenarios (N runs).
- `mp check --to <model>` — replay on a new model, output the behavioral diff + PR-style report.
- `mp report` — run the public standard suite, draft a Modelpin Report.
- Dev: `pytest`, `ruff check`, `black .`.

## The core problem to get right (diff/)
Models are **non-deterministic** — naive text diff = constant false alarms. Detect *real* change via MULTIPLE signals over MULTIPLE runs:
- **Structural:** tool-call trajectory match (strict/unordered/subset/superset), output-schema/format validity, refusal detection, latency/token deltas.
- **Semantic:** LLM-as-judge ("do these mean/accomplish the same?"), low temperature, calibrated.
- **Stats:** run each scenario N times (default 3–5) on baseline AND candidate; flag a regression only when the candidate **distribution** differs from baseline — never on a single differing sample. Emit a confidence score.
- **North-star metric: false-positive rate.** A crying-wolf alerter is worthless. Optimize for "if Modelpin says it broke, it broke."

## Guardrails (legal/trust — do not violate)
- **Use the END USER's own API key** for replays (cost + provider ToS). Never hardcode or ship keys; read from env / Actions secrets.
- Public Reports must be **reproducible** and phrased as measurement/opinion ("on our open suite, under these settings, we observed…"), never "Model X is worse." Keep the harness + scenarios open-source.
- GitHub App/Action acts **only on repos that installed it**; self-throttle; honor rate limits; no unsolicited PRs.
- License: **Apache-2.0** for OSS core; hosted proprietary bits in a separate package.

## How to work
- Build order: data models → Detector + Watcher (easy) → Replay → **invest the most effort in diff/** → Reporter → GitHub Action.
- Write **golden tests** for the diff engine using recorded traces (so it's testable without live API calls and CI stays cheap/deterministic).
- Small modules, typed, tested. When unsure, re-read the wedge + non-goals above.
- Current focus: **Phase 0 — core engine MVP + Modelpin Report #1.** (See roadmap in the spec.)
