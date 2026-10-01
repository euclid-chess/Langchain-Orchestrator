# Langorchestrator

A single FastAPI `POST /ask` endpoint that routes questions with LangChain and streams answers as Server-Sent Events (SSE).

For copyable setup, request, testing, and troubleshooting instructions, see [GUIDE.md](GUIDE.md).

## Behavior

- Basic arithmetic (`12 * (5 + 3)`) is calculated locally with a restricted, bounded parser. It makes no LLM request.
- Conceptual math (`Explain calculus`) uses a math-focused LLM chain.
- Other questions use a general LLM chain.
- Both LLM chains share one model instance and stream output chunks asynchronously.
- LLM responses are capped at 512 output tokens to bound latency and cost.

The router uses LangChain `RunnableBranch`; the LLM chains use `ChatPromptTemplate`, a chat model, and `StrOutputParser`. FastAPI's `EventSourceResponse` is a `StreamingResponse` subclass and emits valid SSE, including keepalive comments.
`/ask` is the only application route; the automatic documentation routes are disabled.

## Run locally

Python 3.10+ is required.

```bash
python3.12 -m venv .venv  # Or use another Python 3.10+ interpreter.
source .venv/bin/activate
python -m pip install -e '.[dev]'
export OPENAI_API_KEY='your-key-from-your-provider'
export OPENAI_MODEL='gpt-4o-mini'  # Optional; this is the default.
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The app reads `OPENAI_API_KEY` with `os.getenv` at startup and fails early if it is absent. `.env.example` lists the available settings; `.env` is ignored by Git and is not loaded automatically. Keep the key out of source files and commits.

## Request and response

```bash
curl -N -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"Explain calculus in simple terms"}'
```

The response has `Content-Type: text/event-stream` and sends `token` events as chunks arrive, followed by `done`:

```text
event: token
data: {"text":"Calculus"}

event: token
data: {"text":" studies change..."}

event: done
data: {}
```

For a browser client, use `fetch()` and read its response stream; the browser's native `EventSource` cannot send the required JSON POST body.

## Test

```bash
pytest -q
```

Tests inject a fake streaming model, so they do not require an API key or incur provider charges. They cover local arithmetic, both LLM routes, SSE framing, and invalid input. A live provider test requires a valid key.

## Assumptions and limits

- “Math” includes both calculations and conceptual explanations. Only arithmetic expressions using `+`, `-`, `*`, `/`, `^`/`**`, and parentheses use the local calculator. Other math questions use the math-focused LLM chain.
- Routing is intentionally local and rule-based to avoid a classification API call. Like any rule-based router, it can misclassify ambiguous language; add a measured classifier if real queries justify it.
- Inputs are limited to 2,000 characters. Arithmetic also has limits on expression length, nesting, exponent size, and result magnitude. No user-provided code is executed.
- The endpoint has no user authentication. If exposed publicly, put it behind authentication and rate limits to control provider usage.
- Configure backups and deployment-specific monitoring separately. Streaming responses send a generic `error` event if a failure occurs after response headers have been sent.
