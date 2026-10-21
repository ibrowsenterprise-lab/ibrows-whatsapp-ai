-- Review and apply only after backup; not run automatically.
CREATE TABLE IF NOT EXISTS agro_marketplace_listings (
 id BIGSERIAL PRIMARY KEY, source_request_id BIGINT UNIQUE REFERENCES website_service_requests(id) ON DELETE SET NULL,
 seller_name TEXT NOT NULL, seller_phone TEXT NOT NULL,
 commodity TEXT NOT NULL, variety_grade TEXT,
 quantity NUMERIC(16,3) NOT NULL CHECK (quantity>=0),
 quantity_unit TEXT NOT NULL, price_mwk NUMERIC(16,2) CHECK (price_mwk>0),
 price_unit TEXT, location TEXT NOT NULL,
 availability_note TEXT, transport_note TEXT, packaging TEXT,
 description TEXT, status TEXT NOT NULL DEFAULT 'PENDING'
 CHECK(status IN ('PENDING','APPROVED','REJECTED','PAUSED','SOLD_OUT')),
 created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
 reviewed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS agro_marketplace_buyer_enquiries (
 id BIGSERIAL PRIMARY KEY,
 listing_id BIGINT NOT NULL REFERENCES agro_marketplace_listings(id),
 buyer_name TEXT NOT NULL, buyer_phone TEXT NOT NULL,
 service_request_id BIGINT UNIQUE REFERENCES website_service_requests(id) ON DELETE SET NULL,
 message TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agro_public ON agro_marketplace_listings(created_at DESC)
 WHERE status='APPROVED' AND quantity>0;
