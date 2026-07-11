"""Small stateless helpers: URL/YouTube validation, byte conversion, zip bundling."""

import io
import re
import zipfile

from PIL import Image

YOUTUBE_RE = re.compile(
    r"^https?://(www\.)?(youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+)", re.IGNORECASE
)


def is_valid_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.match(url.strip()))


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def pil_to_bytes(img: Image.Image, fmt: str = "PNG", quality: int = 90) -> bytes:
    buf = io.BytesIO()
    if fmt.upper() in ("JPEG", "JPG"):
        img.save(buf, format="JPEG", quality=quality)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


def build_zip(named_assets: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in named_assets.items():
            zf.writestr(name, data)
    return buf.getvalue()
