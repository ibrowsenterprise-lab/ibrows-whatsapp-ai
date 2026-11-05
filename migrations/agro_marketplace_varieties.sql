-- Additive provenance for multiple varieties; existing records and unique keys stay intact.
CREATE TABLE IF NOT EXISTS agro_marketplace_listing_sources (
 listing_id BIGINT PRIMARY KEY REFERENCES agro_marketplace_listings(id) ON DELETE CASCADE,
 source_request_id BIGINT REFERENCES website_service_requests(id) ON DELETE SET NULL,
 variant_key TEXT NOT NULL,
 UNIQUE(source_request_id, variant_key)
);
