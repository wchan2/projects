import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { SellerNotFoundError } from "../../engine/payments-engine.js";
import type { PaymentsEngine } from "../../engine/payments-engine.js";
import type { Env } from "../config/env.js";

const onboardBodySchema = z.object({
  email: z.string().email(),
});

export function registerSellerRoutes(app: FastifyInstance, engine: PaymentsEngine, env: Env) {
  app.post("/sellers/onboard", async (request, reply) => {
    const body = onboardBodySchema.parse(request.body);

    const { seller, onboardingUrl } = await engine.onboardSeller({
      email: body.email,
      refreshUrl: `${env.APP_BASE_URL}/sellers/onboard/refresh`,
      returnUrl: `${env.APP_BASE_URL}/sellers/onboard/complete`,
    });

    return reply.code(201).send({ sellerId: seller.id, onboardingUrl });
  });

  app.post("/sellers/:id/onboarding-link", async (request, reply) => {
    const params = z.object({ id: z.string() }).parse(request.params);

    try {
      const { url } = await engine.refreshOnboardingLink({
        sellerId: params.id,
        refreshUrl: `${env.APP_BASE_URL}/sellers/onboard/refresh`,
        returnUrl: `${env.APP_BASE_URL}/sellers/onboard/complete`,
      });
      return reply.send({ onboardingUrl: url });
    } catch (err) {
      if (err instanceof SellerNotFoundError) {
        return reply.code(404).send({ error: err.message });
      }
      throw err;
    }
  });
}
