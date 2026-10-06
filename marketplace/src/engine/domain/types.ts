export type ChargeStatus =
  | "PENDING"
  | "SUCCEEDED"
  | "REFUNDED"
  | "PARTIALLY_REFUNDED"
  | "DISPUTED"
  | "FAILED";

export type PayoutStatus = "PENDING" | "PAID" | "FAILED";

// Reserved for the future seller-configurable refund workflow (deferred).
export type RefundPolicy = "NO_REFUNDS" | "AUTO_APPROVE_WINDOW" | "MANUAL_REVIEW";

export interface Seller {
  id: string;
  email: string;
  gatewayAccountId: string;
  chargesEnabled: boolean;
  payoutsEnabled: boolean;
  detailsSubmitted: boolean;
  refundPolicy: RefundPolicy;
}

export interface Charge {
  id: string;
  sellerId: string;
  gatewayPaymentIntentId: string;
  amount: number;
  applicationFeeAmount: number;
  currency: string;
  status: ChargeStatus;
}

export interface Payout {
  id: string;
  sellerId: string;
  gatewayPayoutId: string;
  amount: number;
  currency: string;
  status: PayoutStatus;
  arrivalDate: Date | null;
}
