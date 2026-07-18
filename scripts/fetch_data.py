"""Stage 1 — Data Acquisition.

Fetches the top-30 text-to-text OpenRouter models, parses their raw per-1M
token prices, and persists the intermediate DataFrame to
``report/<date>/assets/raw_model_data.csv``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from providers.openrouter import OpenRouterProvider  # noqa: E402
from scripts.common import (  # noqa: E402
    assets_dir,
    configure_logging,
    parse_date_args,
    resolve_date,
)

logger = logging.getLogger(__name__)


def run(run_date: str) -> Path:
    """Execute Stage 1 for the given run date.

    Args:
        run_date: ISO date string (YYYY-MM-DD) identifying the run.

    Returns:
        Path to the written raw_model_data.csv file.
    """
    provider = OpenRouterProvider()
    df = provider.fetch_model_data()
    logger.info("Stage 1 produced %d rows for date %s.", len(df), run_date)

    out_dir = assets_dir(run_date)
    out_path = out_dir / "raw_model_data.csv"
    df.to_csv(out_path, index=False)
    logger.info("Wrote raw model data to %s", out_path)
    return out_path


def main() -> None:
    """CLI entrypoint for Stage 1."""
    configure_logging()
    parser = parse_date_args("Stage 1: fetch and persist raw OpenRouter model data.")
    args = parser.parse_args()
    run_date = resolve_date(args)

    run(run_date)


if __name__ == "__main__":
    main()
