# Modelpin — Engineering Context Pack (v1)
### The single source of truth for building this project. Read this before writing any code.

> **Product name:** **Modelpin** (CLI: `modelpin`, alias `mp`; public report: "The Modelpin Report"). *Do a final registrar WHOIS + trademark check before purchase; the name searched clean across products, domains, PyPI, and GitHub.*
>
> **Tagline:** *Know before the model breaks you — a lockfile for the AI models your app depends on.*
>
> **One-line:** Dependabot for AI models — automatically detect when a model update silently changes an app's behavior, and warn the developer in a pull request before it hits production.
>
> **This doc covers:** vision, the problem, users, scope, architecture, data models, the hard core (behavioral diff), tech stack + rationale, repo layout, build roadmap with definitions of done, success metrics, legal guardrails, and risks. A companion `CLAUDE.md` (operational rules for the coding agent) sits at the repo root.

---

## 1. Vision & strategy (why this exists)

**Problem in one breath:** AI apps are built on a specific model version (e.g. `claude-opus-4-6`). Providers update and retire models on *their* schedule, with no version pinning and no warning, so apps silently change behavior or break in production. There is no "lockfile + Dependabot" for the *model* an app depends on.

**What we build:** a tool that watches model releases/retirements, replays an app's real behavior on the new model, detects meaningful regressions despite model randomness, and opens a pull request explaining what changed — plus a public "Modelpin Report" on every major model launch as the distribution engine.

