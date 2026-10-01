import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.runnables import RunnableGenerator

from app.main import create_app


def fake_model() -> RunnableGenerator:
    async def generate(prompts: AsyncIterator[Any]) -> AsyncIterator[str]:
        async for prompt in prompts:
            system_message = prompt.to_messages()[0].content
            if "mathematics tutor" in system_message:
                yield "MATH "
            else:
                yield "GENERAL "
            await asyncio.sleep(0)
            yield "answer"

    return RunnableGenerator(generate)


def parse_events(body: str) -> list[tuple[str, Any]]:
    parsed = []
    event = "message"
    data = None
    for line in body.splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = json.loads(line.removeprefix("data: "))
        elif not line and data is not None:
            parsed.append((event, data))
            event, data = "message", None
    return parsed


async def post_query(query: str) -> httpx.Response:
    app = create_app(model=fake_model())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            return await client.post("/ask", json={"query": query})


def test_local_math_returns_sse_without_model_call() -> None:
    response = asyncio.run(post_query("What is 12 * (5 + 3)?"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert parse_events(response.text) == [
        ("token", {"text": "96"}),
        ("done", {}),
    ]


def test_conceptual_math_streams_through_math_chain() -> None:
    response = asyncio.run(post_query("Explain calculus in simple terms"))
    assert parse_events(response.text) == [
        ("token", {"text": "MATH "}),
        ("token", {"text": "answer"}),
        ("done", {}),
    ]


def test_general_query_streams_through_general_chain() -> None:
    response = asyncio.run(post_query("Why is the sky blue?"))
    assert parse_events(response.text) == [
        ("token", {"text": "GENERAL "}),
        ("token", {"text": "answer"}),
        ("done", {}),
    ]


def test_everyday_use_of_add_is_not_treated_as_math() -> None:
    response = asyncio.run(post_query("Add this book to my reading list"))
    assert parse_events(response.text)[0] == ("token", {"text": "GENERAL "})


def test_written_out_arithmetic_uses_math_chain() -> None:
    response = asyncio.run(post_query("What is seven times eight?"))
    assert parse_events(response.text)[0] == ("token", {"text": "MATH "})


def test_blank_query_is_rejected_before_streaming() -> None:
    response = asyncio.run(post_query("   "))
    assert response.status_code == 422


def test_provider_error_is_redacted_after_stream_starts() -> None:
    async def failing_model(prompts: AsyncIterator[Any]) -> AsyncIterator[str]:
        async for _ in prompts:
            yield "partial"
            raise RuntimeError("secret-provider-error-123")

    async def run() -> httpx.Response:
        app = create_app(model=RunnableGenerator(failing_model))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver"
            ) as client:
                return await client.post("/ask", json={"query": "Explain calculus"})

    response = asyncio.run(run())
    assert "secret-provider-error-123" not in response.text
    assert parse_events(response.text) == [
        ("token", {"text": "partial"}),
        ("error", {"message": "Unable to complete the request."}),
    ]
