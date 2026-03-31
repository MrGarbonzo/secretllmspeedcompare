"""
LLM Speed Compare — FastAPI backend.
Proxies streaming chat completions from two providers via SSE.
Provider A (SecretAI): models discovered dynamically via secret-ai-sdk.
Provider B (Together AI): fixed model from env vars.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from openai import AsyncOpenAI
from secret_ai_sdk.secret import Secret

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Provider A (SecretAI) — dynamic via SDK
# ---------------------------------------------------------------------------
os.environ.setdefault("SECRET_AI_API_KEY", os.environ.get("PROVIDER_A_API_KEY", ""))

secret_client = Secret()
SECRET_AI_API_KEY = os.environ["PROVIDER_A_API_KEY"]
SECRET_AI_LABEL = os.environ.get("PROVIDER_A_LABEL", "SecretAI")

# Discovered at startup, refreshable
secret_models: list[str] = []
secret_urls: dict[str, str] = {}  # model -> base_url

# ---------------------------------------------------------------------------
# Provider B (Together AI) — fixed from env
# ---------------------------------------------------------------------------
PROVIDER_B = {
    "base_url": os.environ["PROVIDER_B_BASE_URL"],
    "api_key": os.environ["PROVIDER_B_API_KEY"],
    "model": os.environ["PROVIDER_B_MODEL"],
    "label": os.environ.get("PROVIDER_B_LABEL", "Together AI"),
}

_b_url = PROVIDER_B["base_url"].rstrip("/")
CLIENT_B = AsyncOpenAI(
    base_url=_b_url if _b_url.endswith("/v1") else _b_url + "/v1",
    api_key=PROVIDER_B["api_key"],
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="LLM Speed Compare")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _discover_models():
    """Fetch models from SecretAI SDK and cache their URLs."""
    global secret_models, secret_urls
    all_models = secret_client.get_models()

    # Filter to chat-capable models (exclude voice/special-purpose)
    skip = {"stt-whisper", "tts-kokoro", "solidity-llm"}
    chat_models = [m for m in all_models if m not in skip]

    urls = {}
    for m in chat_models:
        try:
            model_urls = secret_client.get_urls(model=m)
            if model_urls:
                urls[m] = model_urls[0]
        except Exception:
            pass

    # Put gemma3:4b first as the default
    model_list = list(urls.keys())
    if "gemma3:4b" in model_list:
        model_list.remove("gemma3:4b")
        model_list.insert(0, "gemma3:4b")
    secret_models = model_list
    secret_urls = urls
    logger.info(f"SecretAI models discovered: {secret_models}")


def _get_client_a(model: str) -> tuple[AsyncOpenAI, str]:
    """Get an OpenAI client for a SecretAI model."""
    base_url = secret_urls.get(model)
    if not base_url:
        raise ValueError(f"Unknown model: {model}")
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return AsyncOpenAI(base_url=url, api_key=SECRET_AI_API_KEY), model


@app.on_event("startup")
async def startup():
    """Discover models and warm up the first one."""
    _discover_models()

    if secret_models:
        try:
            client, model = _get_client_a(secret_models[0])
            stream = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                stream=True,
            )
            async for _ in stream:
                pass
            logger.info(f"Warmup complete for {model}")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")


# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------
async def _stream_secret_ai(model: str, prompt: str):
    """Yield SSE chunks from SecretAI for the given model."""
    client, model_name = _get_client_a(model)

    stream = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        content = delta.content if delta else None
        if content is not None:
            yield f"data: {content}\n\n"

    yield "data: [DONE]\n\n"


async def _stream_together(prompt: str):
    """Yield SSE chunks from Together AI."""
    stream = await CLIENT_B.chat.completions.create(
        model=PROVIDER_B["model"],
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        content = delta.content if delta else None
        if content is not None:
            yield f"data: {content}\n\n"

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/stream/a")
async def stream_a(request: Request):
    body = await request.json()
    model = body.get("model", secret_models[0] if secret_models else "")
    return StreamingResponse(
        _stream_secret_ai(model, body["prompt"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/stream/b")
async def stream_b(request: Request):
    body = await request.json()
    return StreamingResponse(
        _stream_together(body["prompt"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/")
async def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/models")
async def get_models():
    return JSONResponse({"models": secret_models})


@app.get("/config")
async def config():
    return JSONResponse({
        "label_a": SECRET_AI_LABEL,
        "label_b": PROVIDER_B["label"],
        "model_b": PROVIDER_B["model"],
    })
