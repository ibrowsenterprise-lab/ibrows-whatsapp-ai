-- Seller-confirmed correction: G9 -> CG9 for Groundnuts listing #684 only.
-- Idempotent and guarded so no other variety or listing is changed.
UPDATE agro_marketplace_listings
SET variety_grade = 'CG9', updated_at = NOW()
WHERE id = 684
  AND commodity = 'Groundnuts'
  AND variety_grade = 'G9'
  AND quantity = 260
  AND quantity_unit = '50 kg bags'
  AND location = 'Lilongwe 49';
