# LLM Pricing Index

A provider-agnostic pipeline that tracks [OpenRouter](https://openrouter.ai) LLM pricing, computes **blended cost per 1M tokens** under three realistic workload profiles, charts it, and has an AI agent draft a publish-ready trends report from the results.

Raw per-token input/output prices are misleading on their own — production workloads consume input and output tokens in very different ratios depending on the use case. This project blends the two into a single comparable number under three profiles:

| Profile | Ratio | Represents |
|---|---|---|
| Balanced | 1:1 | Vendor-neutral baseline |
| Standard Text | 8:2 | RAG, chatbots, summarization |
| Coding | 9:1 | Large context in, concise completions out |

`Blended Cost per 1M tokens = (Input Price × input %) + (Output Price × output %)`

On top of the three cost profiles, each run also computes a **Value Score** — intelligence per blended dollar — so the report can lead with "which model is the best deal" rather than just raw prices:

`Value Score (raw) = 3 × Intelligence Index / (1:1 + 8:2 + 9:1 Blended Cost)`, normalized so the best intelligence-per-dollar model scores 100% and every other model keeps its true relative proportion.

(Intelligence Index comes from OpenRouter's [Artificial Analysis](https://artificialanalysis.ai) benchmark field, where available.)

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python run_pipeline.py                  # fetch + process + chart (+ AI report, if configured)
```

No API key is required — OpenRouter's `/api/v1/models` endpoint is public. To also generate the AI-authored report (Stage 3), install [opencode](https://opencode.ai) and set a model:

```bash
export REPORT_MODEL=anthropic/claude-sonnet-4-20250514   # any opencode-supported provider/model
python run_pipeline.py
```

Without `REPORT_MODEL`/`--model`, the pipeline still runs Stages 1–2 (fresh data + charts) and simply skips the report.

## Pipeline

```
Stage 1  scripts/fetch_data.py        → report/<date>/assets/raw_model_data.csv
Stage 2  scripts/process_and_plot.py  → report/<date>/assets/llm_cost_index_<date>.csv
                                       → report/<date>/assets/value_scores_<date>.csv
                                       → report/<date>/assets/chart_{value_score,intelligence,balanced_1_1,standard_8_2,coding_9_1}.png
Stage 3  scripts/generate_report.py   → report/<date>/README.md
```

Each stage is independently re-runnable with `--date YYYY-MM-DD`. See [`CLAUDE.md`](CLAUDE.md) for architecture details.

## Reports

<!-- REPORTS:START -->
- [2026-07-19](report/2026-07-19/README.md) _(latest)_
- [2026-07-18](report/2026-07-18/README.md)
<!-- REPORTS:END -->

## License

Apache License 2.0 — see [LICENSE](LICENSE).
