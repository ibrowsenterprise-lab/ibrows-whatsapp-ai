-- IBROWS Agro Marketplace additive PostgreSQL migration
-- Apply only after review; this file does not change production on commit.
CREATE TABLE IF NOT EXISTS agro_marketplace_listings (
  id BIGSERIAL PRIMARY KEY,
  source_service_request_id BIGINT,
  seller_name TEXT NOT NULL,
  seller_phone TEXT NOT NULL,
  seller_email TEXT,
  commodity VARCHAR(240) NOT NULL,
  variety_grade VARCHAR(180),
  description TEXT,
  quantity NUMERIC(16,3) NOT NULL CHECK (quantity > 0),
  quantity_unit VARCHAR(40) NOT NULL,
  asking_price_mwk NUMERIC(18,2) CHECK (asking_price_mwk IS NULL OR asking_price_mwk >= 0),
  price_unit VARCHAR(60),
  produce_location VARCHAR(220) NOT NULL,
  available_from TEXT,
  transport_details TEXT,
  packaging TEXT,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','APPROVED','REJECTED','PAUSED','SOLD_OUT')),
  publication_consent BOOLEAN NOT NULL DEFAULT FALSE,
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  moderation_notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT agro_listing_approval_check CHECK
    (status <> 'APPROVED' OR (approved_at IS NOT NULL AND publication_consent))
);
CREATE INDEX IF NOT EXISTS agro_marketplace_public_idx
 ON agro_marketplace_listings(status, created_at DESC)
 WHERE status='APPROVED';
CREATE TABLE IF NOT EXISTS agro_marketplace_images (
 id BIGSERIAL PRIMARY KEY,
 listing_id BIGINT NOT NULL REFERENCES agro_marketplace_listings(id) ON DELETE CASCADE,
 storage_key TEXT NOT NULL,
 mime_type VARCHAR(80) NOT NULL CHECK (mime_type IN ('image/jpeg','image/png','image/webp')),
 display_order SMALLINT NOT NULL DEFAULT 0,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agro_marketplace_buyer_enquiries (
 id BIGSERIAL PRIMARY KEY,
 listing_id BIGINT NOT NULL REFERENCES agro_marketplace_listings(id),
 buyer_name TEXT NOT NULL,
 buyer_phone TEXT NOT NULL,
 buyer_email TEXT,
 quantity_requested NUMERIC(16,3) CHECK (quantity_requested IS NULL OR quantity_requested > 0),
 notes TEXT,
 status VARCHAR(20) NOT NULL DEFAULT 'NEW',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- PUBLIC QUERIES MUST SELECT ONLY NON-PII COLUMNS, never SELECT *.
-- Buyer enquiries are managed exclusively by IBROWS staff.
