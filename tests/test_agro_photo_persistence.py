"""Offline checks for photo persistence helpers, without a live database."""
import unittest
from agro_photo_persistence import associate_seller_photos, get_approved_listing_photo, save_seller_photos


class FakeCursor:
    def __init__(self, result=None):
        self.statements = []
        self.result = result
    def execute(self, sql, params):
        self.statements.append((sql, params))
    def fetchone(self):
        return self.result


class PhotoPersistenceTests(unittest.TestCase):
    def test_empty_upload_creates_no_rows(self):
        cur = FakeCursor()
        self.assertEqual(save_seller_photos(cur, 101, []), 0)
        self.assertEqual(cur.statements, [])

    def test_association_scoped_to_request_and_unlinked_photos(self):
        cur = FakeCursor()
        associate_seller_photos(cur, 101, 77)
        self.assertEqual(len(cur.statements), 1)
        sql, params = cur.statements[0]
        self.assertIn("seller_request_id=%s", sql)
        self.assertIn("listing_id IS NULL", sql)
        self.assertEqual(params, (77, 101))

    def test_public_read_requires_approved_in_stock_listing(self):
        cur = FakeCursor((b"jpeg", "image/jpeg"))
        self.assertEqual(get_approved_listing_photo(cur, 88), (b"jpeg", "image/jpeg"))
        sql, params = cur.statements[0]
        self.assertIn("l.status='APPROVED'", sql)
        self.assertIn("l.quantity>0", sql)
        self.assertEqual(params, (88,))


if __name__ == "__main__":
    unittest.main()
