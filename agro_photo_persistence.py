"""Database persistence helpers for verified agricultural seller photos.

Integration points:
* Existing seller POST must use enctype=multipart/form-data.
* After the seller service request is inserted, call save_seller_photos()
  with the SAME transaction cursor before committing.
* Admin listing import may associate request photos with the new listing.
* Public photo retrieval must require an APPROVED listing with stock > 0.
No route or database migration is activated by importing this module.
"""
from agro_photo_validation import validate_produce_photos


def save_seller_photos(cur, seller_request_id, uploaded_files):
    """Insert validated, sanitized images atomically with the seller request.

    Raises ProducePhotoError for invalid images; caller must roll back the
    enclosing transaction and show a safe error instead of saving a partial request.
    """
    photos = validate_produce_photos(uploaded_files)
    return save_verified_seller_photos(cur, seller_request_id, photos)


def save_verified_seller_photos(cur, seller_request_id, photos):
    """Persist images already validated before the database transaction."""
    for position, photo in enumerate(photos, start=1):
        cur.execute(
            """INSERT INTO agro_produce_photos
               (seller_request_id, photo_position, mime_type, photo_bytes)
               VALUES (%s, %s, %s, %s)""",
            (seller_request_id, position, photo.mime_type, photo.content),
        )
    return len(photos)


def associate_seller_photos(cur, seller_request_id, listing_id):
    """Link request photos to a reviewed listing, preserving existing photos.

    Only assign previously unassociated photos; multiple varieties can share
    one seller request, but each photo belongs to one listing for moderation.
    """
    cur.execute(
        """UPDATE agro_produce_photos SET listing_id=%s
           WHERE seller_request_id=%s AND listing_id IS NULL""",
        (listing_id, seller_request_id),
    )


def get_approved_listing_photo(cur, photo_id):
    """Return photo bytes only if its linked listing is publicly approved."""
    cur.execute(
        """SELECT p.photo_bytes, p.mime_type FROM agro_produce_photos p
           JOIN agro_marketplace_listings l ON l.id=p.listing_id
           WHERE p.id=%s AND l.status='APPROVED' AND l.quantity>0""",
        (photo_id,),
    )
    return cur.fetchone()
