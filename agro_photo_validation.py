"""Validate seller produce photos before persistent storage.

This module deliberately performs no writes and is not wired into the live seller form.
Store verified bytes in persistent private object storage, not Render's ephemeral disk.
"""
from dataclasses import dataclass
from io import BytesIO

MAX_PHOTOS = 5
MAX_BYTES_PER_PHOTO = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 24_000_000


class ProducePhotoError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedProducePhoto:
    filename: str
    mime_type: str
    content: bytes
    width: int
    height: int


def validate_produce_photos(files):
    """Decode and re-encode images to strip metadata and reject forged file types.

    Requires Pillow. Returns sanitized JPEG/PNG bytes for the caller to store.
    No database, network, or filesystem writes occur.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError
    images = [f for f in files if f and getattr(f, "filename", "")]
    if len(images) > MAX_PHOTOS:
        raise ProducePhotoError("Upload no more than five photos.")
    total = 0
    verified = []
    for index, file in enumerate(images):
        raw = file.stream.read(MAX_BYTES_PER_PHOTO + 1)
        total += len(raw)
        if len(raw) > MAX_BYTES_PER_PHOTO or total > MAX_TOTAL_BYTES:
            raise ProducePhotoError("Each photo must be 5 MB or less; maximum 20 MB total.")
        try:
            with Image.open(BytesIO(raw)) as img:
                if img.format not in ("JPEG", "PNG", "WEBP"):
                    raise ProducePhotoError("Only JPEG, PNG and WebP photos are accepted.")
                width, height = img.size
                if width < 100 or height < 100 or width * height > MAX_PIXELS:
                    raise ProducePhotoError("Photo dimensions are unsupported.")
                img = ImageOps.exif_transpose(img)
                img.load()
                img.thumbnail((2048, 2048))
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    target = Image.new("RGB", img.size, (255, 255, 255))
                    rgba = img.convert("RGBA")
                    target.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    target = img.convert("RGB")
                out = BytesIO()
                target.save(out, format="JPEG", quality=82, optimize=True)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            if isinstance(exc, ProducePhotoError):
                raise
            raise ProducePhotoError("A selected photo is invalid or damaged.") from exc
        verified.append(VerifiedProducePhoto(
            filename=f"produce-{index + 1}.jpg", mime_type="image/jpeg",
            content=out.getvalue(), width=target.width, height=target.height
        ))
    return verified
