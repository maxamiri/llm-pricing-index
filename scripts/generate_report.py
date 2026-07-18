"""Stage 3 — AI-Authored Report.

Invokes the opencode CLI non-interactively to write a LinkedIn-ready trends
report grounded in the generated CSV and charts, saving it to
``report/<date>/README.md``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import (  # noqa: E402
    configure_logging,
    parse_date_args,
    report_dir,
    resolve_date,
    sync_reports_index,
)

logger = logging.getLogger(__name__)


def _build_prompt(run_date: str) -> str:
    """Construct the report-writing prompt for the opencode agent."""
    return f"""You are a professional AI/LLM industry analyst. Write a concise, data-grounded trends/news-style report on current LLM pricing, in a professional tone suitable for publishing as a LinkedIn post. No slang, no emoji spam, no clickbait — use a clear, industry-analyst voice.

GROUNDING RULE: Every figure you cite MUST come from the attached CSV file (llm_cost_index_{run_date}.csv). Do NOT invent, estimate, or guess any numbers that are not present in that data. If a claim cannot be supported by the CSV, omit it.

The attached charts (chart_balanced_1_1.png, chart_standard_8_2.png, chart_coding_9_1.png) visualize the three blended-cost profiles described below.

REQUIRED STRUCTURE:
1. A strong, professional headline.
2. A short intro hook (2-3 sentences) framing why LLM pricing literacy matters.
3. A methodology blurb (one paragraph) explaining the three blended-cost profiles:
   - Balanced Profile (1:1): 50% input / 50% output tokens.
   - Standard Text Profile (8:2): 80% input / 20% output tokens (RAG, chatbots, summarization).
   - Coding Profile (9:1): 90% input / 10% output tokens (large codebases ingested as input, concise completions).
   Blended Cost per 1M tokens = (Input Price per 1M * input %) + (Output Price per 1M * output %).
4. A findings section for EACH profile: name the cheapest models, the most expensive models, and note notable price spreads or outliers, using real numbers from the CSV.
5. A short closing takeaway (2-3 sentences).

EMBEDDING CHARTS: Reference the three charts using RELATIVE Markdown image links so the report renders from within its own folder:
- ![Balanced 1:1](assets/chart_balanced_1_1.png)
- ![Standard 8:2](assets/chart_standard_8_2.png)
- ![Coding 9:1](assets/chart_coding_9_1.png)

OUTPUT: Write your final report directly to report/{run_date}/README.md using your own file-write tool. Do not return the report as chat text only — it must be written to that file."""


def _required_files(run_date: str) -> List[Path]:
    """Return the list of files the agent needs (CSV + 3 charts)."""
    assets = report_dir(run_date) / "assets"
    csv = assets / f"llm_cost_index_{run_date}.csv"
    charts = [
        assets / "chart_balanced_1_1.png",
        assets / "chart_standard_8_2.png",
        assets / "chart_coding_9_1.png",
    ]
    return [csv, *charts]


def generate(run_date: str, model: str) -> Path:
    """Invoke opencode to author the report.

    Args:
        run_date: ISO date string identifying the run.
        model: The opencode provider/model spec (e.g. "anthropic/claude-...).

    Returns:
        Path to the written README.md.

    Raises:
        FileNotFoundError: If Stage 2 outputs are missing.
        RuntimeError: If opencode fails or does not produce a non-empty README.
    """
    required = _required_files(run_date)
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Stage 2 outputs missing: " + ", ".join(missing) + ". Run Stage 2 first."
        )

    prompt = _build_prompt(run_date)
    # The `-f` flag is an array type and greedily consumes following positionals,
    # so the prompt MUST come before the file flags to avoid being treated as a
    # file path.
    cmd: List[str] = ["opencode", "run", "--model", model, prompt]
    for f in required:
        cmd += ["-f", str(f)]

    logger.info("Invoking opencode with model %s", model)
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("opencode executable not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        logger.error("opencode exited with error:\n%s", exc.stderr)
        raise RuntimeError("opencode run failed") from exc

    logger.debug("opencode stdout:\n%s", result.stdout)

    readme = report_dir(run_date) / "README.md"
    if not readme.exists() or readme.stat().st_size == 0:
        raise RuntimeError(
            f"Report not produced at {readme}. opencode did not write a non-empty file."
        )

    logger.info("Report written to %s", readme)
    return readme


def main() -> None:
    """CLI entrypoint for Stage 3."""
    configure_logging()
    parser = parse_date_args("Stage 3: generate the AI-authored LLM pricing report.")
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("REPORT_MODEL", ""),
        help="opencode provider/model spec (e.g. 'anthropic/claude-...'). "
        "Falls back to REPORT_MODEL env var.",
    )
    args = parser.parse_args()
    run_date = resolve_date(args)

    if not args.model:
        raise SystemExit(
            "No report model specified. Pass --model or set REPORT_MODEL."
        )

    generate(run_date, args.model)
    sync_reports_index()


if __name__ == "__main__":
    main()
