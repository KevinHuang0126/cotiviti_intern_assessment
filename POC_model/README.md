# policy-as-rule — POC Model

Self-critiquing LLM compiler for healthcare coverage policies. Weekend hackathon POC supporting the Cotiviti intern assessment (Topic 3).

## What it does

1. **Compile** — Read a CMS coverage-policy section and emit an executable rule with verbatim citations.
2. **Self-verify** — Run Compiler → Adversary → Fixer until adversarial tests pass or budget is hit.
3. **Diff** — Compare two compiled rules (v1 vs v2) for structural changes and behavioral claim flips.

Demo policy: **NCD 210.14** (Lung Cancer Screening with LDCT), versions CAG-00439N (2015) and CAG-00439R (2022).

## Quick start

```bash
cd POC_model
make install
make test
make demo          # replay mode (no API key needed)
make demo-live     # requires ANTHROPIC_API_KEY
```

For live mode, copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` (the `.env` is gitignored and loaded automatically).

Open the Gradio UI at `http://127.0.0.1:7860`.

## Layout

```
POC_model/
├── data/                 # Policy text and coverage sections
├── src/                  # Core pipeline
├── tests/                # Engine, canonicalize, diff tests
├── cache/llm/            # LLM response cache
├── runs/                 # Per-run transcripts
└── scripts/              # Pre-flight and cache utilities
```

## Demo mode

- `--demo-mode replay` — Replays cached LLM responses from `cache/llm/golden/` (deterministic recording).
- `--demo-mode live` — Calls Anthropic API (`claude-sonnet-5` for Compiler/Fixer, `claude-haiku-4-5` for Adversary).

## Headline claim flip

A 52-year-old former smoker with 22 pack-years (quit 8 years ago) applying for LDCT:

| Version | Decision |
|---------|----------|
| NCD 210.14 v1 (2015) | **DENIED** (age ≥ 55, pack-years ≥ 30) |
| NCD 210.14 v2 (2022) | **APPROVED** (age ≥ 50, pack-years ≥ 20) |

## Production path

JSON Logic is the POC compilation target. Production would use **CQL + Da Vinci DTR/CRD**.
