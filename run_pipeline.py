"""Pipeline orchestrator.

Computes a single run date once and invokes Stage 1, Stage 2, and Stage 3 in
order, passing that same date to each stage.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

logger = logging.getLogger(__name__)

from scripts.common import (  # noqa: E402
    configure_logging,
    parse_date_args,
    resolve_date,
    sync_reports_index,
)
from scripts.fetch_data import run as stage1  # noqa: E402
from scripts.process_and_plot import main as stage2_main  # noqa: E402
from scripts.generate_report import main as stage3_main  # noqa: E402


def _run_stage(script_main, date_arg: str) -> None:
    """Invoke a stage's main() with the resolved date injected via argv."""
    sys.argv = ["stage", "--date", date_arg]
    script_main()


def run(run_date: str, report_model: Optional[str] = None) -> None:
    """Run the full pipeline for a single date.

    Args:
        run_date: ISO date string identifying the run.
        report_model: Optional opencode model spec for Stage 3.
    """
    logger.info("=== Pipeline start for date %s ===", run_date)

    logger.info("--- Stage 1: fetch data ---")
    stage1(run_date)

    logger.info("--- Stage 2: process & plot ---")
    _run_stage(stage2_main, run_date)

    logger.info("--- Stage 3: generate report ---")
    model = report_model or os.getenv("REPORT_MODEL", "")
    if not model:
        logger.warning(
            "Skipping Stage 3: no report model. Set REPORT_MODEL or pass --model."
        )
    else:
        sys.argv = ["stage", "--date", run_date, "--model", model]
        stage3_main()

    sync_reports_index()
    logger.info("=== Pipeline complete for date %s ===", run_date)


def main() -> None:
    """CLI entrypoint for the orchestrator."""
    configure_logging()
    parser = parse_date_args("Orchestrate the full LLM pricing pipeline.")
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("REPORT_MODEL", ""),
        help="opencode provider/model spec for Stage 3 (falls back to REPORT_MODEL).",
    )
    args = parser.parse_args()
    run_date = resolve_date(args)
    run(run_date, report_model=args.model)


if __name__ == "__main__":
    main()
