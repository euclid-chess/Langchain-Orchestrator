"""Verify that HTTP delivers the first chunk before the second is produced."""

import asyncio
import socket
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import uvicorn
from langchain_core.runnables import RunnableGenerator

from app.main import create_app


def test_sse_is_delivered_incrementally_over_http() -> None:
    release_second_chunk = threading.Event()

    async def model_stream(prompts: AsyncIterator[Any]) -> AsyncIterator[str]:
        async for _ in prompts:
            yield "first"
            await asyncio.to_thread(release_second_chunk.wait, 4)
            yield "second"

    app = create_app(model=RunnableGenerator(model_stream))
    listen_socket = socket.socket()
    listen_socket.bind(("127.0.0.1", 0))
    listen_socket.listen(5)
    port = listen_socket.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[listen_socket])), daemon=True
    )
    thread.start()

    async def consume() -> None:
        async with httpx.AsyncClient(timeout=2) as client:
            async with client.stream(
                "POST", f"http://127.0.0.1:{port}/ask", json={"query": "Tell me a story"}
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                lines = response.aiter_lines()
                async for line in lines:
                    if line.startswith("data: ") and "first" in line:
                        break
                else:
                    raise AssertionError("No first chunk was received")

                # The model cannot produce the second chunk until after this point.
                release_second_chunk.set()
                async for line in lines:
                    if line.startswith("data: ") and "second" in line:
                        break
                else:
                    raise AssertionError("No second chunk was received")

    try:
        deadline = time.monotonic() + 3
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        asyncio.run(consume())
    finally:
        release_second_chunk.set()
        server.should_exit = True
        thread.join(timeout=5)
        listen_socket.close()
