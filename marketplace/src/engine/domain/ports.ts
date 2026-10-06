import type { ChargeStatus, PayoutStatus } from "./types.js";

/**
 * PaymentGateway is the seam between the engine and whichever payment
 * processor is wired in (Stripe Connect today). Consumers of the engine
 * never talk to this interface directly -- only PaymentsEngine does.
 */
export interface PaymentGateway {
  createConnectedAccount(input: CreateConnectedAccountInput): Promise<CreateConnectedAccountResult>;

  createOnboardingLink(input: CreateOnboardingLinkInput): Promise<CreateOnboardingLinkResult>;

  createSplitCharge(input: CreateSplitChargeInput): Promise<CreateSplitChargeResult>;

  refundCharge(input: RefundChargeInput): Promise<RefundChargeResult>;

  /** Verifies the webhook signature and normalizes the payload into a GatewayEvent. */
  verifyAndParseWebhook(rawBody: Buffer, signatureHeader: string): GatewayEvent;
}

export interface CreateConnectedAccountInput {
  email: string;
}

export interface CreateConnectedAccountResult {
  gatewayAccountId: string;
}

export interface CreateOnboardingLinkInput {
  gatewayAccountId: string;
  refreshUrl: string;
  returnUrl: string;
}

export interface CreateOnboardingLinkResult {
  url: string;
}

export interface CreateSplitChargeInput {
  amount: number;
  currency: string;
  applicationFeeAmount: number;
  destinationAccountId: string;
  paymentMethodId: string;
}

export interface CreateSplitChargeResult {
  gatewayPaymentIntentId: string;
  status: ChargeStatus;
}

export interface RefundChargeInput {
  gatewayPaymentIntentId: string;
  amount?: number;
}

export interface RefundChargeResult {
  status: ChargeStatus;
}

/**
 * Normalized webhook event shape. Gateway adapters translate their own
 * event taxonomy (Stripe's `account.updated`, etc.) into this fixed set
 * so the engine's dispatch logic doesn't depend on Stripe's naming.
 */
export type GatewayEventType =
  | "account.updated"
  | "payment.succeeded"
  | "payment.failed"
  | "payment.refunded"
  | "payment.disputed"
  | "payout.paid"
  | "payout.failed";

export type GatewayEvent =
  | { id: string; type: "account.updated"; data: AccountUpdatedData }
  | { id: string; type: "payment.succeeded"; data: PaymentEventData }
  | { id: string; type: "payment.failed"; data: PaymentEventData }
  | { id: string; type: "payment.refunded"; data: PaymentEventData }
  | { id: string; type: "payment.disputed"; data: PaymentEventData }
  | { id: string; type: "payout.paid"; data: PayoutEventData }
  | { id: string; type: "payout.failed"; data: PayoutEventData };

export interface AccountUpdatedData {
  gatewayAccountId: string;
  chargesEnabled: boolean;
  payoutsEnabled: boolean;
  detailsSubmitted: boolean;
}

export interface PaymentEventData {
  gatewayPaymentIntentId: string;
  status: ChargeStatus;
}

export interface PayoutEventData {
  gatewayPayoutId: string;
  gatewayAccountId: string;
  amount: number;
  currency: string;
  status: PayoutStatus;
  arrivalDate: Date | null;
}
