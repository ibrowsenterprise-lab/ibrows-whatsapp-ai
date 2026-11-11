# IBROWS Enterprise — Production backend operations

The private **Backend Operations** page is at:
https://www.ibrowsenterprise.com/admin/backend-health

## What it checks

This dashboard intentionally uses **read-only SQL**. It never migrates,
deletes, voids, marks paid, changes lead stage, sends WhatsApp messages,
or automatically claims that the customer received a message.

- **Actual revenue**: counts only `lead_payments`, not screenshots, estimated
  lead values, outstanding quotes, or sandbox/test entries.
- **Paid one-off eligibility work**: checks only matching ledger-backed
  `Scholarship Eligibility Check` cases. A customer inbound message
  newer than the recorded intake flags the case for review. It does not
  assert qualifications are sufficient, progress a work stage, or mark
  the service delivered. The separate verified-payment work queue is
  always the place for authorized human confirmation.
- **Receipts**: flags failed/document-error sends and delivery attempts
  stuck in `SENDING` for over 15 minutes; does not retry uncertain sends.
  Counts orphaned receipt pointers and duplicate non-empty payment
  request tokens. WhatsApp API `ACCEPTED` is not handset delivery.
- **WhatsApp**: counts incomplete inbound dedupe entries and outbox items
  not marked `SENT`. Check logs/status before any resend.
- **Agriculture**: counts approved listings with invalid quantity, price,
  or missing seller contact, and orphaned variant/source links. It does
  not change any listings or affect public pages.
- **Media/storage**: displays current sizes of the website and
  construction image tables, which hold genuine public-facing assets.

## Recovery principles

Never remove customer information because a status says `NEW`:
`NEW` is the enquiry stage, different from paid status and service
delivery. Do not mistake an uncreated paid-case tracking table for
a missing payment, and do not fabricate a stage without documented work.

If the health endpoint cannot read the database, it returns **HTTP 503**
instead of incorrectly showing zero issues.

A paid client with a new reply should be reviewed promptly through
`/admin/eligibility/<lead_id>`; confirm actual review only when the
person has received the required supporting documents and begun the work.

## Media storage

Current database media is large compared with the actual transaction
tables. Do **not** clear these assets as demo data. A future cost-saving
change can move original image bytes to object storage (for example,
Render/S3-compatible object storage), preserving metadata and site URLs.
That requires backup, checksum reconciliation, staged rollout,
version-compatible reads, permission checks, and a rollback path.

## Security and QA

- No incoming customer chat text, phone numbers, transcript contents,
  login credentials, API tokens or payment references are displayed.
- The page uses the existing administrator authentication and
  no-store / noindex response headers.
- Back-end health is on-demand and does not create a new scheduler,
  background worker or outbound notification.
- The permanent `backend-operations-regression.yml` test covers
  read-only SQL, private access, accurate paid-reply classification,
  false-green prevention when the DB is unavailable, and related
  WhatsApp/receipts/work-queue regressions.
