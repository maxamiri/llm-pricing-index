# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A provider-agnostic pipeline that tracks OpenRouter LLM pricing, computes blended cost-per-1M-tokens under three workload profiles, charts it, and has an AI agent (`opencode`) write a LinkedIn-ready trends report from the results.

## Public repo — no PII, secrets, or machine-identifying info

This repo is public and open source. Nothing committed here — code, generated reports/CSVs/charts, commit messages, or this file — should contain:
- Personal information (real names, emails, usernames) beyond what's already in the public git history/GitHub org.
- API keys, tokens, or credentials of any kind (none are needed — OpenRouter's endpoint is public/unauthenticated, and opencode's own provider credentials live in the *host machine's* opencode config, never in this repo).
- Local machine details: absolute filesystem paths (e.g. `/Users/<name>/...` or `/home/<name>/...`), hostnames, OS/environment specifics, or anything else that identifies the machine or account a run happened on.

Before committing generated output (new `report/<date>/` folders, regenerated charts/CSVs), check it's clean of the above — e.g. `grep -rn "/Users/\|/home/"` over new/changed files, and a quick look at chart PNGs for embedded paths (rare with matplotlib, but check if something looks off). When writing scripts, never log or embed absolute local paths into files that get committed (`report/`-scoped relative paths are fine; full local filesystem paths are not).

## "Update the pricing for me"

This is the single most common request in this repo. It means: run the full pipeline for today (or a given date) and produce a fresh `report/<date>/` folder.

```bash
source .venv/bin/activate
python run_pipeline.py                       # full pipeline, defaults to today
python run_pipeline.py --date 2026-07-18      # specific date
python run_pipeline.py --model anthropic/claude-sonnet-4-20250514   # explicit Stage 3 model
```

- Stage 3 (AI report) needs a model spec via `--model` or the `REPORT_MODEL` env var (`provider/model`, opencode format). If neither is set, `run_pipeline.py` logs a warning and **skips Stage 3** rather than failing — Stages 1–2 (data + charts) still complete. If the user just wants updated numbers/charts without a fresh report, that's fine as-is; otherwise ask which model to use.
- After a successful run, `run_pipeline.py` also refreshes the "Reports" list in the root `README.md` (between the `<!-- REPORTS:START -->` / `<!-- REPORTS:END -->` markers) so it always points at the latest dated report — no manual README edits needed after a pipeline run.
- Each stage is also independently re-runnable with its own `--date`, useful for redoing just one part (e.g. re-plot without re-fetching, or regenerate only the report):
  ```bash
  python scripts/fetch_data.py --date 2026-07-18
  python scripts/process_and_plot.py --date 2026-07-18
  python scripts/generate_report.py --date 2026-07-18 --model <provider/model>
  ```
- Re-running a stage for a date that already has output overwrites the files in that date's `assets/` folder (and `README.md` for Stage 3) — there's no versioning across re-runs of the same date.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

No API key or `.env` file is needed: OpenRouter's `/api/v1/models` endpoint is public and unauthenticated, and `OpenRouterProvider` sends no auth header. Set `REPORT_MODEL` in your shell to avoid passing `--model` to Stage 3 every time. There is no test suite in this repo currently.

## Architecture

Three independently runnable stages, chained by `run_pipeline.py`, all writing into a single date-scoped folder so every run is self-contained and reproducible:

```
Stage 1 (scripts/fetch_data.py)       → report/<date>/assets/raw_model_data.csv
Stage 2 (scripts/process_and_plot.py) → report/<date>/assets/llm_cost_index_<date>.csv
                                       → report/<date>/assets/chart_{balanced_1_1,standard_8_2,coding_9_1}.png
Stage 3 (scripts/generate_report.py)  → report/<date>/README.md
```

`scripts/common.py` holds the shared `--date` CLI parsing and the `assets_dir()`/`report_dir()` path helpers every stage uses — this is what keeps all three stages agreeing on where a given run's files live. `report/` is **committed** (not gitignored) — each dated run is a permanent, published entry in the repo's report archive, not disposable build output.

**Stage 1 — provider layer.** `providers/base.py` defines `BaseProvider` (abstract `fetch_model_data() -> pd.DataFrame`), so a second data source could be added later without touching Stages 2–3. `providers/openrouter.py` is the only implementation: fetches `https://openrouter.ai/api/v1/models`, keeps only `architecture.output_modalities == ["text"]` models, ranks by `benchmarks.artificial_analysis.intelligence_index` (missing on most models — defaults to `0.0`, which is what pushes unscored models to the bottom rather than raising), and takes the top `TOP_N_MODELS` (currently 30 — see `providers/openrouter.py`). Pricing parsing treats the API's `"-1"` sentinel (variable/router pricing, e.g. `openrouter/auto`) as `NaN`, not `0`, so it can't silently blend as free.

**Stage 2 — blending & charts.** Blended cost = `input_price * input_frac + output_price * output_frac` for three profiles defined in `PROFILES` in `scripts/process_and_plot.py`: 1:1 (balanced), 8:2 (standard text / RAG), 9:1 (coding). Charts are vertical bars, sorted ascending left→right (cheapest model leftmost, most expensive rightmost), rendered at a **fixed** `figsize=(14, 7)` regardless of model count — this was deliberately changed from a per-model-scaled `figsize` (which produced unreadable 2000px+-tall portrait images) to a fixed landscape size that fills a normal HTML/article width.

**Stage 3 — AI report.** Shells out to the `opencode` CLI (`opencode run --model <provider/model> -f <csv> -f <png> ... "<prompt>"`), attaching the Stage 2 CSV and all three charts as files rather than pasting data into the prompt, and instructing the agent to write `report/<date>/README.md` directly with its own file tools (not to return the report as stdout — opencode's terminal output includes progress/tool-call logs that aren't safe to parse as the report body). The prompt (`_build_prompt` in `scripts/generate_report.py`) enforces a grounding rule: every number in the report must come from the attached CSV, nothing invented. opencode's own provider credentials (for whatever `--model` you pass) are a machine-level opencode config concern, unrelated to this repo.
