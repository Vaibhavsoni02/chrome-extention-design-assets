"""Site metadata: page title, favicon discovery/download, dominant color."""

import io
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from lxml import html as lxml_html
from PIL import Image

DEFAULT_COLOR = (66, 133, 244)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class MetadataFetchError(Exception):
    pass


@dataclass
class SiteMetadata:
    url: str
    domain: str
    title: str
    favicon: "Image.Image | None"
    dominant_color: tuple


def fetch_html(url: str, timeout: int = 10) -> str:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise MetadataFetchError(f"Couldn't reach {url}: {e}") from e
    return resp.text


def parse_title(html_text: str, fallback: str) -> str:
    try:
        tree = lxml_html.fromstring(html_text)
        titles = tree.xpath("//title/text()")
        if titles and titles[0].strip():
            return titles[0].strip()
    except Exception:
        pass
    return fallback


def _icon_size(sizes_attr: str) -> int:
    if not sizes_attr or sizes_attr.lower() == "any":
        return 0
    best = 0
    for part in sizes_attr.split():
        if "x" in part.lower():
            try:
                w, h = part.lower().split("x")
                best = max(best, int(w) * int(h))
            except ValueError:
                continue
    return best


def find_icon_candidates(html_text: str, base_url: str) -> list:
    candidates = []
    try:
        tree = lxml_html.fromstring(html_text)
        for link in tree.xpath("//link[@rel]"):
            rel = (link.get("rel") or "").lower()
            href = link.get("href")
            if not href or "icon" not in rel:
                continue
            size = _icon_size(link.get("sizes", ""))
            if "apple-touch-icon" in rel and size == 0:
                size = 180 * 180  # soft priority boost, typical apple-touch-icon size
            candidates.append((urljoin(base_url, href), size))
    except Exception:
        pass
    candidates.sort(key=lambda c: c[1], reverse=True)
    candidates.append((urljoin(base_url, "/favicon.ico"), 0))
    return candidates


def pick_best_icon_url(candidates: list, base_url: str) -> "str | None":
    return candidates[0][0] if candidates else None


def download_icon(icon_url: str, timeout: int = 10) -> "Image.Image | None":
    try:
        resp = requests.get(icon_url, headers=REQUEST_HEADERS, timeout=timeout)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        img.load()
        return img
    except Exception:
        return None


def dominant_color(img: "Image.Image | None") -> tuple:
    if img is None:
        return DEFAULT_COLOR
    try:
        small = img.convert("RGB").resize((1, 1), Image.LANCZOS)
        return small.getpixel((0, 0))
    except Exception:
        return DEFAULT_COLOR


def get_site_metadata(url: str) -> SiteMetadata:
    domain = urlparse(url).netloc or url
    html_text = fetch_html(url)
    title = parse_title(html_text, fallback=domain)

    favicon = None
    for candidate_url, _size in find_icon_candidates(html_text, url):
        favicon = download_icon(candidate_url)
        if favicon is not None:
            break

    color = dominant_color(favicon)

    return SiteMetadata(url=url, domain=domain, title=title, favicon=favicon, dominant_color=color)
