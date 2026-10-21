# IBROWS-managed Agriculture marketplace

Tracking: #22. This document is a specification, not a deployed implementation.

## Buyer and seller flow
1. Seller submits product and contact details using the existing agricultural enquiry pathway or a dedicated listing form; listing starts PENDING.
2. Admin reviews product evidence, quantity, price, quality, location and seller identity, then approves or rejects.
3. APPROVED and available listings appear on /agriculture, newest first. Seller phone/email must never be included in public API responses or HTML.
4. Buyer clicks Enquire Through IBROWS on a specific listing; request is linked to listing ID, captured in existing lead/service-request infrastructure and visible to admin.
5. IBROWS confirms current stock and coordinates the transaction manually. No automatic checkout or payment collection.
6. Admin adjusts stock, pauses, rejects or marks sold out; sold-out listings cannot generate purchase requests.

## Data design (adapt to existing schema)
Add additive migration for listing ID, seller reference, commodity, grade, description, price amount/currency/unit, quantity/unit, district, available date, image references, transport/packaging, moderation status, admin audit timestamps, stock status and enquiry linkage. Preserve existing agricultural enquiries.

## API/security requirements
Server-side validation; authenticated and CSRF-protected moderation; image type/size restrictions; spam/rate limits; non-public seller PII; no public exposure of unapproved listings; server-side moderation status checks; safe upload storage and deletion policy. Prefer existing storage patterns.

## Acceptance tests
- PENDING and REJECTED never visible publicly.
- APPROVED listing with stock visible on /agriculture and product detail.
- Buyer enquiry references the correct listing and is routed to IBROWS without contacting seller directly.
- PAUSED/SOLD_OUT cannot be ordered; quantity changes reflected in catalogue.
- Admin moderation endpoints reject unauthenticated/non-admin access.
- Existing agro enquiry form and unrelated website routes continue to function.
- No external customer messages during automated tests.

## Release gate
Inspect app.py and actual schema first. Do not guess or overwrite existing routes. Implement on this branch, run tests, obtain approval, merge and deploy only after verification. Current GitHub file retrieval returned empty app.py content, so coding remains blocked until source is available.