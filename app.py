"""Streamlit app: generate Chrome Web Store listing assets from a website URL."""

import streamlit as st
from PIL import Image

from capture import capture_many, check_playwright_ready
from imaging import (
    build_icon_from_source,
    build_monogram_icon,
    compose_tile,
    process_screenshot_for_output,
    to_bytes,
    validate_asset,
)
from site_meta import DEFAULT_COLOR, MetadataFetchError, dominant_color, get_site_metadata
from utils import build_zip, is_valid_youtube_url, normalize_url

st.set_page_config(
    page_title="Chrome Web Store Asset Generator",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Small CSS polish on top of the config.toml theme: tighten vertical rhythm and give
# bordered containers a touch of depth so asset "cards" read as distinct from the page.
st.markdown(
    """
    <style>
      .block-container { padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1100px; }
      div[data-testid="stVerticalBlockBorderWrapper"] {
          box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      }
      div[data-testid="stImage"] img { border-radius: 8px; }
      h1 { font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🧩 How it works")
    st.markdown(
        "1. Enter a site URL\n"
        "2. Optionally add up to 4 extra page URLs for more screenshots\n"
        "3. Pick how the store icon should be sourced\n"
        "4. Click **Generate Assets**\n"
        "5. Download individual files or the whole ZIP"
    )
    st.divider()
    ready, reason = check_playwright_ready()
    if ready:
        st.badge("Screenshot engine ready", icon="✅", color="green")
    else:
        st.badge("Screenshot engine not ready", icon="⚠️", color="orange")
        st.caption(f"Reason: {reason}")
        st.code("pip install -r requirements.txt\npython3 -m playwright install chromium", language="bash")
    st.divider()
    st.caption("Outputs strictly match Chrome Web Store dimensions: 128×128 icon, 1280×800 screenshots, 440×280 small tile, 1400×560 marquee tile — no alpha channel.")

st.markdown("# 🧩 Chrome Web Store Asset Generator")
st.caption("Enter a website URL and generate the store icon, screenshots, and promo tiles for a Chrome Web Store listing — sized and formatted to spec.")
st.write("")

with st.container(border=True):
    with st.form("asset_form"):
        col_url, col_icon = st.columns([2, 1])
        with col_url:
            primary_url = st.text_input("Primary site URL", placeholder="https://example.com")
        with col_icon:
            icon_mode = st.radio(
                "Store icon source",
                ["Auto: extract favicon", "Auto: generate monogram", "Manual upload"],
            )

        with st.expander("➕ Additional screenshot pages (optional, up to 4 more)"):
            extra_cols = st.columns(2)
            extra_urls = []
            for i in range(4):
                col = extra_cols[i % 2]
                extra_urls.append(col.text_input(f"Screenshot URL {i + 2}", key=f"extra_url_{i}"))

        manual_icon_file = st.file_uploader(
            "Upload icon image (used only if 'Manual upload' is selected above)", type=["png", "jpg", "jpeg"]
        )

        youtube_url = st.text_input("YouTube promo video URL (optional)", placeholder="https://www.youtube.com/watch?v=...")
        if youtube_url and not is_valid_youtube_url(youtube_url):
            st.caption(":orange[That doesn't look like a standard YouTube URL — it will still be passed through as-is.]")

        submitted = st.form_submit_button("✨ Generate Assets", type="primary", use_container_width=True)

if submitted:
    ok, reason = check_playwright_ready()
    if not ok:
        st.error("Screenshot capture isn't ready yet.")
        if reason == "package not installed":
            st.write("The `playwright` package needs to be installed:")
        elif reason == "chromium browser not installed":
            st.write("The Playwright Chromium browser binary needs to be downloaded:")
        else:
            st.write(f"Playwright failed to launch Chromium: {reason}")
        st.code("pip install -r requirements.txt\npython3 -m playwright install chromium", language="bash")
        st.stop()

    if not primary_url.strip():
        st.error("Please enter a primary site URL.")
        st.stop()

    primary_url = normalize_url(primary_url)
    urls = [primary_url]
    for u in extra_urls:
        u = normalize_url(u)
        if u and u not in urls:
            urls.append(u)
    urls = urls[:5]

    with st.status("Generating assets...", expanded=True) as status:
        status.write("Reading site metadata...")
        try:
            meta = get_site_metadata(primary_url)
        except MetadataFetchError as e:
            st.warning(f"Couldn't read site metadata ({e}); using defaults.")
            from urllib.parse import urlparse

            domain = urlparse(primary_url).netloc or primary_url
            from site_meta import SiteMetadata

            meta = SiteMetadata(url=primary_url, domain=domain, title=domain, favicon=None, dominant_color=DEFAULT_COLOR)

        status.write(f"Capturing {len(urls)} screenshot(s)...")
        capture_results = capture_many(urls)

        screenshots = []
        for url, img, err in capture_results:
            if err:
                st.warning(f"Skipped {url}: {err}")
            else:
                screenshots.append((url, img))

        if not screenshots:
            status.update(label="Failed to generate assets", state="error")
            st.error("No screenshots could be captured — check the URL(s) and try again.")
            st.stop()

        # If favicon extraction failed entirely, derive a site-specific tint from the homepage shot instead.
        if meta.favicon is None:
            meta.dominant_color = dominant_color(screenshots[0][1])

        status.write("Building store icon...")
        icon = None
        try:
            if icon_mode == "Manual upload" and manual_icon_file is not None:
                icon = build_icon_from_source(Image.open(manual_icon_file))
            elif icon_mode == "Auto: extract favicon" and meta.favicon is not None:
                icon = build_icon_from_source(meta.favicon)
            else:
                if icon_mode == "Auto: extract favicon":
                    st.info("No favicon found — generated a monogram icon instead.")
                elif icon_mode == "Manual upload":
                    st.info("No file uploaded — generated a monogram icon instead.")
                icon = build_monogram_icon(meta.title, meta.dominant_color)
        except Exception as e:
            st.info(f"Icon source couldn't be processed ({e}) — generated a monogram icon instead.")
            icon = build_monogram_icon(meta.title, meta.dominant_color)
        validate_asset(icon, (128, 128))

        status.write("Composing promo tiles...")
        homepage_shot = screenshots[0][1]
        small_tile = compose_tile(homepage_shot, meta.favicon, meta.title, meta.dominant_color, 440, 280)
        marquee_tile = compose_tile(homepage_shot, meta.favicon, meta.title, meta.dominant_color, 1400, 560)

        processed_screenshots = [(url, process_screenshot_for_output(img)) for url, img in screenshots]

        assets = {"icon-128.png": icon, "promo-tile-small-440x280.png": small_tile, "promo-tile-marquee-1400x560.png": marquee_tile}
        for i, (url, img) in enumerate(processed_screenshots, start=1):
            assets[f"screenshot-{i}.png"] = img

        status.update(label=f"Done — generated {len(assets)} assets", state="complete")

    st.session_state["assets"] = assets
    st.session_state["youtube_url"] = youtube_url
    st.session_state["site_title"] = meta.title
    st.toast(f"Assets ready for {meta.title}", icon="🎉")

if "assets" in st.session_state:
    assets = st.session_state["assets"]
    st.divider()
    st.markdown(f"## Assets for {st.session_state.get('site_title', '')}")

    icon_col, small_col = st.columns([1, 2])
    with icon_col:
        with st.container(border=True):
            st.markdown("**Store icon** · 128×128")
            st.image(assets["icon-128.png"], width=128)
            st.download_button(
                "Download icon-128.png", to_bytes(assets["icon-128.png"]), "icon-128.png", "image/png", icon="⬇️", use_container_width=True
            )
    with small_col:
        with st.container(border=True):
            st.markdown("**Small promo tile** · 440×280")
            st.image(assets["promo-tile-small-440x280.png"])
            st.download_button(
                "Download promo-tile-small-440x280.png",
                to_bytes(assets["promo-tile-small-440x280.png"]),
                "promo-tile-small-440x280.png",
                "image/png",
                icon="⬇️",
            )

    with st.container(border=True):
        st.markdown("**Marquee promo tile** · 1400×560")
        st.image(assets["promo-tile-marquee-1400x560.png"])
        st.download_button(
            "Download promo-tile-marquee-1400x560.png",
            to_bytes(assets["promo-tile-marquee-1400x560.png"]),
            "promo-tile-marquee-1400x560.png",
            "image/png",
            icon="⬇️",
        )

    with st.container(border=True):
        shot_names = [n for n in assets if n.startswith("screenshot-")]
        st.markdown(f"**Screenshots** · 1280×800 · {len(shot_names)} of 5")
        cols = st.columns(len(shot_names))
        for col, name in zip(cols, shot_names):
            with col:
                st.image(assets[name])
                st.download_button(f"Download {name}", to_bytes(assets[name]), name, "image/png", icon="⬇️", key=f"dl_{name}", use_container_width=True)

    if st.session_state.get("youtube_url"):
        st.info(f"**Promo video** — paste this into the Global promo video field: `{st.session_state['youtube_url']}`", icon="🎬")

    st.write("")
    zip_bytes = build_zip({name: to_bytes(img) for name, img in assets.items()})
    st.download_button("📦 Download all as ZIP", zip_bytes, "chrome-store-assets.zip", "application/zip", type="primary", use_container_width=True)
