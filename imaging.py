"""Pillow-based asset builders: icon, screenshots post-processing, branded promo tiles."""

import io

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ICON_SIZE = 128
SCREENSHOT_SIZE = (1280, 800)
SMALL_TILE_SIZE = (440, 280)
MARQUEE_TILE_SIZE = (1400, 560)

FRAME_WIDTH_FRAC = 0.60
FRAME_ASPECT = 1280 / 800
TOOLBAR_HEIGHT_FRAC = 0.09
DOT_RADIUS_FRAC = 0.018
LOGO_HEIGHT_FRAC = 0.16
TITLE_FONT_HEIGHT_FRAC = 0.11
PADDING_FRAC = 0.06
BLUR_RADIUS_FRAC = 0.02
CORNER_RADIUS_FRAC = 0.03

CANDIDATE_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNSDisplay.ttf",
]

_font_cache = {}


def get_font(size: int) -> "ImageFont.FreeTypeFont":
    size = max(size, 8)
    if size in _font_cache:
        return _font_cache[size]
    font = None
    for path in CANDIDATE_FONTS:
        try:
            font = ImageFont.truetype(path, size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _luminance(rgb) -> float:
    r, g, b = rgb[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def strip_alpha(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    if img.mode in ("RGBA", "LA"):
        base = Image.new("RGB", img.size, bg)
        base.paste(img, mask=img.split()[-1])
        return base
    if img.mode == "P":
        return strip_alpha(img.convert("RGBA"), bg)
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def fit_and_pad(img: Image.Image, target_w: int, target_h: int, bg=(255, 255, 255)) -> Image.Image:
    img = strip_alpha(img, bg)
    scale = min(target_w / img.width, target_h / img.height)
    new_w = max(1, round(img.width * scale))
    new_h = max(1, round(img.height * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), bg)
    canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return canvas


def cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize preserving aspect ratio then center-crop the overflow (no distortion, no padding)."""
    img = strip_alpha(img)
    scale = max(target_w / img.width, target_h / img.height)
    new_w = max(1, round(img.width * scale))
    new_h = max(1, round(img.height * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def validate_asset(img: Image.Image, expected_size: tuple, allow_alpha: bool = False) -> None:
    assert img.size == expected_size, f"expected size {expected_size}, got {img.size}"
    if not allow_alpha:
        assert img.mode == "RGB", f"expected RGB, got mode {img.mode}"


def build_icon_from_source(source_img: Image.Image) -> Image.Image:
    icon = fit_and_pad(source_img, ICON_SIZE, ICON_SIZE)
    validate_asset(icon, (ICON_SIZE, ICON_SIZE))
    return icon


def build_monogram_icon(title: str, dominant_color: tuple) -> Image.Image:
    canvas = Image.new("RGB", (ICON_SIZE, ICON_SIZE), dominant_color)
    draw = ImageDraw.Draw(canvas)
    letter = (title or "?").strip()[:1].upper() or "?"
    text_color = (20, 20, 20) if _luminance(dominant_color) > 140 else (255, 255, 255)
    font = get_font(round(ICON_SIZE * 0.55))
    draw.text((ICON_SIZE / 2, ICON_SIZE / 2), letter, font=font, fill=text_color, anchor="mm")
    validate_asset(canvas, (ICON_SIZE, ICON_SIZE))
    return canvas


def process_screenshot_for_output(img: Image.Image, target_size: tuple = SCREENSHOT_SIZE) -> Image.Image:
    if img.size != target_size:
        img = fit_and_pad(img, target_size[0], target_size[1])
    else:
        img = strip_alpha(img)
    validate_asset(img, target_size)
    return img


def _rounded_mask(size, radius) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def compose_tile(screenshot, favicon, title: str, dominant_color: tuple, width: int, height: int) -> Image.Image:
    # 1. Backdrop: blurred + darkened + brand-tinted cover-crop of the screenshot.
    if screenshot is not None:
        backdrop = cover_crop(screenshot, width, height)
        backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=max(6, round(height * BLUR_RADIUS_FRAC))))
        backdrop = ImageEnhance.Brightness(backdrop).enhance(0.55)
        tint = Image.new("RGB", (width, height), dominant_color)
        backdrop = Image.blend(backdrop, tint, alpha=0.25)
    else:
        backdrop = Image.new("RGB", (width, height), dominant_color)

    canvas = backdrop.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 2. Framed screenshot mock (rounded "browser window" with toolbar).
    frame_x = width  # default: no frame, text can use the full width
    if screenshot is not None:
        frame_w = round(width * FRAME_WIDTH_FRAC)
        frame_h = round(frame_w / FRAME_ASPECT)
        max_frame_h = round(height * (1 - 2 * PADDING_FRAC))
        if frame_h > max_frame_h:
            frame_h = max_frame_h
            frame_w = round(frame_h * FRAME_ASPECT)

        toolbar_h = max(6, round(frame_h * TOOLBAR_HEIGHT_FRAC))
        content_h = frame_h - toolbar_h

        frame_img = Image.new("RGB", (frame_w, frame_h), (245, 245, 245))
        fdraw = ImageDraw.Draw(frame_img)
        fdraw.rectangle([0, 0, frame_w, toolbar_h], fill=(230, 230, 230))
        dot_r = max(2, round(height * DOT_RADIUS_FRAC))
        dot_y = toolbar_h // 2
        for i, color in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            cx = round(toolbar_h * 0.6) + i * (dot_r * 3)
            fdraw.ellipse([cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r], fill=color)

        content = cover_crop(screenshot, frame_w, content_h)
        frame_img.paste(content, (0, toolbar_h))

        corner_r = max(4, round(height * CORNER_RADIUS_FRAC))
        mask = _rounded_mask((frame_w, frame_h), corner_r)

        margin = round(width * PADDING_FRAC)
        frame_x = width - frame_w - margin
        frame_y = (height - frame_h) // 2

        # subtle drop shadow
        shadow = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 90))
        canvas.paste(shadow, (frame_x + 4, frame_y + 4), mask)
        canvas.paste(frame_img, (frame_x, frame_y), mask)

    # 3. Logo + wordmark, top-left.
    logo_h = round(height * LOGO_HEIGHT_FRAC)
    text_x = round(width * PADDING_FRAC)
    text_y = round(height * PADDING_FRAC)

    if favicon is not None:
        logo = fit_and_pad(favicon, logo_h, logo_h)
        logo_mask = _rounded_mask((logo_h, logo_h), round(logo_h * 0.15))
        canvas.paste(logo, (text_x, text_y), logo_mask)
        text_x_title = text_x + logo_h + round(width * 0.02)
        title_y = text_y + logo_h // 2
        anchor = "lm"
    else:
        text_x_title = text_x
        title_y = text_y + logo_h // 2
        anchor = "lm"

    display_title = (title or "").strip()
    if len(display_title) > 28:
        display_title = display_title[:25] + "..."

    # Shrink the font until the title fits between its start x and the frame (or canvas edge if no frame).
    max_text_width = frame_x - round(width * PADDING_FRAC) - text_x_title
    font_size = round(height * TITLE_FONT_HEIGHT_FRAC)
    shadow_draw = ImageDraw.Draw(canvas)
    font = get_font(font_size)
    while font_size > 10:
        font = get_font(font_size)
        bbox = shadow_draw.textbbox((0, 0), display_title, font=font)
        if (bbox[2] - bbox[0]) <= max_text_width or max_text_width <= 0:
            break
        font_size -= 2

    shadow_draw.text((text_x_title + 2, title_y + 2), display_title, font=font, fill=(0, 0, 0), anchor=anchor)
    shadow_draw.text((text_x_title, title_y), display_title, font=font, fill=(255, 255, 255), anchor=anchor)

    canvas = canvas.convert("RGB")
    validate_asset(canvas, (width, height))
    return canvas


def to_bytes(img: Image.Image, fmt: str = "PNG", quality: int = 90) -> bytes:
    buf = io.BytesIO()
    if fmt.upper() in ("JPEG", "JPG"):
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()
