# Vera AI Message Engine

## Overview
This is a deterministic, reasoning-driven backend for Magicpin’s Vera AI challenge. It is designed for high-quality, context-grounded, and production-grade message composition, with a focus on decision quality, traceability, and determinism.

## Architecture

**Layers:**
1. **Signal Extraction**: Extracts structured signals from raw context (merchant, trigger, category, customer).
2. **Decision Engine**: Deterministic rule engine with scoring, rationale trace, and intent selection (no randomness).
3. **Message Blueprint Generator**: Converts decision to a structured message blueprint (with specificity, CTA optimization, constraints).
4. **Controlled LLM Renderer (optional)**: Converts blueprint to natural language (strict prompt, no hallucination, deterministic).

**Key Innovations:**
- Micro-reasoning trace (rationale)
- Specificity engine (injects real numbers, % comparisons, time windows)
- CTA optimizer (binary/open-ended/direct)
- Suppression key design
- State management (history, triggers, merchant state)
- Reply handler intelligence (classifies and maps replies)

## Endpoints
- `POST /v1/context` — Ingest context
- `POST /v1/tick` — Scheduled/time-based events
- `POST /v1/reply` — Handle user replies
- `GET /v1/healthz` — Health check
- `GET /v1/metadata` — Service metadata
- `POST /v1/compose` — (Internal) Compose message from signals

## Output Format
```
{
  "body": "...",
  "cta": "...",
  "send_as": "...",
  "suppression_key": "...",
  "rationale": {...}
}
```

## Determinism & Performance
- All outputs are deterministic for the same inputs
- No hallucinated data
- Response time < 2s

## Running Locally

1. Install dependencies:
   ```bash
   pip install fastapi uvicorn
   ```
2. Start the server:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Test endpoints (e.g. with curl or Postman)

## Deployment
- Can be hosted on Railway, Render, or Fly.io (free tier)
- No paid dependencies

## Extending
- Add SQLite for persistent storage
- Integrate Gemini/HuggingFace API for LLM rendering (strict prompt)
- Add rule-learning or few-shot retrieval modules

## Contact
- Magicpin AI Challenge Team
