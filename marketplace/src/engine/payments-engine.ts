import type { GatewayEvent, PaymentGateway } from "./domain/ports.js";
import type { EngineRepositories } from "./domain/repository.js";
import type { Charge, Seller } from "./domain/types.js";

export class PaymentsEngine {
  constructor(
    private readonly gateway: PaymentGateway,
    private readonly repos: EngineRepositories
  ) {}

  /** Creates a connected account for a new seller and returns a hosted onboarding link. */
  async onboardSeller(input: { email: string; refreshUrl: string; returnUrl: string }): Promise<{
    seller: Seller;
    onboardingUrl: string;
  }> {
    const { gatewayAccountId } = await this.gateway.createConnectedAccount({ email: input.email });
    const seller = await this.repos.sellers.create({ email: input.email, gatewayAccountId });
    const { url } = await this.gateway.createOnboardingLink({
      gatewayAccountId,
      refreshUrl: input.refreshUrl,
      returnUrl: input.returnUrl,
    });
    return { seller, onboardingUrl: url };
  }

  /** Re-issues a hosted onboarding link, e.g. if the seller's previous link expired. */
  async refreshOnboardingLink(input: {
    sellerId: string;
    refreshUrl: string;
    returnUrl: string;
  }): Promise<{ url: string }> {
    const seller = await this.repos.sellers.findById(input.sellerId);
    if (!seller) throw new SellerNotFoundError(input.sellerId);
    return this.gateway.createOnboardingLink({
      gatewayAccountId: seller.gatewayAccountId,
      refreshUrl: input.refreshUrl,
      returnUrl: input.returnUrl,
    });
  }

  /**
   * Charges the buyer and splits the payment: the platform keeps
   * applicationFeeAmount, the remainder transfers to the seller.
   */
  async createSplitCharge(input: {
    sellerId: string;
    amount: number;
    applicationFeeAmount: number;
    currency: string;
    paymentMethodId: string;
  }): Promise<Charge> {
    const seller = await this.repos.sellers.findById(input.sellerId);
    if (!seller) throw new SellerNotFoundError(input.sellerId);
    if (!seller.chargesEnabled) throw new SellerNotOnboardedError(input.sellerId);

    if (input.applicationFeeAmount > input.amount) {
      throw new InvalidSplitError(input.amount, input.applicationFeeAmount);
    }

    const result = await this.gateway.createSplitCharge({
      amount: input.amount,
      currency: input.currency,
      applicationFeeAmount: input.applicationFeeAmount,
      destinationAccountId: seller.gatewayAccountId,
      paymentMethodId: input.paymentMethodId,
    });

    return this.repos.charges.create({
      sellerId: seller.id,
      gatewayPaymentIntentId: result.gatewayPaymentIntentId,
      amount: input.amount,
      applicationFeeAmount: input.applicationFeeAmount,
      currency: input.currency,
      status: result.status,
    });
  }

  /**
   * Verifies, dedupes, and dispatches an inbound gateway webhook.
   * Returns false if the event was already processed (safe to 200 and skip).
   */
  async handleWebhook(rawBody: Buffer, signatureHeader: string): Promise<{ handled: boolean }> {
    const event = this.gateway.verifyAndParseWebhook(rawBody, signatureHeader);

    if (await this.repos.webhookEvents.hasProcessed(event.id)) {
      return { handled: false };
    }

    await this.dispatch(event);
    await this.repos.webhookEvents.recordProcessed(event.id, event.type, event.data);
    return { handled: true };
  }

  private async dispatch(event: GatewayEvent): Promise<void> {
    switch (event.type) {
      case "account.updated": {
        const { data } = event;
        await this.repos.sellers.updateOnboardingStatus(data.gatewayAccountId, {
          chargesEnabled: data.chargesEnabled,
          payoutsEnabled: data.payoutsEnabled,
          detailsSubmitted: data.detailsSubmitted,
        });
        return;
      }

      case "payment.succeeded":
      case "payment.failed":
      case "payment.refunded":
      case "payment.disputed": {
        const { data } = event;
        await this.repos.charges.updateStatus(data.gatewayPaymentIntentId, data.status);
        return;
      }

      case "payout.paid":
      case "payout.failed": {
        const { data } = event;
        const seller = await this.repos.sellers.findByGatewayAccountId(data.gatewayAccountId);
        if (!seller) return;
        await this.repos.payouts.upsertFromGatewayEvent({
          sellerId: seller.id,
          gatewayPayoutId: data.gatewayPayoutId,
          amount: data.amount,
          currency: data.currency,
          status: data.status,
          arrivalDate: data.arrivalDate,
        });
        return;
      }
    }
  }
}

export class SellerNotFoundError extends Error {
  constructor(sellerId: string) {
    super(`Seller not found: ${sellerId}`);
  }
}

export class SellerNotOnboardedError extends Error {
  constructor(sellerId: string) {
    super(`Seller ${sellerId} has not completed onboarding (charges not enabled)`);
  }
}

export class InvalidSplitError extends Error {
  constructor(amount: number, applicationFeeAmount: number) {
    super(`applicationFeeAmount (${applicationFeeAmount}) cannot exceed amount (${amount})`);
  }
}
