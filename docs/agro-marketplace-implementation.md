# IBROWS-managed Agriculture marketplace

Public catalogue: `/agriculture/marketplace`; existing agriculture intake preserved.
Admin moderation: `/admin/agro-marketplace`, linked from service requests.

The authoritative additive migration is `migrations/agro_marketplace_v1.sql`.
`migrations/proposed_agro_marketplace.sql` is an obsolete pre-implementation draft;
it is never applied. The root schema file mirrors the authoritative migration.

## Privacy and buyer handling
Only explicit public columns are selected for the catalogue. Seller contact fields
remain private. Buyer enquiries require session CSRF, consent and a valid phone,
use the existing database rate limiter, and save an AGRICULTURE service request
and linked marketplace enquiry atomically. The existing IBROWS admin notification
is attempted only after commit; no seller or buyer messages are sent automatically.

## Initial authorized listing
Source request IBR-SR-2026-0010, seller permission confirmed by Jones on 21 October
2026: 50 bags white maize, MK52,000 per 50 kg bag, Area 25 Sector 4, Lilongwe.
The seed verifies the source commodity, grade, quantity, unit and seller intent.
It copies seller details only into private columns, never updates source data,
and never republishes or resets existing marketplace stock on restart.

## Deployment and rollback
The migration creates new tables and an index in one bounded transaction under an
advisory lock. It does not alter or delete existing tables or records. References
to existing service requests use ON DELETE SET NULL to preserve existing deletion
workflows. If initialization fails it rolls back, marketplace routes return 503,
and existing services remain available. Startup logs expose the failure for review.

Before merging, CI tests full Flask startup against disposable PostgreSQL 18,
moderation, privacy, CSRF, unavailable stock, enquiries, source preservation,
initialization idempotency, spam controls and existing website services. A structural
regression test requires all existing app functions and route decorators to remain
identical to production commit 3b2d6038ced3282df570865471ae9068c9a40170.

Production rollback: restore the previous deployment/commit; leave additive tables
and enquiries intact. Never drop marketplace tables as a rollback step. No existing
business data migration or destructive schema change is part of this release.
