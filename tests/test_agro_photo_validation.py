"""Offline regression tests for produce photo validation; no customer data or network."""
import unittest
from io import BytesIO
from types import SimpleNamespace

from agro_photo_validation import ProducePhotoError, validate_produce_photos


def upload(image_bytes, name="farm.png"):
    return SimpleNamespace(filename=name, stream=BytesIO(image_bytes))


class ProducePhotoValidationTests(unittest.TestCase):
    def test_valid_photo_is_reencoded_without_metadata(self):
        from PIL import Image
        image = Image.new("RGB", (300, 200), "green")
        data = BytesIO()
        image.save(data, "PNG")
        photos = validate_produce_photos([upload(data.getvalue())])
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0].mime_type, "image/jpeg")
        self.assertEqual(photos[0].filename, "produce-1.jpg")
        self.assertTrue(photos[0].content.startswith(bytes((255, 216))))

    def test_rejects_invalid_bytes(self):
        with self.assertRaises(ProducePhotoError):
            validate_produce_photos([upload(b"not a real image")])

    def test_rejects_too_many_photos(self):
        with self.assertRaises(ProducePhotoError):
            validate_produce_photos([upload(b"fake") for _ in range(6)])

    def test_rejects_oversized_photo_before_decoding(self):
        with self.assertRaises(ProducePhotoError):
            validate_produce_photos([upload(b"x" * (5 * 1024 * 1024 + 1))])

    def test_empty_selection_is_allowed(self):
        self.assertEqual(validate_produce_photos([]), [])


if __name__ == "__main__":
    unittest.main()
