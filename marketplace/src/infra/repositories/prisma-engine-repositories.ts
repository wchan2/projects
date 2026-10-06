import type { PrismaClient } from "@prisma/client";
import type {
  ChargeRepository,
  EngineRepositories,
  PayoutRepository,
  SellerRepository,
  WebhookEventRepository,
} from "../../engine/domain/repository.js";
import type { Charge, Payout, Seller } from "../../engine/domain/types.js";

export function createPrismaEngineRepositories(prisma: PrismaClient): EngineRepositories {
  const sellers: SellerRepository = {
    async create(input) {
      return prisma.seller.create({ data: input }) as Promise<Seller>;
    },
    async findById(id) {
      return prisma.seller.findUnique({ where: { id } }) as Promise<Seller | null>;
    },
    async findByGatewayAccountId(gatewayAccountId) {
      return prisma.seller.findUnique({ where: { gatewayAccountId } }) as Promise<Seller | null>;
    },
    async updateOnboardingStatus(gatewayAccountId, status) {
      return prisma.seller.update({ where: { gatewayAccountId }, data: status }) as Promise<Seller>;
    },
  };

  const charges: ChargeRepository = {
    async create(input) {
      return prisma.charge.create({ data: input }) as Promise<Charge>;
    },
    async findByGatewayPaymentIntentId(gatewayPaymentIntentId) {
      return prisma.charge.findUnique({
        where: { gatewayPaymentIntentId },
      }) as Promise<Charge | null>;
    },
    async updateStatus(gatewayPaymentIntentId, status) {
      return prisma.charge.update({
        where: { gatewayPaymentIntentId },
        data: { status },
      }) as Promise<Charge>;
    },
  };

  const payouts: PayoutRepository = {
    async upsertFromGatewayEvent(input) {
      return prisma.payout.upsert({
        where: { gatewayPayoutId: input.gatewayPayoutId },
        create: input,
        update: {
          status: input.status,
          arrivalDate: input.arrivalDate,
        },
      }) as Promise<Payout>;
    },
  };

  const webhookEvents: WebhookEventRepository = {
    async hasProcessed(gatewayEventId) {
      const existing = await prisma.webhookEvent.findUnique({ where: { gatewayEventId } });
      return existing !== null;
    },
    async recordProcessed(gatewayEventId, type, payload) {
      await prisma.webhookEvent.create({
        data: {
          gatewayEventId,
          type,
          payload: payload as object,
          processedAt: new Date(),
        },
      });
    },
  };

  return { sellers, charges, payouts, webhookEvents };
}
