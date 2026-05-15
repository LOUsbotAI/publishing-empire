/**
 * LOUSTA Publishing Empire — Cloudflare Worker
 * =============================================
 * Edge payment receiver + product API.
 * Runs globally on Cloudflare's network, writes to D1 (lousta_transactions).
 *
 * Endpoints:
 *   GET  /                       — health + stats
 *   GET  /books                  — list available products
 *   GET  /books/:id              — single product detail
 *   POST /webhook/stripe         — Stripe webhook receiver (HMAC verified)
 *   GET  /revenue                — revenue summary (protected by ADMIN_KEY)
 *   GET  /revenue/daily          — last 30 days breakdown
 *   GET  /revenue/milestones     — milestone tracker
 *
 * Secrets (set via: wrangler secret put <NAME>):
 *   STRIPE_WEBHOOK_SECRET        — whsec_... from Stripe dashboard
 *   ADMIN_KEY                    — your private key for /revenue endpoints
 *
 * Bindings (wrangler.toml):
 *   DB                           — D1 database lousta_transactions
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, Stripe-Signature',
    };

    if (method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    try {
      // ── Routes ────────────────────────────────────────────────────────────
      if (path === '/' || path === '/health') {
        return handleHealth(env, cors);
      }

      if (path === '/books' && method === 'GET') {
        return handleListBooks(env, cors);
      }

      if (path.startsWith('/books/') && method === 'GET') {
        const id = path.slice(7);
        return handleGetBook(env, cors, id);
      }

      if (path === '/webhook/stripe' && method === 'POST') {
        return handleStripeWebhook(request, env, cors);
      }

      if (path === '/revenue' && method === 'GET') {
        return handleRevenue(request, env, cors);
      }

      if (path === '/revenue/daily' && method === 'GET') {
        return handleRevenueDaily(request, env, cors);
      }

      if (path === '/revenue/milestones' && method === 'GET') {
        return handleMilestones(request, env, cors);
      }

      return json({ error: 'Not found' }, 404, cors);

    } catch (err) {
      console.error('Worker error:', err);
      return json({ error: 'Internal server error', detail: err.message }, 500, cors);
    }
  }
};


// ── Health ────────────────────────────────────────────────────────────────────

async function handleHealth(env, cors) {
  const result = await env.DB.prepare(
    'SELECT COUNT(*) as sales, SUM(amount_cents) as total FROM transactions WHERE status="completed"'
  ).first();
  const books = await env.DB.prepare('SELECT COUNT(*) as cnt FROM books WHERE status="ready"').first();

  return json({
    status: 'ok',
    service: 'lousta-publishing-empire',
    region: 'global-edge',
    books_available: books?.cnt ?? 0,
    total_transactions: result?.sales ?? 0,
    total_revenue_aud_cents: result?.total ?? 0,
    timestamp: new Date().toISOString(),
  }, 200, cors);
}


// ── Books / Products ──────────────────────────────────────────────────────────

async function handleListBooks(env, cors) {
  const { results } = await env.DB.prepare(
    `SELECT id, title, genre, word_count, created_at
     FROM books WHERE status = 'ready' ORDER BY created_at DESC`
  ).all();
  return json({ books: results, count: results.length }, 200, cors);
}

async function handleGetBook(env, cors, id) {
  const book = await env.DB.prepare(
    'SELECT id, title, genre, word_count, created_at FROM books WHERE id = ? AND status = "ready"'
  ).bind(id).first();
  if (!book) return json({ error: 'Book not found' }, 404, cors);
  return json({ book }, 200, cors);
}


// ── Stripe Webhook ────────────────────────────────────────────────────────────

async function handleStripeWebhook(request, env, cors) {
  const body = await request.text();
  const sigHeader = request.headers.get('Stripe-Signature') || '';

  // Verify HMAC signature
  const secret = env.STRIPE_WEBHOOK_SECRET;
  if (!secret) {
    console.error('STRIPE_WEBHOOK_SECRET not configured');
    return json({ error: 'Webhook secret not configured' }, 500, cors);
  }

  const verified = await verifyStripeSignature(body, sigHeader, secret);
  if (!verified) {
    console.warn('Stripe signature verification failed');
    return json({ error: 'Invalid signature' }, 400, cors);
  }

  let event;
  try {
    event = JSON.parse(body);
  } catch {
    return json({ error: 'Invalid JSON' }, 400, cors);
  }

  // Store raw webhook for audit trail
  await env.DB.prepare(
    `INSERT OR IGNORE INTO webhooks (id, event_type, payload, processed)
     VALUES (?, ?, ?, 0)`
  ).bind(event.id, event.type, body.slice(0, 10000)).run();

  // Process known event types
  const handled = await processStripeEvent(event, env);

  // Mark processed
  await env.DB.prepare('UPDATE webhooks SET processed = 1 WHERE id = ?')
    .bind(event.id).run();

  return json({ received: true, event_type: event.type, handled }, 200, cors);
}

async function processStripeEvent(event, env) {
  const type = event.type;
  const obj = event.data?.object;

  if (!obj) return false;

  // ── Payment successful ────────────────────────────────────────────────────
  if (type === 'payment_intent.succeeded' || type === 'charge.succeeded') {
    const paymentId = obj.id;
    const amountCents = obj.amount ?? obj.amount_captured ?? 0;
    const currency = (obj.currency ?? 'aud').toUpperCase();
    const email = obj.billing_details?.email ?? obj.receipt_email ?? 'unknown';
    const productName = obj.description ?? obj.metadata?.product_name ?? 'LOUSTA Book';
    const productId = obj.metadata?.product_id ?? null;
    const now = new Date().toISOString();
    const today = now.slice(0, 10);

    // Insert transaction
    await env.DB.prepare(
      `INSERT OR IGNORE INTO transactions
         (payment_id, customer_email, product_name, amount_cents, currency,
          status, stripe_event_type, created_at)
       VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)`
    ).bind(paymentId, email, productName, amountCents, currency, type, now).run();

    // Update book record if we have a product_id
    if (productId) {
      await env.DB.prepare(
        `UPDATE books SET stripe_payment_id = ?, customer_email = ?, delivered_at = ?
         WHERE id = ? AND delivered_at IS NULL`
      ).bind(paymentId, email, now, productId).run();
    }

    // Upsert customer
    if (email !== 'unknown') {
      await env.DB.prepare(
        `INSERT OR IGNORE INTO customers (id, email, stripe_customer_id, created_at)
         VALUES (?, ?, ?, ?)`
      ).bind(
        obj.customer ?? `cus_${paymentId}`,
        email,
        obj.customer ?? null,
        now
      ).run();
    }

    // Update daily revenue
    await env.DB.prepare(
      `INSERT INTO daily_revenue (date, total_cents, transaction_count, new_customers)
         VALUES (?, ?, 1, 1)
       ON CONFLICT(date) DO UPDATE SET
         total_cents = total_cents + excluded.total_cents,
         transaction_count = transaction_count + 1`
    ).bind(today, amountCents).run();

    // Update sales table
    await env.DB.prepare(
      `INSERT OR IGNORE INTO sales
         (stripe_event_id, amount, currency, product_id, customer_email, status, tax_amount, created_at)
       VALUES (?, ?, ?, ?, ?, 'paid', 0, ?)`
    ).bind(event.id, amountCents, currency, productId, email, now).run();

    console.log(`Sale recorded: ${paymentId} — ${currency} ${amountCents} — ${email}`);

    // Check revenue milestones
    await checkMilestones(env);

    return true;
  }

  // ── Payout sent ───────────────────────────────────────────────────────────
  if (type === 'payout.paid' || type === 'payout.created') {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO payouts (id, amount, currency, status, stripe_payout_id, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      obj.id,
      obj.amount ?? 0,
      (obj.currency ?? 'aud').toUpperCase(),
      obj.status ?? 'pending',
      obj.id,
      new Date().toISOString()
    ).run();
    console.log(`Payout recorded: ${obj.id} — ${obj.amount}`);
    return true;
  }

  // ── Subscription events ───────────────────────────────────────────────────
  if (type === 'customer.subscription.created' || type === 'customer.subscription.updated') {
    await env.DB.prepare(
      `INSERT OR REPLACE INTO subscriptions
         (stripe_subscription_id, customer_email, plan_name, amount_cents, status,
          current_period_end, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      obj.id,
      obj.metadata?.email ?? 'unknown',
      obj.items?.data?.[0]?.plan?.nickname ?? 'plan',
      obj.items?.data?.[0]?.plan?.amount ?? 0,
      obj.status,
      obj.current_period_end ? new Date(obj.current_period_end * 1000).toISOString() : null,
      new Date().toISOString()
    ).run();
    return true;
  }

  // Unhandled event type — stored for audit, no action needed
  return false;
}

async function checkMilestones(env) {
  const result = await env.DB.prepare(
    'SELECT SUM(amount_cents) as total FROM transactions WHERE status="completed"'
  ).first();
  const totalCents = result?.total ?? 0;

  // Milestone thresholds in AUD cents
  const milestones = [
    { id: 'aud_500', cents: 50000, label: 'AUD $500' },
    { id: 'aud_1000', cents: 100000, label: 'AUD $1,000' },
    { id: 'aud_5000', cents: 500000, label: 'AUD $5,000' },
    { id: 'aud_10000', cents: 1000000, label: 'AUD $10,000' },
    { id: 'aud_50000', cents: 5000000, label: 'AUD $50,000' },
    { id: 'aud_100000', cents: 10000000, label: 'AUD $100,000' },
  ];

  for (const m of milestones) {
    if (totalCents >= m.cents) {
      await env.DB.prepare(
        `INSERT OR IGNORE INTO revenue_milestones
           (id, milestone_amount, reached_at, payout_status, notes)
         VALUES (?, ?, ?, 'pending', ?)`
      ).bind(m.id, m.cents, new Date().toISOString(), `Reached ${m.label}`).run();
    }
  }
}


// ── Revenue ───────────────────────────────────────────────────────────────────

function requireAdmin(request, env) {
  const key = request.headers.get('X-Admin-Key') ?? new URL(request.url).searchParams.get('key');
  return key === env.ADMIN_KEY;
}

async function handleRevenue(request, env, cors) {
  if (!requireAdmin(request, env)) {
    return json({ error: 'Unauthorized' }, 401, cors);
  }

  const totals = await env.DB.prepare(
    `SELECT
       COUNT(*) as transaction_count,
       SUM(amount_cents) as total_cents,
       currency
     FROM transactions WHERE status="completed"
     GROUP BY currency`
  ).all();

  const customers = await env.DB.prepare('SELECT COUNT(*) as cnt FROM customers').first();
  const books = await env.DB.prepare('SELECT COUNT(*) as cnt FROM books WHERE status="ready"').first();
  const milestones = await env.DB.prepare(
    'SELECT * FROM revenue_milestones ORDER BY milestone_amount'
  ).all();

  return json({
    revenue_by_currency: totals.results,
    total_customers: customers?.cnt ?? 0,
    books_available: books?.cnt ?? 0,
    milestones: milestones.results,
    generated_at: new Date().toISOString(),
  }, 200, cors);
}

async function handleRevenueDaily(request, env, cors) {
  if (!requireAdmin(request, env)) {
    return json({ error: 'Unauthorized' }, 401, cors);
  }

  const { results } = await env.DB.prepare(
    `SELECT date, total_cents, transaction_count, new_customers
     FROM daily_revenue ORDER BY date DESC LIMIT 30`
  ).all();

  return json({ daily: results, days: results.length }, 200, cors);
}

async function handleMilestones(request, env, cors) {
  if (!requireAdmin(request, env)) {
    return json({ error: 'Unauthorized' }, 401, cors);
  }
  const { results } = await env.DB.prepare(
    'SELECT * FROM revenue_milestones ORDER BY milestone_amount'
  ).all();
  return json({ milestones: results }, 200, cors);
}


// ── Helpers ───────────────────────────────────────────────────────────────────

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
  });
}

async function verifyStripeSignature(payload, sigHeader, secret) {
  if (!sigHeader) return false;

  const parts = sigHeader.split(',');
  const tPart = parts.find(p => p.startsWith('t='));
  if (!tPart) return false;
  const timestamp = tPart.slice(2);

  const v1Sigs = parts
    .filter(p => p.startsWith('v1='))
    .map(p => p.slice(3));

  if (v1Sigs.length === 0) return false;

  // Reject webhooks older than 5 minutes
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp, 10)) > 300) {
    console.warn('Stripe webhook timestamp too old');
    return false;
  }

  const signedPayload = `${timestamp}.${payload}`;
  const keyData = new TextEncoder().encode(secret);
  const msgData = new TextEncoder().encode(signedPayload);

  const key = await crypto.subtle.importKey(
    'raw', keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false, ['sign']
  );

  const sigBytes = await crypto.subtle.sign('HMAC', key, msgData);
  const computedHex = Array.from(new Uint8Array(sigBytes))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  return v1Sigs.some(sig => sig === computedHex);
}
