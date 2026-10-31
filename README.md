# Support & Logistics Assistant

Customer-support chatbot for orders, refunds and complaints. FastAPI, LangGraph, MongoDB Atlas,
Gemini (free tier), Stripe test mode with a Stripe-shaped fake behind the same interface, and a vanilla HTML/CSS/JS
frontend served by the same FastAPI process (one Render service, same-origin cookies, no CORS).

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill MONGODB_URL, GOOGLE_API_KEY, JWT_SECRET_KEY
python -m scripts.seed      # demo users + orders
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000. Demo logins: `user@example.com / UserPass123`, `admin@example.com / AdminPass123`.
Tests (no network, no database needed): `pytest`.

## Setup you must do yourself
1. **MongoDB Atlas M0**: create a cluster, a DB user, allow `0.0.0.0/0` (Render free has no fixed IP), copy the SRV URL.
2. **Gemini**: create a key in Google AI Studio. Check your per-model limits there and set `LLM_MODEL` / `ROUTER_MODEL`.
   Free-tier data may be used by Google: use only fake customers.
3. **Google SSO**: Cloud Console > APIs & Services > Credentials > OAuth client ID (Web). Add `http://localhost:8000`
   and your Render URL under *Authorized JavaScript origins*. Put the client ID in `GOOGLE_CLIENT_ID`. No secret is needed.
4. **Stripe (optional)**: `PAYMENT_PROVIDER=stripe`, `STRIPE_SECRET_KEY=sk_test_...` (live keys are rejected by code).
   Webhook: `stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe`, then set `STRIPE_WEBHOOK_SECRET`.
   Re-run the seed script after switching providers: orders carry the provider that charged them.
5. **Images**: Render's disk is ephemeral. Use `STORAGE_BACKEND=cloudinary` in production (free tier), `local` for dev only.
6. **Cold starts / SLA escalation**: point a free uptime monitor at `/health`, and a free cron at
   `POST /api/v1/jobs/escalate` with header `X-Cron-Secret`. Escalation is also evaluated lazily whenever complaints are read.

## Shop (mock data)
After sign-in, **Shop** lists a 12-item demo catalogue (`app/services/catalog.py`, seeded on startup). Customers add items,
change quantities, remove items and check out with a delivery address. Checkout is server-priced (18% tax, free delivery from
INR 1,500), reserves stock atomically, charges through the active payment provider, creates a normal order (so chat tracking,
cancellation and refunds work on it immediately), and is idempotent against double clicks. `python -m scripts.seed` resets stock.

## How it fits together
- **Security**: the LLM never supplies `user_id`. It comes from the verified JWT into `RunnableConfig`; every query is scoped by it.
  Access token 15 min (memory) + rotating refresh token in an HttpOnly cookie, reuse detection, argon2 hashes, rate limits,
  strict CSP, assistant text rendered via DOM text nodes only.
- **Money**: integer minor units. Eligibility and refund math live in `services/order_rules.py` (unit-tested).
  Cancel = atomic claim -> provider refund with idempotency key -> webhook/immediate result applied idempotently.
- **Cancellation confirm** is a LangGraph `interrupt()` resolved by a UI button, not by the model's say-so.
- **Defect photos** start a separate review graph (`review-<complaint_id>` thread) that pauses until an admin decides, so the
  customer's chat never blocks. Approve triggers a full refund; the result is posted back into the customer's chat.
- **Admin takeover**: `handled_by="human"` makes the bot silent; customers see agent replies through 6-second polling.
- **Quota-aware**: heuristic router first (LLM classifier only when rules can't decide), max 4 tool rounds, per-user rate limit.

## Decisions you can change
- Cancellable states and fee rule: `services/order_rules.py` (`CANCELLABLE`, `DELIVERY_FEE_REFUNDABLE`). Current rule: cancel until
  delivered; delivery fee returned before dispatch, kept after.
- Complaint matrix/SLA: `CATEGORIES` in the same file.
- Swap LLM vendor: `app/agents/llm.py`.
- Tools are plain LangChain tools in `app/agents/tools.py`; they can be exposed over MCP later without changing the graph.
