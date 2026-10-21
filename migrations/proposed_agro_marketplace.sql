-- Proposed additive schema. NOT executed on production.
CREATE TABLE IF NOT EXISTS agro_marketplace_listings (
 id BIGSERIAL PRIMARY KEY,
 source_request_id BIGINT,
 seller_name TEXT NOT NULL,
 seller_phone TEXT NOT NULL,
 seller_email TEXT,
 commodity TEXT NOT NULL,
 variety_grade TEXT,
 description TEXT,
 quantity NUMERIC(16,3) NOT NULL CHECK (quantity > 0),
 quantity_unit TEXT NOT NULL,
 price_mwk NUMERIC(16,2) CHECK (price_mwk IS NULL OR price_mwk >= 0),
 price_unit TEXT,
 location TEXT NOT NULL,
 availability_note TEXT,
 transport_note TEXT,
 packaging TEXT,
 status TEXT NOT NULL DEFAULT 'PENDING'
  CHECK (status IN ('PENDING','APPROVED','REJECTED','PAUSED','SOLD_OUT')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 reviewed_at TIMESTAMPTZ,
 reviewed_by TEXT,
 review_notes TEXT
);
CREATE TABLE IF NOT EXISTS agro_marketplace_images (
 id BIGSERIAL PRIMARY KEY,
 listing_id BIGINT NOT NULL REFERENCES agro_marketplace_listings(id) ON DELETE CASCADE,
 storage_key TEXT NOT NULL,
 mime_type TEXT NOT NULL,
 display_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS agro_marketplace_buyer_enquiries (
 id BIGSERIAL PRIMARY KEY,
 listing_id BIGINT NOT NULL REFERENCES agro_marketplace_listings(id),
 buyer_name TEXT NOT NULL,
 buyer_phone TEXT NOT NULL,
 buyer_email TEXT,
 requested_quantity NUMERIC(16,3),
 message TEXT,
 status TEXT NOT NULL DEFAULT 'NEW',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agro_public ON agro_marketplace_listings(created_at DESC) WHERE status='APPROVED' AND quantity > 0;
CREATE INDEX IF NOT EXISTS idx_agro_buyer_listing ON agro_marketplace_buyer_enquiries(listing_id,created_at DESC);
-- Public queries MUST explicitly select non-sensitive columns, never SELECT *.
-- Buyer enquiries must re-check APPROVED and quantity > 0 in the transaction.
