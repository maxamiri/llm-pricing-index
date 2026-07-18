"""Concrete OpenRouter provider implementation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd
import requests

from providers.base import BaseProvider

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
TOP_N_MODELS = 30
MILLION = 1_000_000


class OpenRouterProvider(BaseProvider):
    """Fetch and normalize model pricing data from the public OpenRouter API."""

    def __init__(self, timeout: int = 30) -> None:
        """Initialize the provider.

        Args:
            timeout: HTTP request timeout in seconds.
        """
        self._timeout = timeout

    def fetch_model_data(self) -> pd.DataFrame:
        """Fetch, filter, and rank OpenRouter models.

        Returns:
            A DataFrame containing the top ``TOP_N_MODELS`` text-to-text models
            ranked by intelligence index, with parsed per-1M-token prices.
        """
        raw_models = self._fetch_raw_models()
        logger.info("Total models fetched from API: %d", len(raw_models))

        modality_filtered = self._filter_text_to_text(raw_models)
        logger.info("Models after modality filter: %d", len(modality_filtered))

        scored = self._rank_by_intelligence(modality_filtered)
        top_models = scored[:TOP_N_MODELS]
        logger.info("Models after score sort / top-%d: %d", TOP_N_MODELS, len(top_models))

        return self._build_dataframe(top_models)

    def _fetch_raw_models(self) -> List[Dict[str, Any]]:
        """Retrieve the raw model list from the OpenRouter API.

        Raises:
            RuntimeError: If the request fails or the payload is malformed.
        """
        headers = {"Accept": "application/json"}
        try:
            logger.info("Fetching models from %s", OPENROUTER_MODELS_URL)
            response = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Network error while fetching OpenRouter models.")
            raise RuntimeError("Failed to fetch OpenRouter models") from exc

        payload = response.json()
        models = payload.get("data")
        if not isinstance(models, list):
            logger.error("Unexpected payload shape: 'data' key missing or not a list.")
            raise RuntimeError("Malformed OpenRouter response payload")
        return models

    @staticmethod
    def _filter_text_to_text(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep only text-to-text models.

        A model is retained when its ``architecture.output_modalities`` equals
        exactly ``["text"]``, omitting pure multimodal-only output models.
        """
        kept: List[Dict[str, Any]] = []
        for model in models:
            architecture = model.get("architecture", {}) or {}
            output_modalities = architecture.get("output_modalities")
            if output_modalities == ["text"]:
                kept.append(model)
        return kept

    @staticmethod
    def _rank_by_intelligence(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort models by intelligence index, descending.

        Models missing the nested ``benchmarks.artificial_analysis.intelligence_index``
        field default to ``0.0``, naturally sinking to the bottom of the list.
        """
        def _score(model: Dict[str, Any]) -> float:
            benchmarks = model.get("benchmarks", {}) or {}
            aa = benchmarks.get("artificial_analysis", {}) or {}
            index = aa.get("intelligence_index")
            try:
                return float(index) if index is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        return sorted(models, key=_score, reverse=True)

    @staticmethod
    def _build_dataframe(models: List[Dict[str, Any]]) -> pd.DataFrame:
        """Construct the output DataFrame from ranked models.

        Prices are stored as cost per 1,000,000 tokens (USD). Invalid/"-1"
        prices become ``NaN`` and are excluded from blending downstream.
        """
        rows: List[Dict[str, Any]] = []
        for model in models:
            pricing = model.get("pricing", {}) or {}
            input_per_token = BaseProvider._safe_price(pricing.get("prompt"))
            output_per_token = BaseProvider._safe_price(pricing.get("completion"))
            benchmarks = model.get("benchmarks", {}) or {}
            aa = benchmarks.get("artificial_analysis", {}) or {}
            index = aa.get("intelligence_index")
            try:
                score = float(index) if index is not None else 0.0
            except (TypeError, ValueError):
                score = 0.0

            rows.append(
                {
                    "Model Name": model.get("name"),
                    "Model ID": model.get("id"),
                    "Intelligence Index": score,
                    "Raw Input Price": input_per_token * MILLION
                    if not pd.isna(input_per_token)
                    else float("nan"),
                    "Raw Output Price": output_per_token * MILLION
                    if not pd.isna(output_per_token)
                    else float("nan"),
                }
            )

        return pd.DataFrame(rows)
