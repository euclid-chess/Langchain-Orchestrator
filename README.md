# Langorchestrator

A single FastAPI `POST /ask` endpoint that routes questions with LangChain and streams answers as Server-Sent Events (SSE).

For copyable setup, request, testing, and troubleshooting instructions, see [GUIDE.md](GUIDE.md).

## Behavior

- Basic arithmetic (`12 * (5 + 3)`) is calculated locally with a restricted, bounded parser. It makes no LLM request.
- Conceptual math (`Explain calculus`) uses a math-focused LLM chain.
- Other questions use a general LLM chain.
- Both LLM chains share one model instance and stream output chunks asynchronously.
- Choose the model provider and model at server startup; OpenAI is not required.

The router uses LangChain `RunnableBranch`; the LLM chains use `ChatPromptTemplate`, a chat model, and `StrOutputParser`. FastAPI's `EventSourceResponse` is a `StreamingResponse` subclass and emits valid SSE, including keepalive comments.
`/ask` is the only application route; the automatic documentation routes are disabled.

## Run locally

Python 3.10+ is required. This example selects OpenAI; see [GUIDE.md](GUIDE.md) for a local Ollama example and other providers.

```bash
python3.12 -m venv .venv  # Or use another Python 3.10+ interpreter.
source .venv/bin/activate
python -m pip install -e '.[dev,openai]'
export MODEL_PROVIDER=openai
export MODEL_NAME=gpt-4o-mini
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
echo
export OPENAI_API_KEY
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`MODEL_PROVIDER` and `MODEL_NAME` are required; there is no default provider. Install the selected provider's LangChain integration (`openai`, `anthropic`, and `ollama` extras are supplied), and provide its credentials only if needed. A compatible LangChain model can also be injected with `create_app(model=...)`. `.env.example` lists the settings, but `.env` is ignored by Git and is not loaded automatically. Never commit credentials.

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

Tests inject a fake streaming model, so they do not require provider credentials or incur model charges. They cover provider selection, local arithmetic, both LLM routes, SSE framing, and invalid input. Verify true chunking with the provider and model you select; not every model integration streams incrementally.

## Assumptions and limits

- “Math” includes both calculations and conceptual explanations. Only arithmetic expressions using `+`, `-`, `*`, `/`, `^`/`**`, and parentheses use the local calculator. Other math questions use the math-focused LLM chain.
- Routing is intentionally local and rule-based to avoid a classification API call. Like any rule-based router, it can misclassify ambiguous language; add a measured classifier if real queries justify it.
- Model selection happens once at startup, not per request. Different providers have different credential, streaming, output-length, timeout, and retry behavior; there is no provider-independent 512-token cap.
- Inputs are limited to 2,000 characters. Arithmetic also has limits on expression length, nesting, exponent size, and result magnitude. No user-provided code is executed.
- The endpoint has no user authentication. If exposed publicly, put it behind authentication and rate limits to control provider usage.
- Configure backups and deployment-specific monitoring separately. Streaming responses send a generic `error` event if a failure occurs after response headers have been sent.
