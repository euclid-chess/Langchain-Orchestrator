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

## Routing and performance choices

**Local, rule-based routing avoids a classification-model request.** LangChain's outer `RunnableBranch` checks whether the query looks mathematical; its math branch then checks whether the *whole query* is a supported arithmetic expression. The decisions are, in order:

1. A complete expression such as `12 * (5 + 3)` or `What is 12 * (5 + 3)?` goes to the local calculator.
2. Other queries containing math terms (for example, `Explain calculus`), calculation words paired with digits or written-out numbers (for example, `What is seven times eight?`), or a numeric operator go to the math-tutor prompt and LLM.
3. Everything else goes to the general prompt and LLM. `Add this book to my reading list` is general: the word “add” alone is not enough to classify it as math.

These checks use a bounded expression parser and case-insensitive regular expressions, not semantic understanding. They are cheap and deterministic, but ambiguous wording can choose the wrong prompt. Written-out arithmetic is routed to the math LLM, not evaluated locally. See `is_math_query` and `is_direct_calculation` in [`app/routing.py`](app/routing.py).

**The local calculator avoids an LLM request for supported arithmetic.** It parses an expression into a Python syntax tree, evaluates only approved arithmetic nodes with `Decimal`, and never executes user-supplied Python. Limits on expression length, tree size, nesting, exponents, and value magnitude bound the work. This path is narrower than general math reasoning: an unsupported word problem still needs the LLM. The current router parses a direct expression more than once; with the small input limit this is minor overhead, not a claimed optimal parser implementation.

**The model and router are built once at startup.** Both LLM paths reuse the configured LangChain model object rather than rebuilding it per request. This avoids repeated setup in the application, but does not necessarily warm a provider connection or eliminate network latency. Each path uses a short, task-specific system prompt plus the user's query, keeping prompt overhead modest without claiming a measured saving.

**Asynchronous SSE streaming reduces time to visible output.** The endpoint iterates over `router.astream(...)` and yields each nonempty chunk through `EventSourceResponse` as a `token` event, then emits `done`. It does not wait to assemble the whole answer. A chunk need not equal one model token, and the benefit depends on a provider that truly streams; streaming does not necessarily reduce the time to *finish* the answer. Awaiting an asynchronous provider also lets the server handle other work while a response is in progress. The 2,000-character query limit bounds input processing and prompt size, but is not a model-token cap.

These are design choices, not benchmark results. Measure first-chunk latency, total latency, and concurrent-request behavior with the intended provider and deployment before making speed claims or adding a more complex classifier.

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
