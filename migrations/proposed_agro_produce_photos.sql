-- Proposed only. Apply after backup and approval; not executed on import.
-- Private photo bytes persist in PostgreSQL, avoiding ephemeral Render disk.
-- Photos are attached to the existing seller service request and optionally
-- to a reviewed marketplace listing. No public storage URLs are created.
CREATE TABLE IF NOT EXISTS agro_produce_photos (
    id BIGSERIAL PRIMARY KEY,
    seller_request_id BIGINT NOT NULL REFERENCES website_service_requests(id) ON DELETE CASCADE,
    listing_id BIGINT REFERENCES agro_marketplace_listings(id) ON DELETE SET NULL,
    photo_position SMALLINT NOT NULL CHECK (photo_position BETWEEN 1 AND 5),
    mime_type TEXT NOT NULL DEFAULT 'image/jpeg' CHECK (mime_type = 'image/jpeg'),
    photo_bytes BYTEA NOT NULL CHECK (octet_length(photo_bytes) BETWEEN 1 AND 5242880),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (seller_request_id, photo_position)
);
CREATE INDEX IF NOT EXISTS idx_agro_produce_photos_listing
    ON agro_produce_photos (listing_id, photo_position)
    WHERE listing_id IS NOT NULL;