**Why us / why now:** the pain is real, dated, and accelerating (models update constantly; "model pinning" is the #1 unmet developer ask); it's solo-buildable on public data + provider APIs; and it reaches developers worldwide through open source with no gatekeepers.

**Business goal (honest scope):** a **$1M-ARR** open-core business (~1,000 paying customers) that also compounds an audience + reputation. **Not** a $1B category-king (that seat is crowded — Promptfoo/OpenAI, Solo.io `agentevals`, Braintrust, LangSmith, the EvalView OSS clone). We win a defensible *slice* by being the narrow, automatic, cross-vendor *migration* tool for the long tail those enterprise platforms ignore.

**Strategic wedge (never lose this):**
1. The **migration** tool, not a general eval platform.
2. **Zero-config + auto-triggered** on the providers' release schedule.
3. **Cross-vendor**, and the **public Report** is the independent voice the labs structurally cannot be.
4. Win the **solo-dev / small-team long tail** the $249/mo enterprise tools skip.

---

## 2. Users & jobs-to-be-done

**Primary user (beachhead):** a solo dev or small-team engineer shipping an LLM app/agent to production, who has been (or fears being) burned by a silent model change. Python-leaning, adopts tools via GitHub/`pip`, hates ceremony.

**Their jobs:**
- "Tell me *before* I upgrade whether the new model breaks my app."
- "Warn me when a model I depend on is being retired."
- "Show me *exactly what changed* in plain language, in my normal git workflow."
- "Don't make me build and maintain an eval suite by hand."

**Secondary (later):** small AI-native startups (team features), then scaleups running fleets of agents (business tier, auto-fix).

**Explicit non-users (for now):** large enterprises requiring procurement/SLAs/SOC2 (that's the trap that kills founder-fit). We serve them only if they self-serve.

---

## 3. Scope: MVP, later, and non-goals

**MVP (Phase 0–1) — must do:**
- Detect models a repo uses.
- Track model release/retirement status across OpenAI, Anthropic, Google.
- Capture a behavioral **baseline** from user-provided scenarios.
- **Replay** scenarios on a target/new model and produce a **behavioral diff** that survives model nondeterminism.
- Output a clear CLI report + a Markdown PR-comment report.
- A **GitHub Action** users can add to run it in CI.
- Generate "The Modelpin Report" for a public standard task suite.

**Later (Phase 2–3):** hosted GitHub App (auto-PRs across installed repos), web dashboard, team accounts, billing, "managed migration" auto-fix PRs, more providers/open models.

**Non-goals (protect scope — say no to these):**
- Not a general eval/observability platform (that's Braintrust/LangSmith).
- Not prompt management, not model hosting/gateway, not a tracing vendor.
- Not a leaderboard of "which model is best" — we report *behavior change relative to a user's app*, not absolute model quality.

---

## 4. System architecture (the six machines + glue)

Data flows left to right. Each component is a small, independently testable module.

```
        ┌────────────┐   ┌────────────┐
        │  WATCHER    │   │  DETECTOR  │
        │ model       │   │ scan repo  │
        │ release/    │   │ for model  │
        │ deprecation │   │ strings    │
        └─────┬───────┘   └─────┬──────┘
              │  new model?      │ which models?
              └────────┬─────────┘
                       ▼
                ┌──────────────┐      ┌───────────────┐
                │  SCENARIOS    │─────▶│ REPLAY ENGINE │  (runs scenarios on a model,
                │ user test     │      │ via provider  │   N times, via user's API key)
                │ cases/inputs  │      │ adapters      │
                └──────────────┘      └──────┬────────┘
                       │ baseline traces      │ candidate traces
                       └──────────┬───────────┘
                                  ▼
                        ┌────────────────────┐
                        │  BEHAVIORAL DIFF    │  ← the hard core / the moat
                        │ structural + judge  │
                        │ + nondeterminism    │
                        │ statistics          │
                        └─────────┬──────────┘
                                  ▼
                        ┌────────────────────┐
                        │  REPORTER           │ → CLI output
                        │ render results      │ → Markdown PR comment
                        └─────────┬──────────┘ → public Report page
                                  ▼
                  ┌──────────────────────────────┐
                  │ DELIVERY                      │
                  │ Phase 1: GitHub Action (CI)   │
                  │ Phase 2: GitHub App (auto-PR) │
                  │ Phase 3: Hosted backend + UI  │
                  └──────────────────────────────┘
```

**4.1 Watcher** — knows the state of every model. Sources: provider model-list endpoints (e.g. OpenAI's models list, Anthropic's models list), provider deprecation pages (scraped), and a **community-maintained `data/models.json`** we ship and update. Normalizes to a registry with status + dates. *Verify exact provider endpoints/SDKs at build time — they change.*

**4.2 Detector** — scans a repo for model identifiers in code, config, `.env`, YAML/JSON/TOML. Returns the set of models the project depends on and where. (Reference prior art: the OSS tool "Chowkidar" does this class of thing.)

**4.3 Scenarios** — the user's representative cases. A `scenarios/` folder; each scenario = an input (single prompt or a multi-turn/agent run with tools) + optional assertions (expected tool calls, output schema, must/must-not contain). Lowest-friction onboarding: point Modelpin at the user's existing tests or example inputs and auto-record the current model's behavior as the baseline.

**4.4 Replay Engine** — executes a scenario against a specific model through a **provider adapter**, **N times** (default 3–5), capturing a full **Trace**: messages, tool calls (name + args), final output, refusal flag, token counts, latency. Uses the **end user's own API key** (cost + ToS reasons — see §9).

**4.5 Behavioral Diff (the core — see §6).** Compares baseline traces vs candidate traces and decides per scenario: `unchanged | changed_minor | regression`, with signals, confidence, and a human explanation. Built to **survive nondeterminism** (the make-or-break).

**4.6 Reporter** — renders results three ways: rich CLI summary, Markdown PR comment (the example in §7), and the public Report format.

**Delivery layers** (phased): GitHub **Action** first (no servers), then a hosted **GitHub App** (auto-PRs), then a **backend + dashboard + billing**.

---

## 5. Data models (canonical shapes)

Use typed models (pydantic). Persist as JSON on disk in MVP; Postgres in the hosted phase.

```
Model        { id, provider, family, status: active|deprecated|retired,
               released_at, deprecated_at, replacement_id }

Scenario     { id, name, kind: single|agent, input (messages[], tools[]?),
               assertions[]?  (expected_tool_calls?, output_schema?,
               must_contain[]?, must_not_contain[]?) }

Trace        { scenario_id, model_id, run_idx, messages[], tool_calls[],
               final_output, refused: bool, tokens{in,out}, latency_ms, ts }

Baseline     { scenario_id, model_id, traces[] (N runs), summary_stats }

DiffResult   { scenario_id, from_model, to_model,
               verdict: unchanged|changed_minor|regression,
               signals { tool_call_match, format_valid, refusal_delta,
                         semantic_score, latency_delta, token_delta },
               confidence: 0..1, explanation }

CheckRun     { id, repo, from_model, to_model, results: DiffResult[],
               created_at }                       # hosted phase

# hosted-only
Org/User/Project/Subscription { … standard SaaS + billing fields }
```

---

## 6. The hard core: the Behavioral Diff (this is where the product is won or lost)

Naive text comparison fails because models are **non-deterministic** — identical input yields slightly different output each run, so word-for-word diffing produces constant false alarms. The craft is detecting *real* behavior change while ignoring normal variance. Use **multiple signals + statistics over multiple runs**:

**A. Structural signals (cheap, deterministic):**
- **Tool-call trajectory match** — compare the sequence of tool calls (name + args) baseline vs candidate. Support match modes (strict / unordered / subset / superset). (Solo.io's open-source `agentevals` implements exactly these matchers and is Apache-2.0 — evaluate using it as a dependency or reference rather than reinventing.)
- **Output format/schema validity** — does the output still parse against the expected schema (JSON shape, required fields, regex)? Format drift (e.g., a dropped delimiter) is a top real-world breakage.
- **Refusal detection** — did the model start refusing tasks it used to do? (classifier/regex + a judge fallback).
- **Cheap deltas** — latency and token-count shifts (a proxy for behavior change and a cost regression in their own right).

**B. Semantic signal (LLM-as-judge, used only when text differs):**
- Ask a judge model: "Do these two answers accomplish the same task / mean the same thing?" → score 0–1, low judge temperature. Calibrate the judge on a small labeled set; track its error rate.

**C. Nondeterminism control (the key to low false positives):**
- Run each scenario **N times** on *both* baseline and candidate. Build a small distribution per signal.
- Flag a **regression only when the candidate distribution is meaningfully different from the baseline distribution** (e.g., a simple statistical test / threshold), not when a single sample differs.
- Re-run borderline cases more times before deciding; surface a **confidence** score.

**D. Output:** per scenario → verdict + which signals fired + confidence + a one-line plain-English explanation ("now calls `lookup_order` twice; refusal rate 0%→30%").

**North-star quality metric:** **false-positive rate.** A migration alerter that cries wolf is worthless. Optimize relentlessly for "when Modelpin says it broke, it broke."

---

## 7. The PR / report UX (what the user actually sees)

CLI and PR comment both render the same result. Target PR comment:

```
🚨 Modelpin: model change detected — claude-opus-4-6 → claude-opus-4-7
Replayed 12 scenarios ×5 runs using your API key.

REGRESSIONS (2)
❌ refund_request   tool-call changed: lookup_order called 2× (was 1×).
                    confidence 0.93 — risks double API charge.
❌ angry_customer   refusal rate 0% → 60%: now refuses the cancellation.
                    confidence 0.88.

MINOR CHANGES (1)
⚠️ invoice_parse    output format drift: trailing "$" dropped; still parses.

UNCHANGED (9) ✅

→ Pin to claude-opus-4-6 until resolved, or review the full diff. [link]
```

The **public Modelpin Report** uses the same engine over a fixed, open, public scenario suite, published within hours of each major launch, with reproducible methodology.

---

## 8. Tech stack & key decisions (with rationale)

| Decision | Choice | Why |
|---|---|---|
| Language | **Python 3.12** (single language across CLI, engine, and backend) | Best AI/LLM ecosystem; the agent-builder audience is Python-heavy; `pipx`/`pip` install; fastest for a solo AI-native founder. Keep one language to stay solo-efficient. |
| CLI framework | **Typer** (+ Rich for output) | Minimal, typed, great DX. |
| Data models | **pydantic v2** | Typed shapes, validation, JSON in/out. |
| Provider calls | official SDKs (openai, anthropic, google-genai) behind a thin **adapter interface** | Isolate provider differences; easy to add models; verify current SDKs at build. |
| Trajectory matching | evaluate **`agentevals`** (Apache-2.0) as a dependency | Don't reinvent strict/unordered/subset/superset matchers; spend your effort on the migration trigger + nondeterminism stats + report (your wedge). |
| Tests | **pytest** | Standard. |
| Lint/format | **ruff + black**, full type hints | Clean, reviewable code. |
| Packaging | `pyproject.toml`, publish to PyPI; `pipx install modelpin` | Broad reach. |
| CI delivery (P1) | **GitHub Action** | Zero hosted infra; fastest path to users. |
| Hosted (P2–3) | **FastAPI + Postgres**, GitHub App via webhooks, **Stripe** billing, deploy on Render/Fly | Only when revenue justifies infra. |
| Public site | static site (GitHub Pages / Vercel) | Cheap, fast, SEO. |
| Secrets | env vars + GitHub Actions secrets; **bring-your-own-key**; never commit; encrypt at rest in hosted | Cost, trust, and ToS (see §9). |

**Cost envelope:** fits ~$60/mo — main spend is model API calls during replays (small early; and in CI it's the *user's* key) + a cheap host later. Claude Max covers building.

---

## 9. Legal & trust guardrails (bake these in from day one)

From diligence — these are cheap to honor now and expensive to retrofit:
- **Use the end user's own API keys** for replays. Shifts the provider relationship (and cost) to the user, and avoids the "you accessed our service to benchmark a competitor" ToS framing (providers have revoked access for this).
- **The public Report must be reproducible and framed as measurement/opinion** — "on our open suite, under these settings, we observed…" — never bare claims like "Model X is worse." Open-source the harness + scenarios; let providers reproduce/respond. This neutralizes defamation/disparagement risk.
- **GitHub App acts only on repos that installed it**; never send unsolicited PRs; self-throttle (per-repo hourly PR cap, honor rate limits) to stay within GitHub Acceptable Use.
- **License:** permissive (Apache-2.0 or MIT) for the OSS core; keep the hosted tier's proprietary bits in a separate package.
- **Disclaimers:** "decision-support, verify independently; no warranty." B2B only.

---

## 10. Repository structure

```
modelpin/
├─ pyproject.toml
├─ README.md                 # what it is, install, quickstart, the wedge
├─ CLAUDE.md                 # operational rules for the coding agent (companion file)
├─ LICENSE                   # Apache-2.0
├─ modelpin/
│  ├─ cli.py                 # typer entrypoints: init, scan, baseline, check, report
│  ├─ config.py              # load/validate modelpin.yaml
│  ├─ models.py              # pydantic data models (§5)
│  ├─ watcher/               # model release/deprecation registry
│  ├─ detector/              # scan repo for model strings
│  ├─ scenarios/             # load/define scenarios + assertions
│  ├─ replay/                # run scenarios on a model, capture traces
│  ├─ providers/             # openai.py, anthropic.py, google.py adapters
│  ├─ diff/                  # THE CORE
│  │  ├─ structural.py       # tool-call/format/refusal signals
│  │  ├─ semantic.py         # LLM-judge
│  │  └─ stats.py            # multi-run nondeterminism handling
│  └─ report/                # CLI + Markdown + public-report renderers
├─ actions/                  # GitHub Action wrapper (Phase 1)
├─ examples/                 # a sample agent + scenarios for dogfooding/tests
├─ data/models.json          # the community model registry
├─ docs/                     # public site + Report archive
└─ tests/                    # pytest, incl. golden tests for the diff engine
```

---

## 11. Build roadmap with Definitions of Done

**Phase 0 — Core engine MVP (weeks 0–6).**
Build: `models.py`, providers (≥2: OpenAI + Anthropic), Detector, Scenarios loader, Replay (N runs), Diff (structural + judge + stats), CLI `scan/baseline/check`, Markdown report. Ship `examples/` sample agent.
**DoD:** on a real sample agent, `modelpin check` detects a genuine regression between two real models and prints the PR-style report, with a measured low false-positive rate on a held-out set. Publish **Modelpin Report #1** on the next model release and post it (HN / r/LocalLLaMA / X). *This is also the go/no-go signal.*

**Phase 1 — Lovable OSS + first dollars (months 2–6).**
Build: polish CLI/DX, `pipx` release to PyPI, **GitHub Action**, Watcher automation, the public report site + cadence (a report on *every* launch), launch **hosted Pro** (BYO-key, hosted baselines, alerts).
**DoD:** few-thousand installs/stars; first paying customers; ~$1.5k MRR.

**Phase 2 — GitHub App + teams (months 6–14).**
Build: hosted backend (FastAPI+Postgres), **GitHub App** (auto-PR across installed repos), web dashboard, team accounts, Slack, Stripe.
**DoD:** ~$10k MRR; auto-PRs running for real teams.

**Phase 3 — Business tier + scale (months 14–30).**
Build: Business tier, **managed migration** (auto-generate the fix PR), more providers/open models, SSO.
**DoD:** **$1M ARR** (~1,000 paying accounts).

---

## 12. Success metrics

- **Quality north star:** behavioral-diff **false-positive rate** (lower = trust = adoption).
- **Adoption:** GitHub stars, `pip` installs, weekly-active repos.
- **Distribution:** Modelpin Report reach (views, shares, backlinks) per launch.
- **Business:** free→paid conversion (target 3–4%), MRR, logo count, churn.

---

## 13. Risks & how the build mitigates them

| Risk | Mitigation baked into the plan |
|---|---|
| Incumbent/lab bundles it (esp. Promptfoo/OpenAI) | Be narrower + faster + cross-vendor; own the independent Report brand; serve the long tail they ignore. |
| Devs tolerate the pain | Target the already-burned (agent builders); 2-minute zero-config install; lead with the visceral PR. |
| OSS monetization is hard | Local CLI free forever; charge for hosted convenience + team features. |
| The diff is hard / false positives | It's the core effort; multi-signal + multi-run stats; golden tests; false-positive rate as north star. |
| Provider ToS / access | BYO-key; reproducible, opinion-framed public reports; open harness. |

---

## 14. How to use this pack in Claude Code

1. Create the repo; put **`CLAUDE.md`** (companion file) at the root and this pack in `docs/`.
2. Open the repo in Claude Code. It auto-reads `CLAUDE.md`.
3. Kick off with the first prompt (provided alongside) — start with the data models + Detector + Watcher (the easy machines) to get a working skeleton, then the Replay engine, then invest the bulk of effort in the **Diff** core.
4. Keep scope discipline: when in doubt, re-read §1 (the wedge) and §3 (non-goals). Stay the narrow migration tool.

**Destination restated:** a trusted, open, narrow tool that catches model-migration regressions for developers worldwide, distributed through GitHub, monetized as open-core, on a believable path to $1M ARR — while making your name as the person who built it and writes The Modelpin Report.
