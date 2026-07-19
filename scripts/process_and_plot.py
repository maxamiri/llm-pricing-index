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

# Solid, commercial-grade single-hue-per-chart palette (no per-bar rainbow
# gradients) -- each chart gets one flat color from a fixed categorical set.
VALUE_SCORE_COLOR = "#2a78d6"  # blue
INTELLIGENCE_COLOR = "#008300"  # green

# Value-score (intelligence-per-dollar) chart config. This is the report's
# "winner" chart, so it's generated and presented first.
VALUE_SCORE_CHART = {
    "file": "chart_value_score.png",
    "title": "Value Score - Intelligence per Blended-Dollar (best = 100%)",
    "label": "Value Score (%)",
}

# Intelligence-only leaderboard chart config (companion to the value-score
# chart now that per-profile cost charts no longer carry an intelligence
# overlay -- see _plot_profile).
INTELLIGENCE_CHART = {
    "file": "chart_intelligence.png",
    "title": "Intelligence Index by Model",
    "label": "Intelligence Index",
}

# Filename for the value-score leaderboard CSV.
VALUE_SCORE_CSV = "value_scores_{run_date}.csv"

# Filename + chart title + solid color per profile.
CHART_CONFIG: Dict[str, Dict[str, str]] = {
    "1:1": {
        "file": "chart_balanced_1_1.png",
        "title": "Balanced Profile (1:1) - Blended Cost per 1M Tokens",
        "label": "Balanced (1:1)",
        "color": "#eb6834",  # orange
    },
    "8:2": {
        "file": "chart_standard_8_2.png",
        "title": "Standard Text Profile (8:2) - Blended Cost per 1M Tokens",
        "label": "Standard Text (8:2)",
        "color": "#4a3aa7",  # violet
    },
    "9:1": {
        "file": "chart_coding_9_1.png",
        "title": "Coding Profile (9:1) - Blended Cost per 1M Tokens",
        "label": "Coding (9:1)",
        "color": "#e34948",  # red
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

    # Value score: 3 * intelligence per summed blended-dollar. Dividing by the
    # sum of all three profile costs (rather than the average) under-weights
    # the score, so multiply by 3 to recover intelligence-per-average-cost.
    # Normalized proportionally (value / max * 100) so the best
    # intelligence-per-dollar model maps to 100% and every other model keeps
    # its true relative proportion -- this does NOT floor the lowest to an
    # absolute 0 (min-max would); a model only reads 0% if its raw value is
    # genuinely 0 (i.e. unscored intelligence).
    #
    # A $0 (free-tier) model would divide-by-zero here, poisoning the raw
    # score with inf and turning every other model's normalized score into
    # 0 or NaN. Treat free models as the ceiling case (best possible value)
    # instead: they're excluded from the finite max used to normalize the
    # rest, and pinned to 100% directly.
    cost_columns = [f"{p} Blended Cost" for p in PROFILES]
    df["Total Blended Cost"] = df[cost_columns].sum(axis=1)
    is_free = df["Total Blended Cost"] <= 0
    df["Value Score (raw)"] = pd.Series(index=df.index, dtype=float)
    df.loc[~is_free, "Value Score (raw)"] = (
        3.0 * df.loc[~is_free, "Intelligence Index"] / df.loc[~is_free, "Total Blended Cost"]
    )
    df.loc[is_free, "Value Score (raw)"] = float("inf")

    finite_raw = df.loc[~is_free, "Value Score (raw)"]
    max_raw = finite_raw.max() if not finite_raw.empty else 0.0
    df["Value Score (%)"] = 0.0
    if max_raw:
        df.loc[~is_free, "Value Score (%)"] = (
            df.loc[~is_free, "Value Score (raw)"] / max_raw * 100.0
        )
    df.loc[is_free, "Value Score (%)"] = 100.0

    column_order = [
        "Model Name",
        "Intelligence Index",
        "Raw Input Price",
        "Raw Output Price",
        "1:1 Blended Cost",
        "8:2 Blended Cost",
        "9:1 Blended Cost",
        "Total Blended Cost",
        "Value Score (raw)",
        "Value Score (%)",
    ]
    df = df[column_order]

    out_path = assets / f"llm_cost_index_{run_date}.csv"
    df.to_csv(out_path, index=False)
    logger.info("Wrote blended cost index to %s", out_path)
    return df


def value_scores(run_date: str, df: pd.DataFrame) -> pd.DataFrame:
    """Write the value-score leaderboard CSV, ranked best choice first.

    The leaderboard is ordered by descending normalized value score, so the
    strongest intelligence-per-dollar model appears at the top.

    Args:
        run_date: ISO date string identifying the run.
        df: The enriched Stage 2 DataFrame (must include value-score columns).

    Returns:
        The leaderboard DataFrame, sorted best-first.
    """
    leaderboard = df[
        [
            "Model Name",
            "Intelligence Index",
            "Total Blended Cost",
            "Value Score (raw)",
            "Value Score (%)",
        ]
    ].copy()
    leaderboard = leaderboard.sort_values(by="Value Score (%)", ascending=False)

    out_path = assets_dir(run_date) / VALUE_SCORE_CSV.format(run_date=run_date)
    leaderboard.to_csv(out_path, index=False)
    logger.info("Wrote value-score leaderboard to %s", out_path)
    return leaderboard


def _bar_chart(
    plot_df: pd.DataFrame,
    x_col: str,
    y_col: str,
    color: str,
    title: str,
    ylabel: str,
    xlabel: str,
    out_path: Path,
    fmt: str,
    ylim: tuple[float, float] | None = None,
) -> Path:
    """Render one flat-color vertical bar chart. Shared by every chart here.

    A single solid hue per chart (rather than a per-bar gradient) keeps the
    charts calm and legible on a white page instead of reading as neon.
    """
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(14, 7))

    ax.bar(plot_df[x_col], plot_df[y_col], color=color)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xlabel(xlabel, fontsize=11)
    if ylim is not None:
        ax.set_ylim(*ylim)
    plt.setp(ax.get_xticklabels(), rotation=60, ha="right", fontsize=8)

    for container in ax.containers:
        ax.bar_label(container, fmt=fmt, padding=2, fontsize=7, rotation=90)

    plt.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote chart %s", out_path)
    return out_path


def _plot_profile(df: pd.DataFrame, profile: str, run_date: str) -> Path:
    """Render a single-series vertical bar chart of one profile's blended cost.

    Bars are sorted ascending by the profile's own blended cost, left to
    right, so the cheapest model is leftmost and the most expensive is
    rightmost. Sized to a fixed landscape aspect ratio that fills a typical
    HTML page/article width.
    """
    column = f"{profile} Blended Cost"
    cfg = CHART_CONFIG[profile]
    plot_df = df.sort_values(by=column, ascending=True).reset_index(drop=True)

    return _bar_chart(
        plot_df,
        x_col="Model Name",
        y_col=column,
        color=cfg["color"],
        title=cfg["title"],
        ylabel="Blended Cost (USD per 1M tokens)",
        xlabel="Model (cheapest → most expensive)",
        out_path=assets_dir(run_date) / cfg["file"],
        fmt="$%.2f",
    )


def _plot_value_score(df: pd.DataFrame, run_date: str) -> Path:
    """Render the value-score leaderboard chart -- the report's "winner" chart.

    Bars are sorted ascending by normalized value score, left to right, so the
    weakest intelligence-per-dollar model is leftmost and the best choice
    (100%) is rightmost.
    """
    cfg = VALUE_SCORE_CHART
    plot_df = df.sort_values(by="Value Score (%)", ascending=True).reset_index(
        drop=True
    )

    return _bar_chart(
        plot_df,
        x_col="Model Name",
        y_col="Value Score (%)",
        color=VALUE_SCORE_COLOR,
        title=cfg["title"],
        ylabel="Value Score (normalized, best = 100%)",
        xlabel="Model (lowest → highest value)",
        out_path=assets_dir(run_date) / cfg["file"],
        fmt="%.1f",
        ylim=(0, 105),
    )


def _plot_intelligence(df: pd.DataFrame, run_date: str) -> Path:
    """Render the intelligence-only leaderboard chart.

    Companion to the value-score chart: with the intelligence overlay removed
    from the three cost charts, this is where readers see which model wins on
    raw intelligence alone. Sorted ascending, left to right.
    """
    cfg = INTELLIGENCE_CHART
    plot_df = df.sort_values(by="Intelligence Index", ascending=True).reset_index(
        drop=True
    )

    return _bar_chart(
        plot_df,
        x_col="Model Name",
        y_col="Intelligence Index",
        color=INTELLIGENCE_COLOR,
        title=cfg["title"],
        ylabel="Intelligence Index (Artificial Analysis)",
        xlabel="Model (lowest → highest intelligence)",
        out_path=assets_dir(run_date) / cfg["file"],
        fmt="%.0f",
    )


def generate_charts(df: pd.DataFrame, run_date: str) -> List[Path]:
    """Generate all five charts, in report presentation order:

    1. Value score (the "winner" chart -- intelligence per dollar).
    2. Intelligence-only leaderboard.
    3-5. The three per-profile blended-cost charts.

    Returns the list of written paths.
    """
    paths = [_plot_value_score(df, run_date), _plot_intelligence(df, run_date)]
    paths.extend(_plot_profile(df, profile, run_date) for profile in PROFILES)
    return paths


def main() -> None:
    """CLI entrypoint for Stage 2."""
    configure_logging()
    parser = parse_date_args("Stage 2: compute blended costs and render charts.")
    args = parser.parse_args()
    run_date = resolve_date(args)

    df = process(run_date)
    generate_charts(df, run_date)
    value_scores(run_date, df)
    logger.info("Stage 2 complete for %s.", run_date)


if __name__ == "__main__":
    main()
