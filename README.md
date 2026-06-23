# Modelpin

**Dependabot for AI models.** Know before the model breaks you.

Modelpin watches the AI models your app depends on. The moment a provider ships or
retires a model, Modelpin replays your app's real behavior on the new model, detects
genuine regressions (despite model randomness), and opens a pull request explaining
exactly what changed — so you find out *before* your users do.

Plus a public **Modelpin Report** on every major model launch: the independent
"what broke when the model changed" reference.

> Status: **Phase 0 scaffold.** The skeleton runs end-to-end with fake providers; the
> real provider adapters and the behavioral-diff engine are stubbed with clear TODOs.
> See `docs/Modelpin-Engineering-Context-Pack.md` (full spec) and `CLAUDE.md` (build rules).

## Why
AI apps are pinned to a specific model (e.g. `claude-opus-4-6`). Providers update and
retire models on *their* schedule, with no version pinning and no warning — so apps
silently change behavior or break in production. "Model pinning" is the #1 unmet
developer ask. There is no lockfile + Dependabot for the *model* an app depends on.
Modelpin is that safety net.

## The wedge (don't lose it)
1. The **migration** tool, not a general eval platform.
2. **Zero-config + auto-triggered** on the providers' release schedule.
3. **Cross-vendor**; the public Report is the independent voice labs can't be.
4. Win the **solo-dev / small-team long tail** the enterprise tools ignore.

## Install (dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # add ",providers" for live OpenAI/Anthropic calls
modelpin version                  # or: mp version
```

## Commands
```bash
mp init                  # scaffold modelpin.yaml + scenarios/ in your repo
mp scan                  # detect which models this repo uses
mp baseline              # record current model behavior for your scenarios (N runs)
mp check --to <model>    # replay on a new model, report behavioral regressions
mp report                # run the public suite, draft a Modelpin Report
```

## Bring-your-own-key
Replays use **your** provider API key from the environment
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...). Modelpin never ships or stores keys.

## Layout
```
modelpin/        cli.py config.py models.py
  watcher/  detector/  scenarios/  replay/  providers/
  diff/     structural.py semantic.py stats.py   <- THE CORE
  report/
  data/models.json   # seed model registry (verify before relying on it)
actions/  examples/  docs/  tests/
```

## License
Apache-2.0. See `LICENSE`.
