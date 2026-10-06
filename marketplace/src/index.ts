import { buildServer } from "./app/server.js";
import { loadEnv } from "./app/config/env.js";
import { PaymentsEngine } from "./engine/payments-engine.js";
import { StripeGateway } from "./engine/stripe/stripe-gateway.js";
import { prisma } from "./infra/prisma/client.js";
import { createPrismaEngineRepositories } from "./infra/repositories/prisma-engine-repositories.js";

async function main() {
  const env = loadEnv();

  const gateway = new StripeGateway(env.STRIPE_SECRET_KEY, env.STRIPE_WEBHOOK_SECRET);
  const repos = createPrismaEngineRepositories(prisma);
  const engine = new PaymentsEngine(gateway, repos);

  const app = buildServer(engine, env);

  await app.listen({ port: env.PORT, host: "0.0.0.0" });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
