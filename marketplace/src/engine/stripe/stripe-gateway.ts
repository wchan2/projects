import Stripe from "stripe";
import type {
  AccountUpdatedData,
  CreateConnectedAccountInput,
  CreateConnectedAccountResult,
  CreateOnboardingLinkInput,
  CreateOnboardingLinkResult,
  CreateSplitChargeInput,
  CreateSplitChargeResult,
  GatewayEvent,
  PaymentEventData,
  PayoutEventData,
  PaymentGateway,
  RefundChargeInput,
  RefundChargeResult,
} from "../domain/ports.js";
import type { ChargeStatus, PayoutStatus } from "../domain/types.js";

export class StripeGateway implements PaymentGateway {
  private readonly stripe: Stripe;
  private readonly webhookSecret: string;

  constructor(secretKey: string, webhookSecret: string) {
    this.stripe = new Stripe(secretKey);
    this.webhookSecret = webhookSecret;
  }

  async createConnectedAccount(input: CreateConnectedAccountInput): Promise<CreateConnectedAccountResult> {
    const account = await this.stripe.accounts.create({
      type: "express",
      email: input.email,
      capabilities: {
        card_payments: { requested: true },
        transfers: { requested: true },
      },
    });
    return { gatewayAccountId: account.id };
  }

  async createOnboardingLink(input: CreateOnboardingLinkInput): Promise<CreateOnboardingLinkResult> {
    const link = await this.stripe.accountLinks.create({
      account: input.gatewayAccountId,
      refresh_url: input.refreshUrl,
      return_url: input.returnUrl,
      type: "account_onboarding",
    });
    return { url: link.url };
  }

  async createSplitCharge(input: CreateSplitChargeInput): Promise<CreateSplitChargeResult> {
    const intent = await this.stripe.paymentIntents.create({
      amount: input.amount,
      currency: input.currency,
      payment_method: input.paymentMethodId,
      confirm: true,
      automatic_payment_methods: { enabled: true, allow_redirects: "never" },
      application_fee_amount: input.applicationFeeAmount,
      transfer_data: {
        destination: input.destinationAccountId,
      },
    });
    return {
      gatewayPaymentIntentId: intent.id,
      status: mapPaymentIntentStatus(intent.status),
    };
  }

  async refundCharge(input: RefundChargeInput): Promise<RefundChargeResult> {
    await this.stripe.refunds.create({
      payment_intent: input.gatewayPaymentIntentId,
      amount: input.amount,
      reverse_transfer: true,
      refund_application_fee: true,
    });
    return { status: input.amount ? "PARTIALLY_REFUNDED" : "REFUNDED" };
  }

  verifyAndParseWebhook(rawBody: Buffer, signatureHeader: string): GatewayEvent {
    const event = this.stripe.webhooks.constructEvent(rawBody, signatureHeader, this.webhookSecret);
    return normalizeStripeEvent(event);
  }
}

function mapPaymentIntentStatus(status: Stripe.PaymentIntent.Status): ChargeStatus {
  switch (status) {
    case "succeeded":
      return "SUCCEEDED";
    case "processing":
    case "requires_action":
    case "requires_confirmation":
    case "requires_capture":
    case "requires_payment_method":
      return "PENDING";
    default:
      return "FAILED";
  }
}

function mapPayoutStatus(status: string): PayoutStatus {
  switch (status) {
    case "paid":
      return "PAID";
    case "failed":
    case "canceled":
      return "FAILED";
    default:
      return "PENDING";
  }
}

function normalizeStripeEvent(event: Stripe.Event): GatewayEvent {
  switch (event.type) {
    case "account.updated": {
      const account = event.data.object as Stripe.Account;
      const data: AccountUpdatedData = {
        gatewayAccountId: account.id,
        chargesEnabled: account.charges_enabled ?? false,
        payoutsEnabled: account.payouts_enabled ?? false,
        detailsSubmitted: account.details_submitted ?? false,
      };
      return { id: event.id, type: "account.updated", data };
    }

    case "payment_intent.succeeded":
    case "payment_intent.payment_failed": {
      const intent = event.data.object as Stripe.PaymentIntent;
      const data: PaymentEventData = {
        gatewayPaymentIntentId: intent.id,
        status: mapPaymentIntentStatus(intent.status),
      };
      return {
        id: event.id,
        type: event.type === "payment_intent.succeeded" ? "payment.succeeded" : "payment.failed",
        data,
      };
    }

    case "charge.refunded": {
      const charge = event.data.object as Stripe.Charge;
      const data: PaymentEventData = {
        gatewayPaymentIntentId: typeof charge.payment_intent === "string" ? charge.payment_intent : "",
        status: charge.amount_refunded < charge.amount ? "PARTIALLY_REFUNDED" : "REFUNDED",
      };
      return { id: event.id, type: "payment.refunded", data };
    }

    case "charge.dispute.created": {
      const dispute = event.data.object as Stripe.Dispute;
      const data: PaymentEventData = {
        gatewayPaymentIntentId: typeof dispute.payment_intent === "string" ? dispute.payment_intent : "",
        status: "DISPUTED",
      };
      return { id: event.id, type: "payment.disputed", data };
    }

    case "payout.paid":
    case "payout.failed": {
      const payout = event.data.object as Stripe.Payout;
      // Connect events carry the connected account id on the event itself,
      // not on the payout object (`payout.destination` is the bank/card, not the account).
      const gatewayAccountId = (event as Stripe.Event & { account?: string }).account;
      if (!gatewayAccountId) {
        throw new Error(`payout webhook event ${event.id} missing connected account id`);
      }
      const data: PayoutEventData = {
        gatewayPayoutId: payout.id,
        gatewayAccountId,
        amount: payout.amount,
        currency: payout.currency,
        status: mapPayoutStatus(payout.status),
        arrivalDate: payout.arrival_date ? new Date(payout.arrival_date * 1000) : null,
      };
      return {
        id: event.id,
        type: event.type === "payout.paid" ? "payout.paid" : "payout.failed",
        data,
      };
    }

    default:
      throw new UnhandledWebhookEventError(event.type);
  }
}

export class UnhandledWebhookEventError extends Error {
  constructor(public readonly stripeEventType: string) {
    super(`Unhandled Stripe webhook event type: ${stripeEventType}`);
  }
}
