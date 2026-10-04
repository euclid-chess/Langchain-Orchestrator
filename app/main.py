"""FastAPI entry point for a single, streaming /ask endpoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import load_model
from app.routing import build_router

logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)

    @field_validator("query")
    @classmethod
    def reject_blank_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


def create_app(model: Runnable[Any, Any] | None = None) -> FastAPI:
    """Create the app, optionally injecting any compatible streaming model."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        selected_model = model if model is not None else load_model()
        app.state.router = build_router(selected_model)
        yield

    app = FastAPI(
        title="Langorchestrator",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.post("/ask", response_class=EventSourceResponse)
    async def ask(payload: AskRequest) -> AsyncIterator[ServerSentEvent]:
        try:
            async for chunk in app.state.router.astream({"query": payload.query}):
                if chunk:
                    yield ServerSentEvent(event="token", data={"text": str(chunk)})
            yield ServerSentEvent(event="done", data={})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not put upstream errors, queries, or credentials on the wire.
            logger.error("Request stream failed (%s)", type(exc).__name__)
            yield ServerSentEvent(
                event="error", data={"message": "Unable to complete the request."}
            )

    return app


app = create_app()
