-- Correct confirmed packaging on the existing G9 groundnuts listing.
-- Exact row and original values guard against touching unrelated listings.
UPDATE agro_marketplace_listings
SET quantity_unit = '50 kg bags', updated_at = NOW()
WHERE id = 684
  AND commodity = 'Groundnuts'
  AND variety_grade = 'G9'
  AND quantity = 260
  AND quantity_unit = '50kg'
  AND location = 'Lilongwe 49'
  AND price_mwk = 7000
  AND lower(price_unit) = 'kg';
