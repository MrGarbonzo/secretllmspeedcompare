"""
Minimal streaming test — connects to SecretAI and prints each chunk with a timestamp.
Verifies that the endpoint streams token-by-token and does not buffer.
All config loaded from .env (no hardcoded credentials).
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load .env from the same directory as this script
load_dotenv(Path(__file__).parent / ".env")

base_url = os.environ["PROVIDER_A_BASE_URL"]
api_key = os.environ["PROVIDER_A_API_KEY"]
model = os.environ["PROVIDER_A_MODEL"]

print(f"Connecting to: {base_url}")
print(f"Model: {model}")
print("-" * 60)

effective_url = base_url.rstrip("/") if base_url.rstrip("/").endswith("/v1") else base_url.rstrip("/") + "/v1"
client = OpenAI(base_url=effective_url, api_key=api_key)

t0 = time.perf_counter()
first_token_time = None

stream = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "What is the capital of France? Answer in one sentence."}],
    stream=True,
)

for chunk in stream:
    now = time.perf_counter()
    elapsed_ms = (now - t0) * 1000

    delta = chunk.choices[0].delta if chunk.choices else None
    content = delta.content if delta else None

    if content:
        if first_token_time is None:
            first_token_time = elapsed_ms
            print(f"\n[{elapsed_ms:8.1f} ms] FIRST TOKEN: {content!r}")
        else:
            print(f"[{elapsed_ms:8.1f} ms] {content!r}")

total_ms = (time.perf_counter() - t0) * 1000
print("-" * 60)
print(f"TTFT:  {first_token_time:.1f} ms")
print(f"Total: {total_ms:.1f} ms")
