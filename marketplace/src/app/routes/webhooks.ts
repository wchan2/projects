import type { FastifyInstance, FastifyRequest } from "fastify";
import type { PaymentsEngine } from "../../engine/payments-engine.js";

// Populated by the raw-body content type parser registered in server.ts.
type RequestWithRawBody = FastifyRequest & { rawBody?: Buffer };

export function registerWebhookRoutes(app: FastifyInstance, engine: PaymentsEngine) {
  app.post("/webhooks/stripe", async (request: RequestWithRawBody, reply) => {
    const signature = request.headers["stripe-signature"];
    if (typeof signature !== "string" || !request.rawBody) {
      return reply.code(400).send({ error: "missing signature or raw body" });
    }

    try {
      const result = await engine.handleWebhook(request.rawBody, signature);
      return reply.code(200).send(result);
    } catch (err) {
      request.log.error(err, "failed to process Stripe webhook");
      return reply.code(400).send({ error: "webhook verification or processing failed" });
    }
  });
}
