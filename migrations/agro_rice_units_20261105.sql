-- Owner-approved correction of three unit fields. Stock, prices, status,
-- seller requests and all other listings remain unchanged.
-- Match the exact listings, source, variety, stock and price verified at approval.
UPDATE agro_marketplace_listings AS listing
SET price_unit = CASE WHEN listing.price_unit = '1' THEN 'kg' ELSE listing.price_unit END,
    quantity_unit = CASE WHEN listing.id = 437 AND listing.quantity_unit = '5'
                         THEN 'kg' ELSE listing.quantity_unit END,
    updated_at = NOW()
FROM agro_marketplace_listing_sources AS source
JOIN website_service_requests AS request ON request.id = source.source_request_id
WHERE listing.id = source.listing_id
  AND request.reference = 'IBR-SR-2026-0011'
  AND request.service_key = 'AGRICULTURE'
  AND listing.commodity = 'Rice'
  AND listing.quantity = 1000
  AND (
    (listing.id = 436 AND listing.variety_grade = 'White rice'
     AND source.variant_key = 'white rice' AND listing.price_mwk = 5000
     AND listing.price_unit = '1')
    OR
    (listing.id = 437 AND listing.variety_grade = 'Brown rice'
     AND source.variant_key = 'brown rice' AND listing.price_mwk = 7000
     AND (listing.price_unit = '1' OR listing.quantity_unit = '5'))
  );
