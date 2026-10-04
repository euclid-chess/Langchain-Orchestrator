"""Provider selection is configuration, not part of the public API."""

import asyncio

import pytest
from langchain_core.runnables import RunnableLambda

from app import models
from app.main import create_app


def test_model_settings_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    with pytest.raises(RuntimeError, match="MODEL_PROVIDER and MODEL_NAME"):
        models.load_model()


def test_model_settings_are_passed_to_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", " AnThRoPiC ")
    monkeypatch.setenv("MODEL_NAME", " chosen-model ")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    selected = RunnableLambda(lambda _: "answer")
    calls: list[tuple[str, str]] = []

    def init(name: str, *, model_provider: str):
        calls.append((name, model_provider))
        return selected

    monkeypatch.setattr(models, "init_chat_model", init)
    assert models.load_model() is selected
    assert calls == [("chosen-model", "anthropic")]


def test_app_loads_one_model_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = RunnableLambda(lambda _: "answer")
    calls = 0

    def load():
        nonlocal calls
        calls += 1
        return selected

    monkeypatch.setattr("app.main.load_model", load)
    app = create_app()

    async def start() -> None:
        async with app.router.lifespan_context(app):
            assert app.state.router is not None

    asyncio.run(start())
    assert calls == 1
