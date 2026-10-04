"""Select one LangChain chat model from trusted server-side settings."""

from __future__ import annotations

import os
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.runnables import Runnable


def load_model() -> Runnable[Any, Any]:
    """Create the configured model once at application startup."""
    provider = os.getenv("MODEL_PROVIDER", "").strip().lower()
    name = os.getenv("MODEL_NAME", "").strip()
    if not provider or not name:
        raise RuntimeError("MODEL_PROVIDER and MODEL_NAME must be set before starting the app")
    return init_chat_model(name, model_provider=provider)
