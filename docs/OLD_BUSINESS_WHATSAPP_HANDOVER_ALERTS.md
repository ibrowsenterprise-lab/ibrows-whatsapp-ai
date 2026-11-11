# IBROWS — human takeover WhatsApp alert delivery

## Recipient and source

- **Alert destination:** `0882 242 594` = `265882242594` (old IBROWS WhatsApp Business App).
- **Source:** the active IBROWS AI Cloud API number `0883 242 594`.
- Jones's personal number is **not** an alert recipient. Do not change this without explicit confirmation.
- Customers continue interacting with the AI number. Human replies go via the authenticated [IBROWS Inbox](https://www.ibrowsenterprise.com/admin/inbox), never from the alert thread.
- The existing Brevo email human-handover alert remains enabled as a fallback.

## Activate immediately on the old IBROWS phone — 24-hour window

From the **0882 242 594** WhatsApp Business App, send the exact message **`IBROWS ALERTS ON`** to **0883 242 594**.

The AI's webhook recognises the authorized business line, stores the inbound message as an internal notification conversation, and replies with a confirmation; it does **not** create a paid customer lead or change the underlying lead, invoices, or AI pause status.

That inbound message opens/renews a 24-hour service window for 0882. During that window, new genuine human-takeover requests trigger a free-form WhatsApp alert with a secure inbox link. **This is temporary; send the command again after 24 hours if the approved template has not been enabled.**

## Permanent alerts outside the 24-hour window (Meta template)

Submit the following utility template in **WhatsApp Manager → Message Templates** for the WABA of the AI business number. The template is not active until Meta approves it.

- **Name:** `ibrows_human_takeover_notice`
- **Category:** Utility
- **Language:** `en_US` (English US)
- **Body:**

> IBROWS Enterprise: {{1}} has requested human assistance for {{2}}. Please review the request in your secure IBROWS Inbox: https://www.ibrowsenterprise.com/admin/inbox

- **Sample variables:** 1 = `Customer`; 2 = `General Enquiry`.
- Do not include the customer's full message, financial credentials or identity documents in the notification template.
- Once Meta shows **Approved**, set the Render service environment variable
  `IBROWS_HANDOVER_WHATSAPP_TEMPLATE=ibrows_human_takeover_notice` and save/deploy.
- The language defaults to `en_US`; use `IBROWS_HANDOVER_WHATSAPP_TEMPLATE_LANGUAGE` only if the approved language differs.

Never set the template variable before approval. When the recipient's 24-hour window is open, the system prefers free-form alerts; after it expires, it uses the explicitly configured approved template. Meta may charge per eligible template message. Failure to send by WhatsApp does **not** disable email fallback.

## Alert outcomes and troubleshooting

The production backend stores each attempted handover alert in `ibrows_handover_whatsapp_alerts` with lead ID, recipient last 4 digits, channel, status and time only. No copied customer message or bearer token is stored.

- `ACCEPTED`: Meta API accepted a WhatsApp message, **not** confirmed delivered to phone.
- `TEMPLATE_REQUIRED`: recipient has no active 24-hour window and no approved template is configured; email should still be sent.
- `FAILED`: Graph API did not accept the WhatsApp message; email remains backup.
- `MISSING_API_CONFIG` / `BAD_TEMPLATE_CONFIG`: configuration issue, do not claim message delivered.

Use `IBROWS ALERTS ON` to check immediate ability to deliver to the old number; it should receive a confirmation via the AI business number. Then test a human takeover using a **separate test customer** or an already authorized account. Avoid modifying real paid client service records just to test an alert.
