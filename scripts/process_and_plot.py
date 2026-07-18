"""Stage 2 — Processing & Chart Generation.

Loads the raw model data, computes blended costs for three workload profiles,
writes ``llm_cost_index_<date>.csv``, and renders three bar charts.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import (  # noqa: E402
    assets_dir,
    configure_logging,
    parse_date_args,
    resolve_date,
)

logger = logging.getLogger(__name__)

# Blended-cost profiles: (input fraction, output fraction).
PROFILES: Dict[str, Dict[str, float]] = {
    "1:1": {"input": 0.50, "output": 0.50},
    "8:2": {"input": 0.80, "output": 0.20},
    "9:1": {"input": 0.90, "output": 0.10},
}

# Filename + chart title per profile.
CHART_CONFIG: Dict[str, Dict[str, str]] = {
    "1:1": {
        "file": "chart_balanced_1_1.png",
        "title": "Balanced Profile (1:1) - Blended Cost per 1M Tokens",
        "label": "Balanced (1:1)",
    },
    "8:2": {
        "file": "chart_standard_8_2.png",
        "title": "Standard Text Profile (8:2) - Blended Cost per 1M Tokens",
        "label": "Standard Text (8:2)",
    },
    "9:1": {
        "file": "chart_coding_9_1.png",
        "title": "Coding Profile (9:1) - Blended Cost per 1M Tokens",
        "label": "Coding (9:1)",
    },
}


def _blended_cost(df: pd.DataFrame, profile: str) -> pd.Series:
    """Compute the blended cost column for a given profile."""
    weights = PROFILES[profile]
    return (
        df["Raw Input Price"] * weights["input"]
        + df["Raw Output Price"] * weights["output"]
    )


def process(run_date: str) -> pd.DataFrame:
    """Load raw data, compute blended costs, and return the enriched DataFrame.

    Args:
        run_date: ISO date string identifying the run.

    Returns:
        The blended-cost DataFrame.

    Raises:
        FileNotFoundError: If the raw data CSV for the date is missing.
    """
    assets = assets_dir(run_date)
    raw_path = assets / "raw_model_data.csv"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Raw data file not found at {raw_path}. Run Stage 1 (fetch_data.py) first."
        )

    df = pd.read_csv(raw_path)
    logger.info("Loaded %d rows from %s", len(df), raw_path)

    before = len(df)
    df = df.dropna(subset=["Raw Input Price", "Raw Output Price"]).copy()
    logger.info("Dropped %d rows with invalid (NaN) pricing.", before - len(df))

    for profile in PROFILES:
        column = f"{profile} Blended Cost"
        df[column] = _blended_cost(df, profile)

    column_order = [
        "Model Name",
        "Raw Input Price",
        "Raw Output Price",
        "1:1 Blended Cost",
        "8:2 Blended Cost",
        "9:1 Blended Cost",
    ]
    df = df[column_order]

    out_path = assets / f"llm_cost_index_{run_date}.csv"
    df.to_csv(out_path, index=False)
    logger.info("Wrote blended cost index to %s", out_path)
    return df


def _plot_profile(df: pd.DataFrame, profile: str, run_date: str) -> Path:
    """Render a single vertical bar chart for one profile.

    Bars are sorted ascending by the profile's own blended cost, left to
    right, so the cheapest model is leftmost and the most expensive is
    rightmost. Sized to a fixed landscape aspect ratio that fills a typical
    HTML page/article width rather than growing with the model count.
    """
    column = f"{profile} Blended Cost"
    cfg = CHART_CONFIG[profile]
    plot_df = df.sort_values(by=column, ascending=True)

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(14, 7))

    palette = sns.color_palette("viridis", n_colors=len(plot_df))
    ax.bar(plot_df["Model Name"], plot_df[column], color=palette)

    ax.set_title(cfg["title"], fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Blended Cost (USD per 1M tokens)", fontsize=11)
    ax.set_xlabel("Model (cheapest → most expensive)", fontsize=11)
    plt.setp(ax.get_xticklabels(), rotation=60, ha="right", fontsize=8)

    for container in ax.containers:
        ax.bar_label(container, fmt="$%.2f", padding=2, fontsize=7, rotation=90)

    plt.tight_layout()

    assets = assets_dir(run_date)
    out_path = assets / cfg["file"]
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote chart %s", out_path)
    return out_path


def generate_charts(df: pd.DataFrame, run_date: str) -> List[Path]:
    """Generate all three profile charts. Returns the list of written paths."""
    return [_plot_profile(df, profile, run_date) for profile in PROFILES]


def main() -> None:
    """CLI entrypoint for Stage 2."""
    configure_logging()
    parser = parse_date_args("Stage 2: compute blended costs and render charts.")
    args = parser.parse_args()
    run_date = resolve_date(args)

    df = process(run_date)
    generate_charts(df, run_date)
    logger.info("Stage 2 complete for %s.", run_date)


if __name__ == "__main__":
    main()
