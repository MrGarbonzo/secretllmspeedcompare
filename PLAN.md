# LLM Speed Compare — PLAN.md

A side-by-side streaming demo comparing SecretAI vs. Groq (both running Llama 3.3 70B).
Built to show that privacy-preserving inference (via SecretAI / TEE) is not significantly
slower than a standard cloud-hosted model.

---

## Goals

- Honest, real-world speed comparison — no throttling, no tricks
- Looks credible to developers AND polished enough for marketing
- Reusable demo asset for Secret Network outreach / partner meetings

---

## Stack

| Layer     | Choice                        | Reason                                      |
|-----------|-------------------------------|---------------------------------------------|
| Backend   | Python / FastAPI              | Matches existing SecretOrNot pattern        |
| Frontend  | Single HTML file, vanilla JS  | No build step, easy to demo anywhere        |
| Streaming | SSE (Server-Sent Events)      | Native browser support, simple to proxy     |
| Model A   | Llama 3.3 70B via SecretAI    | Privacy-preserving, TEE-hosted              |
| Model B   | Llama 3.3 70B via Groq        | Fast public baseline, 280 T/sec             |
| Protocol  | OpenAI-compatible on both     | Same calling code for both sides            |

Groq is chosen as the public baseline because it is genuinely fast — this keeps the
delta between the two providers small, making the "not significantly slower" argument
as strong as possible.

Llama 3.3 70B is used because it is the only model available on both SecretAI and Groq.
It is also a stronger demo model — production-grade, impressive for live audiences,
and longer responses make the TTFT delta proportionally smaller.

---

## Architecture

```
Browser
  |
  |-- fetch POST /stream/a  --->  FastAPI  --->  Provider A (configured via .env)
  |-- fetch POST /stream/b  --->  FastAPI  --->  Provider B (configured via .env)
  |
  Both fetches fired simultaneously in the same JS tick (fair race)
```

Both backend routes use identical code — only env vars differ.
Keys never leave the server.

---

## Environment Configuration

Both providers are fully configurable via .env — URL, model string, and API key.
No provider is hardcoded anywhere in the application code.

```
# Provider A (default: SecretAI)
PROVIDER_A_BASE_URL=https://secretai-rytn.scrtlabs.com:21434
PROVIDER_A_API_KEY=...
PROVIDER_A_MODEL=llama3.3:70b
PROVIDER_A_LABEL=SecretAI

# Provider B (default: Groq)
PROVIDER_B_BASE_URL=https://api.groq.com/openai/v1
PROVIDER_B_API_KEY=...
PROVIDER_B_MODEL=llama-3.3-70b-versatile
PROVIDER_B_LABEL=Groq
```

This means:
- Swapping providers requires only an .env change — no code edits
- The demo can be repurposed for any two OpenAI-compatible endpoints
- UI labels are also env-driven so the frontend always reflects what is configured

---

## Timing Methodology

- **Primary metric**: Time to First Token (TTFT)
  - Clock starts the moment the frontend fires the fetch
  - Clock stops (and freezes) the moment the first chunk arrives
- **Secondary metric**: Total completion time (tracked, displayed, but not headlined)
- The backend hop inflates both timers equally (~1-2ms) — the delta stays accurate
- Both requests fire in the same JS event tick — no staggering, fair race

---

## Streaming Approach

We call the raw OpenAI-compatible HTTP endpoint directly via the `openai` Python client
with `stream=True`. We do NOT use the SecretAI SDK or LangChain.

- Identical calling code for both providers — only config values differ
- SecretAI confirmed: HTTPS only, requires Authorization header, served via Caddy
- SecretAI endpoint confirmed responding at port 21434 with standard OpenAI chunk format
- Verify in Phase 1 that chunks arrive token-by-token and are not buffered

---

## Backend — Phase 1

**File structure:**
```
C:\dev\llmspeedcompare\
  backend\
    main.py          # FastAPI app
    .env             # API keys and config (gitignored)
    requirements.txt
  frontend\
    index.html       # Single file, all JS inline
  PLAN.md
  .gitignore
```

**Routes:**
- `POST /stream/a` — proxies to Provider A, streams SSE back to browser
- `POST /stream/b` — proxies to Provider B, streams SSE back to browser
- `GET /config`    — returns `{ label_a, label_b, model_a, model_b }` for UI
- `GET /`          — serves index.html (or Nginx handles this)

