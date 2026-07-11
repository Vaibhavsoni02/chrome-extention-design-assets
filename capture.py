"""Screenshot capture via Playwright headless Chromium."""

import io

from PIL import Image


class PlaywrightNotInstalledError(Exception):
    pass


class ScreenshotError(Exception):
    pass


def check_playwright_ready():
    """Returns (ok, reason). reason is a human-readable string when not ok."""
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        return False, "package not installed"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        return True, ""
    except Exception as e:
        msg = str(e)
        if "playwright install" in msg.lower() or "executable doesn't exist" in msg.lower():
            return False, "chromium browser not installed"
        return False, msg


def capture_screenshot(browser, url: str, width: int = 1280, height: int = 800, timeout_ms: int = 15000) -> Image.Image:
    page = browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=1,  # pin to 1x, otherwise Retina hosts return 2x-scaled screenshots
    )
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        png_bytes = page.screenshot()
    except Exception as e:
        raise ScreenshotError(f"{url}: {e}") from e
    finally:
        page.close()
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def capture_many(urls: list, width: int = 1280, height: int = 800, timeout_ms: int = 15000) -> list:
    """Returns a list of (url, image|None, error|None), one browser instance reused across all URLs."""
    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for url in urls:
                try:
                    img = capture_screenshot(browser, url, width, height, timeout_ms)
                    results.append((url, img, None))
                except ScreenshotError as e:
                    results.append((url, None, str(e)))
                except Exception as e:
                    results.append((url, None, f"{url}: {e}"))
        finally:
            browser.close()
    return results
