"""Image normalization for the talking-head provider.

D-ID's "10 MB" image limit is on the *decoded* (uncompressed) image in memory —
roughly 3.3 megapixels at 3 bytes/pixel — NOT the JPEG file size on disk. So a
small 1.7 MB JPEG that happens to be 6.5 MP is still rejected with a misleading
"file size exceeded 10 MB" error. We cap every uploaded image's resolution
before it is stored and handed to D-ID. The output video is only 360-720p, so
downscaling a large source is lossless in practice.
"""

import io

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps


def normalize_for_did(uploaded_file):
    """Return a JPEG ContentFile capped to DID_MAX_IMAGE_MP megapixels.

    Applies EXIF orientation and flattens any transparency onto white so the
    JPEG encoding preserves intent. Downscales (preserving aspect ratio) only
    when the source exceeds the megapixel budget.
    """
    budget_px = int(settings.DID_MAX_IMAGE_MP * 1_000_000)

    uploaded_file.seek(0)
    img = Image.open(uploaded_file)
    img = ImageOps.exif_transpose(img)  # bake in orientation before re-encoding
    if img.mode != "RGB":
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            img = Image.alpha_composite(bg, rgba).convert("RGB")
        else:
            img = img.convert("RGB")

    w, h = img.size
    if w * h > budget_px:
        scale = (budget_px / (w * h)) ** 0.5
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS
        )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=settings.DID_IMAGE_JPEG_QUALITY, optimize=True)
    uploaded_file.seek(0)
    return ContentFile(buf.getvalue(), name="source.jpg")
