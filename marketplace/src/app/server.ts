import Fastify from "fastify";
import type { PaymentsEngine } from "../engine/payments-engine.js";
import type { Env } from "./config/env.js";
import { registerChargeRoutes } from "./routes/charges.js";
import { registerSellerRoutes } from "./routes/sellers.js";
import { registerWebhookRoutes } from "./routes/webhooks.js";

export function buildServer(engine: PaymentsEngine, env: Env) {
  const app = Fastify({ logger: true });

  // Capture the raw body for every JSON request so the Stripe webhook route
  // can verify the signature; parsed JSON is still handed to normal routes.
  app.addContentTypeParser("application/json", { parseAs: "buffer" }, (req, body, done) => {
    (req as unknown as { rawBody: Buffer }).rawBody = body as Buffer;
    if (body.length === 0) {
      done(null, undefined);
      return;
    }
    try {
      done(null, JSON.parse(body.toString()));
    } catch (err) {
      done(err as Error, undefined);
    }
  });

  app.get("/health", async () => ({ status: "ok" }));

  registerSellerRoutes(app, engine, env);
  registerChargeRoutes(app, engine);
  registerWebhookRoutes(app, engine);

  return app;
}
