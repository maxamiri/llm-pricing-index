"""Shared helpers for pipeline stages: date resolution and report paths."""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_ROOT = REPO_ROOT / "report"


def parse_date_args(description: str) -> argparse.ArgumentParser:
    """Build an ArgumentParser that accepts an optional ``--date`` flag.

    Args:
        description: Help text describing the stage.

    Returns:
        A configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Run date in YYYY-MM-DD format (default: today).",
    )
    return parser


def resolve_date(args: argparse.Namespace) -> str:
    """Validate and return the resolved run date string.

    Args:
        args: Parsed CLI arguments containing a ``date`` attribute.

    Returns:
        The validated ISO date string.

    Raises:
        ValueError: If the date string is not valid ISO format.
    """
    raw = args.date
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid --date value {raw!r}; expected YYYY-MM-DD.") from exc
    return parsed.isoformat()


def assets_dir(run_date: str) -> Path:
    """Return the assets directory Path for a given run date."""
    path = REPORT_ROOT / run_date / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_dir(run_date: str) -> Path:
    """Return the report directory Path for a given run date."""
    path = REPORT_ROOT / run_date
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging with a consistent format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


REPORTS_START_MARKER = "<!-- REPORTS:START -->"
REPORTS_END_MARKER = "<!-- REPORTS:END -->"


def sync_reports_index() -> None:
    """Regenerate the report list in the root README.md, newest first.

    Rewrites only the block between ``REPORTS_START_MARKER`` and
    ``REPORTS_END_MARKER`` so the rest of the README is left untouched. Only
    dated folders that contain a ``README.md`` (i.e. Stage 3 completed) are
    listed, since a folder with just data/charts isn't a "report" yet.
    """
    readme_path = REPO_ROOT / "README.md"
    if not readme_path.exists():
        logger.warning("No root README.md found; skipping report index sync.")
        return

    dated_dirs = [p for p in REPORT_ROOT.glob("*") if p.is_dir() and (p / "README.md").exists()]
    dated_dirs.sort(key=lambda p: p.name, reverse=True)

    if dated_dirs:
        lines = [
            f"- [{p.name}](report/{p.name}/README.md)" + (" _(latest)_" if i == 0 else "")
            for i, p in enumerate(dated_dirs)
        ]
        block = "\n".join(lines)
    else:
        block = "_No reports generated yet. Run `python run_pipeline.py` to create one._"

    content = readme_path.read_text()
    start = content.find(REPORTS_START_MARKER)
    end = content.find(REPORTS_END_MARKER)
    if start == -1 or end == -1:
        logger.warning("README.md is missing the REPORTS markers; skipping index sync.")
        return

    new_content = (
        content[: start + len(REPORTS_START_MARKER)]
        + "\n"
        + block
        + "\n"
        + content[end:]
    )
    readme_path.write_text(new_content)
    logger.info("Synced report index into README.md (%d report(s)).", len(dated_dirs))
