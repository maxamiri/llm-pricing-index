"""Abstract base class defining the provider interface for LLM pricing data."""

from __future__ import annotations

import abc
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class BaseProvider(abc.ABC):
    """Abstract interface that every pricing data provider must implement."""

    @abc.abstractmethod
    def fetch_model_data(self) -> pd.DataFrame:
        """Fetch, filter, and rank model pricing data.

        Returns:
            A pandas DataFrame containing the top models with parsed raw
            input/output prices (per 1M tokens, USD) and a capability score.
        """
        raise NotImplementedError

    @staticmethod
    def _safe_float(value: Optional[str], default: float = 0.0) -> float:
        """Convert a possibly-malformed string price into a float safely.

        Args:
            value: The raw string value (e.g. "0.000001" or "-1").
            default: Value returned when parsing fails or the input is invalid.

        Returns:
            The parsed float, or ``default`` when the value cannot be used.
        """
        if value is None:
            return default
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            logger.debug("Could not parse value %r as float; using default.", value)
            return default
        if parsed < 0:
            # Negative pricing (e.g. "-1") signals variable/router pricing.
            return default
        return parsed

    @staticmethod
    def _safe_price(value: Optional[str]) -> float:
        """Parse a per-token USD price string, returning NaN for invalid input.

        Unlike ``_safe_float``, a negative value (the OpenRouter sentinel
        "-1" for variable/router pricing) maps to ``NaN`` rather than 0.0,
        so that downstream blended-cost math cannot silently treat an unknown
        price as free. Parse failures also yield ``NaN``.

        Args:
            value: The raw price string (e.g. "0.000001" or "-1").

        Returns:
            The per-token price as a float, or ``float("nan")`` when invalid.
        """
        if value is None:
            return float("nan")
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            logger.debug("Could not parse price %r; setting NaN.", value)
            return float("nan")
        if parsed < 0:
            # "-1" sentinel: variable/router pricing, exclude from blending.
            return float("nan")
        return parsed
