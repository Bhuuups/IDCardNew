import io

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

RATIO = 4 / 5          # passport shape: width / height
OUT_W, OUT_H = 480, 600


def process_photo(upload):
    """Fix rotation, crop to 4:5 around the centre, shrink, return a JPEG ContentFile.
    Raises ValueError for anything that is not a real image."""
    try:
        im = Image.open(upload)
        im = ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file is not a valid image.")
    w, h = im.size
    if w / h > RATIO:
        nw = int(h * RATIO)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / RATIO)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize((OUT_W, OUT_H), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85, optimize=True)
    return ContentFile(buf.getvalue(), name="p.jpg")


def process_template(upload, max_w=1400):
    """School card design: keep it sharp but not huge."""
    try:
        im = Image.open(upload)
        im = ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file is not a valid image.")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return ContentFile(buf.getvalue(), name="t.jpg"), im.width / im.height