**Request body (both stream routes):**
```json
{ "prompt": "..." }
```

**Response:** `text/event-stream` SSE, standard OpenAI chunk format:
```
data: {"choices": [{"delta": {"content": "..."}}]}
data: [DONE]
```

---

## Frontend — Phase 1 (Simple)

- On load: fetch `/config`, set panel headings from returned labels
- Single text input + submit button
- Two `<div>` panels side by side
- On submit: fire both fetch calls simultaneously
- Each panel shows:
  - A live ms timer counting up from 0
  - "First token: Xms" badge — freezes when first chunk arrives
  - Streaming text as chunks arrive
- No framework, no bundler, no dependencies

---

## Frontend — Phase 2 (Visual Polish)

Reference: secretai.com homepage (screenshot on file)

### Color Palette

| Token            | Hex       | Usage                                      |
|------------------|-----------|--------------------------------------------|
| --color-bg       | #FDF5EE   | Page background (warm cream)               |
| --color-accent   | #E8431C   | Primary CTA, highlights, SecretAI panel    |
| --color-dark     | #1C1C1C   | Dark sections, footer bar, text            |
| --color-text     | #2A2A2A   | Body copy, panel text                      |
| --color-muted    | #6B6B6B   | Secondary labels, subtitles                |
| --color-panel-a  | #FDF5EE   | SecretAI panel background (warm, on-brand) |
| --color-panel-b  | #F0F4F8   | Groq panel background (cool, neutral)      |
| --color-border   | #E8DDD4   | Panel borders, dividers                    |

### Typography
- Headlines: bold/black weight, modern sans-serif (Inter or system-ui)
- Timers: monospace, very large, cinematic — this is the emotional focal point
- Labels: uppercase, tight letter-spacing for badge text

### Layout & Components
- Page header: SecretAI logo + wordmark top left, tagline top right
- Two panels side by side, equal width, subtle border radius
- Panel A (SecretAI): accent-colored top border, lock/shield icon, "TEE Protected" badge
  modeled after the site's "Encrypted / Verified / Isolated" badge language
- Panel B (Groq): neutral top border, cloud icon, "Standard Cloud" label
- Timers: large monospace numbers, counting up in ms, freeze on first token
  displayed prominently at the top of each panel — the race is the visual core
- "First token" badge animates in when TTFT is captured
- Verdict banner: animates in after both streams complete
  e.g. "SecretAI was only Xms slower — with full privacy"
  styled like the dark stats bar on the site (#1C1C1C background, white text)
- Prompt suggestion chips below the input box so audiences don't blank

### Tone
- Panel A copy: "TEE Protected", "Encrypted", "Verifiable" — mirror the site's badge language
- Panel B copy: "Standard Cloud", "Unencrypted" — neutral, not disparaging
- Verdict: confident, not boastful — let the numbers speak

---

## Deployment

- Fits the existing `attestai.io` Nginx + FastAPI pattern
- Candidate subdomain: `compare.attestai.io`
- `proxy_buffering off` required in Nginx for SSE to stream correctly (same as SecretOrNot)
- `.env` stays on server, never committed

---

## Resolved

- [x] SecretAI base URL: https://secretai-rytn.scrtlabs.com:21434 (HTTPS only, Caddy)
- [x] SecretAI model string: llama3.3:70b
- [x] Groq model string: llama-3.3-70b-versatile
- [x] Groq base URL: https://api.groq.com/openai/v1
- [x] Model parity confirmed: Llama 3.3 70B available on both providers
- [x] Visual theme: SecretAI homepage color palette and design language

## Open Questions

- [ ] Verify raw HTTP streaming is chunk-by-chunk on SecretAI (first task in Phase 1)
- [ ] Decide: serve frontend via FastAPI static files, or separate Nginx block?

---

## Phase Checklist

- [ ] Phase 1 — Backend: two SSE proxy routes, env-driven config, requirements.txt
- [ ] Phase 2 — Frontend simple: two panels, live timers, streaming text
- [ ] Phase 3 — Verify timing accuracy, test with real prompts
- [ ] Phase 4 — Frontend visual polish (Phase 2 ideas above)
- [ ] Phase 5 — Deploy to compare.attestai.io
