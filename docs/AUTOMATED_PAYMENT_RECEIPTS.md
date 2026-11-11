# IBROWS Enterprise — Automated Payment Receipts

## Trigger and scope

A receipt is generated **only** when an authenticated IBROWS administrator explicitly checks **Confirm that this payment was actually received** in **Customers & Enquiries → Manage lead**, supplies a positive amount, and saves the entry.

The system's existing `lead_payments` ledger records the payment first, using its unique `payment_request_token`. A payment screenshot, WhatsApp message, automated AI inference, estimated value or package selection **never** confirms money and **never** generates an automatic receipt.

The automation ignores historical ledger payments already recorded before the new hook and ignores a repeat submission of the same payment token.

## What the client receives

- Existing numbered, branded IBROWS Enterprise PDF receipt (e.g. `IB-R-2026-0001`), generated from the verified ledger with the original amount, currency, payment method and payment date
- Correct selected service and the customer information from their own lead
- Current outstanding balance; if a client paid only part of the service charge, the existing receipt builder labels it as a deposit/part payment instead of fully paid
- A WhatsApp document caption with the IBROWS receipt number; the client stays on the original business WhatsApp, **0883 242 594**

The system uses the existing `business_documents` PDF generator. The receipt number and snapshot are permanent and unique to the individual payment ID, not to the whole enquiry.

## WhatsApp delivery rules

- The customer's **own** 24-hour customer-service window must be open. This is independent of Jones's 0882 human-takeover alert window.
- If the window is open, the backend immediately attempts to deliver the PDF as a document via WhatsApp Cloud API.
- If the customer has not messaged IBROWS in the last 24 hours, the new receipt is marked `WAITING_WINDOW`. It remains queued until that customer next messages the AI business number. After a successful inbound webhook, IBROWS attempts to send their waiting PDF.
- If Meta rejects the document upload or send, the attempt is recorded as `FAILED`. No automatic repeat is attempted after an uncertain send; staff can inspect and manually resend the permanent PDF after establishing whether the original arrived. Avoid duplicates.
- A `SENDING` state left behind after a worker crash is **not** retried automatically because Meta may have accepted the document just before the crash.
- Status `ACCEPTED` means WhatsApp's API accepted the document for processing. It **does not** independently prove arrival on the customer's device.

An approved WhatsApp utility template and Meta's current applicable rules would be needed for business-initiated receipt notifications outside 24 hours. No template is assumed, and this feature does not attempt a prohibited free-form outbound message outside the window.

## Mobile operations

1. Open **https://www.ibrowsenterprise.com/admin/leads**. Verify money in the actual Airtel Money, TNM Mpamba, bank or cash records—do not rely on a screenshot.
2. On the correct lead, enter **the amount actually received**, method and reference if provided. Confirm the payment receipt checkbox and save.
3. The original payment is recorded regardless of any temporary WhatsApp failure.
4. Open **https://www.ibrowsenterprise.com/admin/receipts** to review accepted, waiting or failed automatic deliveries. No second payment should be entered merely to trigger a receipt.
5. For a pending/failed historical receipt, open the original lead and use **Business documents → Send receipt to WhatsApp**. Check the existing document number and sent history first.
6. Customers must never be told that a receipt was delivered just because the API returned HTTP 200.

## Data protection and robustness

- The `ibrows_auto_receipt_deliveries` table stores only payment and lead IDs, a permanent receipt number, delivery status, timestamps and attempt count.
- Unique primary key `payment_id` prevents repeated automatic claims for the same ledger transaction.
- Sending is attempted **after** the paid ledger transaction commits, never in the same database transaction.
- A failure in PDF generation or WhatsApp delivery cannot reverse a real payment.
- Customer personal details and PDF bytes do **not** enter build logs or the receipt delivery audit table.
- The admin receipt status page uses existing administrator authentication; PDFs remain behind existing authenticated download routes.
- Only newly verified, genuinely recorded payments are automatically processed. Old paid records, including the first MK5,000 one-off eligibility client, are **not** sent a surprise second confirmation; their receipt can be sent manually from the CRM.

## Regular tests

The permanent `automatic-receipt-regression.yml` workflow exercises the confirmed-payment gate, idempotent database claim, PDF sending, 24-hour window, manual-send protection, failed deliveries and other business flows in offline mocks. No real customer messages are sent from CI.
