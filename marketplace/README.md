# Marketplace Payments Engine

A gateway-agnostic payments engine for marketplace-style apps: sellers onboard,
buyers get charged, the platform keeps a cut, the rest routes directly to the
seller. Stripe Connect (Express accounts, destination charges, weekly payouts)
is the first — currently only — gateway implementation.

## Structure

```
src/
  engine/            # The reusable core. No Fastify/HTTP concerns live here.
    domain/
      types.ts       # Seller / Charge / Payout value types
      ports.ts        # PaymentGateway interface + normalized GatewayEvent
      repository.ts   # Persistence ports (engine doesn't know about Prisma)
    stripe/
      stripe-gateway.ts  # The only file that imports the Stripe SDK
    payments-engine.ts   # Facade: onboardSeller, createSplitCharge, handleWebhook

  infra/              # Adapters for the ports above
    prisma/client.ts
    repositories/prisma-engine-repositories.ts

  app/                # This specific HTTP app. Not part of the reusable core.
    config/env.ts
    routes/{sellers,charges,webhooks}.ts
    server.ts

  index.ts            # Composition root: wires gateway + repos + engine + server
```

`engine/` is intentionally the extraction boundary — when this becomes a
template for other services, that folder (plus the Prisma schema) is what
gets pulled out. `app/` and `infra/` are this service's own wiring.

## Local setup

```bash
cp .env.example .env        # fill in real Stripe test keys
docker compose up -d        # starts Postgres
npm install
npm run prisma:migrate      # creates tables
npm run dev                 # starts the API on :3000
```

To receive webhooks locally, forward Stripe events to the running server:

```bash
stripe listen --forward-to localhost:3000/webhooks/stripe
```

## Design notes / deferred work

- **Refund policies are not implemented yet.** `Seller.refundPolicy` exists as
  a schema placeholder (`NO_REFUNDS` / `AUTO_APPROVE_WINDOW` / `MANUAL_REVIEW`)
  but nothing reads or enforces it — that's a later feature (seller-configurable
  policy + logged refund requests + seller approval step).
- **Destination charges** are used (platform is merchant of record), not
  direct charges — see `StripeGateway.createSplitCharge`.
- **Payouts** are Stripe's default weekly rolling schedule per connected
  account; the engine only records `payout.paid`/`payout.failed` webhook
  events for audit, it doesn't trigger payouts itself.
- **No auth on the HTTP API yet** — routes are unauthenticated. Add
  auth/authorization before this talks to anything but your own trusted
  services.
