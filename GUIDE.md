# Using and testing Langorchestrator

This guide covers the project as it is currently implemented. The service accepts one JSON question at `POST /ask`, chooses a math or general-answer path with LangChain, and sends the answer as Server-Sent Events (SSE). The API has no other application endpoint.

## 1. Get ready

You need Python 3.10 or newer, `pip`, `curl`, and an OpenAI API key for **live** requests. A live LLM request needs network access and may cost money. The automated tests use a fake model and need neither a key nor provider access.

Open a terminal in the repository folder. If you are elsewhere, change to the path where **you** saved it; for example:

```bash
cd /path/to/langorchestrator
```

If a `.venv` already exists, activate it and install the project and test dependencies:

```bash
source .venv/bin/activate
python --version
python -m pip install -e '.[dev]'
```

If `.venv` is missing, create it first with a Python 3.10+ interpreter, then run those commands. For example, if `python3.12` is installed:

```bash
python3.12 -m venv .venv
```

Check the interpreter's version before creating a virtual environment. Some systems still use a Python older than 3.10 for the `python3` command.

## 2. Supply the key and start the server

In the **same terminal**, enter the key at a hidden prompt and export it. You may optionally set `OPENAI_MODEL` before the `uvicorn` command; its default is `gpt-4o-mini`.

```bash
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
echo
export OPENAI_API_KEY
# Optional: export OPENAI_MODEL='gpt-4o-mini'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The key is read from the environment when the app starts. It is required even if you plan to send only arithmetic questions, because the shared LLM is initialized at startup.

`.env.example` documents the variables, but the app does **not** load a `.env` file automatically. An ignored `.env` file by itself will not configure the server. Do not put a real key in source code, a commit, screenshots, or a shared terminal transcript.

The server listens only on your machine at `http://127.0.0.1:8000`. Leave this terminal running while testing. Press `Ctrl+C` to stop it.

## 3. Send requests and see the stream

Open a **second terminal**. These commands work without activating the virtual environment because they use `curl`. The `-N` option tells `curl` to display incoming data immediately instead of buffering it.

Fast, local arithmetic (no LLM call for this request):

```bash
curl -N -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is 12 * (5 + 3)?"}'
```

Its answer is deterministic. Expect a `token` event containing `{"text":"96"}`, followed by `done`:

```text
event: token
data: {"text":"96"}

event: done
data: {}
```

Conceptual math (math-focused LLM chain):

```bash
curl -N -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"Explain calculus in simple terms"}'
```

General knowledge (general LLM chain):

```bash
curl -N -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"Why is the sky blue?"}'
```

For LLM answers, the wording and number/size of `token` events vary. Each event carries a JSON object with a `text` field. Append those `text` values in order to reconstruct the answer. A token event is **not** guaranteed to be exactly one word or one model token. The stream ends with `event: done` and `data: {}`. You may also see SSE keepalive comment lines during a quiet period; they are not answer text.

The response content type is `text/event-stream`. It is an HTTP response that stays open while events arrive, so the caller can see the beginning of an LLM answer before the rest is finished. Browser `EventSource` cannot send the required JSON POST; a browser client should use `fetch()` and read/parse its response stream.

### Invalid input and errors

Try an empty question:

```bash
curl -i -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"   "}'
```

The request is rejected with HTTP `422` and a JSON validation response, **before** SSE starts. A missing `query`, a non-string value, extra JSON fields, or more than 2,000 characters is also rejected. Valid questions are trimmed before routing.

If processing fails **after** streaming has started, the server sends an SSE `error` event with the generic message `Unable to complete the request.` It does not send the upstream error or the query to the client. The HTTP status may already be `200` because the response headers were sent before the failure; clients must check for `error`, not only the status code. Disconnecting a client cancels its stream.

## 4. Run the automated tests

From the repository directory, with `.venv` activated:

```bash
python -m pytest -q
```

The current suite has 17 tests. It checks arithmetic and its safety limits, math/general routing, input validation, SSE event formatting, error redaction, and actual incremental HTTP delivery. The incremental test uses a fake model that withholds its second chunk until the client has received the first, so it tests streaming behavior rather than merely checking a completed response. These tests do **not** prove that your particular key, model, network, or provider account works; run the live `curl` examples above for that.

## How it works, without jargon

```text
JSON question → input checks → LangChain router
                               ├─ simple arithmetic → local calculator → SSE answer
                               ├─ other math → math prompt + shared LLM → SSE chunks
                               └─ general → general prompt + shared LLM → SSE chunks
```

1. `app/main.py` defines the one FastAPI endpoint and checks that `query` is a nonblank string of at most 2,000 characters. It creates one reusable chat model and router at startup rather than rebuilding them for every request. The model is configured for streaming, at most 512 output tokens, a 30-second timeout, and one retry.
2. `app/routing.py` builds a LangChain `RunnableBranch`. Its first decision is math versus general, using local text rules. Inside the math branch, a second decision sends supported arithmetic directly to the calculator; other math questions get a math-tutor prompt and the LLM. General questions get a concise-answer prompt and the same LLM instance. `StrOutputParser` turns LLM output into text.
3. `app/math_tools.py` accepts only a whole, simple arithmetic expression, optionally prefixed by phrases such as “what is” or “calculate.” It parses the expression into a syntax tree and evaluates permitted arithmetic nodes with `Decimal`; it does **not** run user-supplied Python code. Supported operations are `+`, `-`, `*`, `/`, and `^`/`**`, with parentheses and decimals. It limits expression length, tree size, nesting, exponent, and value magnitude. A recognized expression that cannot be evaluated safely produces a short explanatory answer rather than running unsafe input. Text that does not match the calculator's expression format follows the other routing rules.
4. Back in `app/main.py`, `router.astream(...)` produces answer pieces asynchronously. FastAPI's `EventSourceResponse`—a `StreamingResponse` subclass—sends each nonempty piece as an SSE `token` event, then sends `done`. This lets the LLM and network make progress without waiting for the entire answer to be assembled.

Routing is intentionally rule-based to avoid a separate classification-model request on every question. “Explain calculus” is math and goes to the math LLM chain, even though it is not an arithmetic calculation. An ambiguous question may still be misrouted. For example, natural-language arithmetic such as “What is seven times eight?” is recognized as math but does not match the local expression parser, so the math LLM answers it. The LLM may make mistakes; the local calculator is for the narrow supported expression format, not all mathematical reasoning.

## Practical limits and troubleshooting

- **Server will not start:** Check `python --version` and confirm `OPENAI_API_KEY` was exported in the terminal that starts Uvicorn. Installing packages or having a `.env` file does not set that variable.
- **No visible stream:** Use `curl -N`; check that the server is still running. Model/network latency can occur before the first chunk, and intermediaries may buffer SSE in a deployed setup.
- **Unexpected route:** The router uses keywords and expression shape, not deep semantic understanding. Inspect `app/routing.py` and add representative tests before changing rules.
- **Public deployment:** The endpoint has no authentication or rate limiting. Keep the example bound to `127.0.0.1`; put authentication, quotas/rate limits, and appropriate monitoring in front of it before exposing it to other users.

The repository is local and has not been pushed to GitHub. The optional Loom walkthrough script is in `docs/loom-walkthrough.md`; it is a script, not a recorded video.
