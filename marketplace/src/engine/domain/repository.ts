import type { Charge, Payout, Seller } from "./types.js";

export interface SellerRepository {
  create(input: { email: string; gatewayAccountId: string }): Promise<Seller>;
  findById(id: string): Promise<Seller | null>;
  findByGatewayAccountId(gatewayAccountId: string): Promise<Seller | null>;
  updateOnboardingStatus(
    gatewayAccountId: string,
    status: { chargesEnabled: boolean; payoutsEnabled: boolean; detailsSubmitted: boolean }
  ): Promise<Seller>;
}

export interface ChargeRepository {
  create(input: {
    sellerId: string;
    gatewayPaymentIntentId: string;
    amount: number;
    applicationFeeAmount: number;
    currency: string;
    status: Charge["status"];
  }): Promise<Charge>;
  findByGatewayPaymentIntentId(gatewayPaymentIntentId: string): Promise<Charge | null>;
  updateStatus(gatewayPaymentIntentId: string, status: Charge["status"]): Promise<Charge>;
}

export interface PayoutRepository {
  upsertFromGatewayEvent(input: {
    sellerId: string;
    gatewayPayoutId: string;
    amount: number;
    currency: string;
    status: Payout["status"];
    arrivalDate: Date | null;
  }): Promise<Payout>;
}

/** Idempotency/audit log for inbound webhook events. */
export interface WebhookEventRepository {
  hasProcessed(gatewayEventId: string): Promise<boolean>;
  recordProcessed(gatewayEventId: string, type: string, payload: unknown): Promise<void>;
}

export interface EngineRepositories {
  sellers: SellerRepository;
  charges: ChargeRepository;
  payouts: PayoutRepository;
  webhookEvents: WebhookEventRepository;
}
