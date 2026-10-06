import type { FastifyInstance } from "fastify";
import { z } from "zod";
import {
  InvalidSplitError,
  SellerNotFoundError,
  SellerNotOnboardedError,
} from "../../engine/payments-engine.js";
import type { PaymentsEngine } from "../../engine/payments-engine.js";

const createChargeBodySchema = z.object({
  sellerId: z.string(),
  amount: z.number().int().positive(),
  applicationFeeAmount: z.number().int().nonnegative(),
  currency: z.string().default("usd"),
  paymentMethodId: z.string(),
});

export function registerChargeRoutes(app: FastifyInstance, engine: PaymentsEngine) {
  app.post("/charges", async (request, reply) => {
    const body = createChargeBodySchema.parse(request.body);

    try {
      const charge = await engine.createSplitCharge(body);
      return reply.code(201).send(charge);
    } catch (err) {
      if (err instanceof SellerNotFoundError) {
        return reply.code(404).send({ error: err.message });
      }
      if (err instanceof SellerNotOnboardedError || err instanceof InvalidSplitError) {
        return reply.code(422).send({ error: err.message });
      }
      throw err;
    }
  });
}
