-- Migration 011: persist tax-receipt URL for audit
--
-- After a successful payment, if fiscalization is enabled for the provider,
-- the bot registers income in «Мой налог» via the nalogo SDK and gets back a
-- public print-URL for the receipt. We persist this URL on the payment row so:
--
--   * admin queries like "find payments without a receipt" are trivial
--     (SELECT id FROM payments WHERE is_successful AND fiscal_receipt_url IS NULL)
--   * the receipt can be re-sent to the buyer later if their original message
--     was lost (admin command or future "my receipts" UI)
--
-- Column is nullable: payments via providers with fiscalization disabled
-- naturally have NULL here. Historical payments (created before this column
-- existed) also remain NULL — no backfill is possible since «Мой налог»
-- stopped accepting after-the-fact YooKassa registrations on 2025-12-29.
--
-- Length 256 covers the standard print-URL format:
--   https://lknpd.nalog.ru/api/v1/receipt/{12-digit-inn}/{uuid}/print
-- which is ~85 chars in practice; 256 leaves headroom for hypothetical other
-- fiscalizers.

BEGIN;

ALTER TABLE payments
    ADD COLUMN fiscal_receipt_url VARCHAR(256);

COMMIT;
