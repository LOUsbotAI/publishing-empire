# Cloudflare Worker — lousta-publishing-empire

## What it does
- Receives Stripe webhook events globally at the edge (zero downtime)
- Stores transactions, customers, daily revenue to D1 (lousta_transactions)
- Exposes a products API for the store
- Tracks revenue milestones

## Deploy (one-time setup)

```bash
cd cloudflare
npm install -g wrangler   # if not installed

# Set secrets (never commit these)
wrangler secret put STRIPE_WEBHOOK_SECRET   # whsec_... from Stripe dashboard
wrangler secret put ADMIN_KEY               # your private admin key

# Deploy worker
wrangler deploy
```

## After deploy
Copy the Worker URL (e.g. `https://silent-union-202e.YOURNAME.workers.dev`)
and set `CF_WORKER_URL=<that URL>` in your `.env` file.

## Stripe webhook setup
In Stripe Dashboard → Developers → Webhooks → Add endpoint:
- URL: `https://silent-union-202e.YOURNAME.workers.dev/webhook/stripe`
- Events to listen:
  - `payment_intent.succeeded`
  - `charge.succeeded`
  - `payout.paid`
  - `customer.subscription.created`
  - `customer.subscription.updated`

## Endpoints
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | none | Health + stats |
| GET | `/books` | none | List available books |
| GET | `/books/:id` | none | Single book |
| POST | `/webhook/stripe` | Stripe-Signature | Stripe events |
| GET | `/revenue` | X-Admin-Key | Revenue totals |
| GET | `/revenue/daily` | X-Admin-Key | Last 30 days |
| GET | `/revenue/milestones` | X-Admin-Key | Milestones |
