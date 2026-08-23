# Razorpay Test Mode and local webhooks

RecoverAI uses Razorpay Test Mode only during development. Keep `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` in the ignored local `.env`; the API key secret and webhook secret are different credentials and neither is logged or exposed.

The local endpoint is:

```text
POST http://localhost:8000/api/webhooks/razorpay
```

The handler verifies HMAC-SHA256 over the exact raw request body using `RAZORPAY_WEBHOOK_SECRET` and compares it with `X-Razorpay-Signature`. Invalid signatures, malformed JSON, and missing required entity fields are rejected. Events are idempotent by SHA-256 hash of the raw payload. `payment.failed` creates/updates the payment and runs the ML recovery pipeline; `payment.authorized` and `payment.captured` update an existing payment without creating a recovery opportunity; `order.paid` is recognized without inventing unsupported order behavior. Unknown events are persisted and safely returned as ignored.

Run a synthetic local test while the backend is running:

```powershell
python scripts/test_razorpay_webhook.py
```

This creates a clearly synthetic `payment.failed` payload, signs it locally, sends it to localhost, and prints only safe response information. It is not a Razorpay-delivered event and does not represent real payment recovery. The automated webhook tests also verify valid signatures, invalid signatures, duplicate delivery, malformed payloads, unknown events, PostgreSQL persistence, ML prediction, intervention scores, decisions, guardrails, and audit records.

Do not configure the Razorpay Dashboard webhook yet. Razorpay cannot deliver to localhost directly; after deployment, a public HTTPS backend URL will be required before Dashboard webhook configuration. Continue using Test Mode and never Live Mode for development.
