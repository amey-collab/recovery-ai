# RecoverAI

RecoverAI is a modular fintech recovery platform: failed payment → prediction → expected-value intervention → deterministic guardrails → approved execution → verified outcome → analytics. Demo records are clearly synthetic.

## Run locally

1. Copy `.env.example` to `.env`, set a strong `SECRET_KEY`, and use PostgreSQL (SQLite is retained only as a simple no-infrastructure fallback).
2. `cd backend; python -m venv .venv; .venv\\Scripts\\pip install -r requirements.txt; .venv\\Scripts\\uvicorn app.main:app --reload`
3. `cd frontend; npm install; npm run dev`
4. Register an administrator at `POST /api/auth/register`, then sign in at `http://localhost:5173`.

Generate data and train real local models:

```powershell
python ml/data_generator.py --rows 100000
python scripts/train_models.py
python scripts/seed.py
cd backend; pytest
```

## Razorpay Test Mode

Use Test Mode keys only. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`; no browser credential is ever embedded. The backend uses the official Python SDK to create Orders and fetch Payments. Amounts are converted to currency subunits. Configure the public webhook URL as `https://<tunnel-or-host>/api/webhooks/razorpay`, select `payment.failed`, `payment.authorized`, `payment.captured`, and `order.paid`, and set the same secret locally. A tunnel/deployment is required for Razorpay to reach a local backend. Webhook signatures are verified against the raw request body and duplicates are idempotently ignored.

Payment collection is not a recovery API. Razorpay’s Payments API is used only for its documented fetching/capture lifecycle. Recovery execution is intentionally labelled simulation until a later real test payment/webhook proves the outcome.

## Security and limits

Passwords are bcrypt hashes; JWT access is role-controlled (`ADMIN`, `ANALYST`, `OPERATOR`, `VIEWER`). Guardrails cap auto-recovery at ₹10,000, max retries at two, and require confidence ≥ .35. The LLM is optional and can never execute an action or alter guardrails.

## Docker

`docker compose up --build` starts frontend, backend, PostgreSQL, and Redis. For production, use managed PostgreSQL, a secret manager, HTTPS/reverse proxy, migration jobs, restricted CORS, and a publicly routable signed webhook endpoint.

## Render Free plan

For a native Render Web Service on the Free plan, set the Build Command to:

```bash
bash scripts/render_build.sh
```

This installs `backend/requirements.txt` and runs `alembic upgrade head` against the Render-provided `DATABASE_URL` before the service starts. Keep the Start Command as:

```bash
bash scripts/render_start.sh
```

The wrapper validates Render's runtime `PORT`, binds Uvicorn to `0.0.0.0`,
and uses `exec` so the web process remains attached to Render's port scan.
For a one-time production demo-data population, set `RUN_SYNTHETIC_SEED=true`
for one deploy; it creates four idempotent synthetic bundles before starting
the server. Remove the variable or set it to `false` afterward.

Configure `DATABASE_URL`, `APP_ENV`, `SECRET_KEY`, `CORS_ORIGINS`, and the required Test Mode Razorpay variables in Render's environment settings. Never commit `.env` or credentials.

## Limitations

The UI intentionally focuses on the operational dashboard while the backend offers the protected REST workflows. Add email/SMS delivery only behind a `NotificationService`, and replace the in-process pipeline with a worker when volume needs it.
