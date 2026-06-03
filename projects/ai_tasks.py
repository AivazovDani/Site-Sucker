import os
import threading
import tempfile
import zipfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin

import anthropic
from bs4 import BeautifulSoup, Comment
from celery import shared_task
from django.conf import settings
from playwright.sync_api import sync_playwright

from .models import Projects
from .utils import call_api_with_retry


# ─── Tracking domains to strip from HTML ─────────────────────────────────────

TRACKING_DOMAINS = [
    'googletagmanager.com',
    'google-analytics.com',
    'analytics.google.com',
    'connect.facebook.net',
    'facebook.com/tr',
    'hotjar.com',
    'clarity.ms',
    'doubleclick.net',
    'adservice.google.com',
    'snap.licdn.com',
    'static.ads-twitter.com',
    'sc-static.net',
    'cdn.segment.com',
    'cdn.amplitude.com',
]

# Inline <script> content patterns that indicate tracking code
TRACKING_SCRIPT_PATTERNS = [
    'gtag(',
    'fbq(',
    'hj(',
    '_hsq',
    'analytics.track',
    'mixpanel',
    'GoogleAnalyticsObject',
    'dataLayer',
]

# Asset content types worth capturing and self-hosting
ASSET_CONTENT_TYPES = [
    'text/css',
    'application/javascript',
    'text/javascript',
    'image/png',
    'image/jpeg',
    'image/gif',
    'image/svg+xml',
    'image/webp',
    'image/x-icon',
    'font/woff',
    'font/woff2',
    'font/ttf',
    'font/otf',
    'application/font-woff',
    'application/font-woff2',
]


# ─── Celery Task ──────────────────────────────────────────────────────────────

@shared_task
def scrape(project_id):
    print('TASK STARTED, project_id:', project_id)
    project = Projects.objects.get(id=project_id)
    project.status = 'processing'
    project.save()

    url = project.website_link
    print('URL:', url)

    try:
        with tempfile.TemporaryDirectory() as temp_folder:
            start = time.perf_counter()

            # Phase 1 — Render page and capture all assets via Playwright interception
            html, asset_map = render_and_capture(url, temp_folder)

            # Phase 2 — Strip tracking scripts from HTML using BeautifulSoup
            clean_html = strip_tracking(html)

            # Phase 3 — Clean CSS files via Claude (JS bundles are skipped)
            clean_css_files(asset_map, temp_folder)

            # Phase 4 — Rewrite asset paths in HTML and CSS files
            final_html = rewrite_paths(clean_html, asset_map, temp_folder)

            # Phase 5 — Zip everything and save to the project
            zip_name = f'project_{project_id}.zip'
            zipped_path = zipp(temp_folder, zip_name)

            end = time.perf_counter()
            print(f'Elapsed: {end - start:.4f}s')

            with open(zipped_path, 'rb') as f:
                project.cleaned_zip.save(zip_name, f)

        project.status = 'ready'
        project.save()

    except Exception as e:
        project.status = 'failed'
        print('SCRAPE ERROR:', e)
        project.save()
        raise


# ─── Phase 1: Render + Capture ────────────────────────────────────────────────

def render_and_capture(url, temp_folder):
    """
    Launch Playwright, intercept every network response while the page loads,
    save asset files directly to temp_folder, return rendered HTML + asset_map.

    asset_map: { original_url: local_filename }
        e.g. { 'https://example.com/assets/main.js': 'assets_main.js' }
    """
    asset_map = {}
    lock = threading.Lock()

    def handle_response(response):
        try:
            resp_url = response.url

            # Skip tracking domains — don't download them at all
            if any(domain in resp_url for domain in TRACKING_DOMAINS):
                return

            # Only capture recognised asset types
            content_type = response.headers.get('content-type', '')
            is_asset = any(t in content_type for t in ASSET_CONTENT_TYPES)
            if not is_asset:
                return

            body = response.body()
            if not body:
                return

            # Derive a flat local filename from the URL path
            parsed = urlparse(resp_url)
            path = parsed.path.strip('/')       # 'assets/main-C-viK0xx.js'
            filename = path.replace('/', '_')   # 'assets_main-C-viK0xx.js'

            if not filename:
                return

            full_path = os.path.join(temp_folder, filename)

            with open(full_path, 'wb') as f:
                f.write(body)

            with lock:
                asset_map[resp_url] = filename  # original URL → local filename

        except Exception as e:
            print(f'Response capture error ({response.url}): {e}')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            service_workers='block',            # prevent service workers hiding requests
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
        )
        page = context.new_page()

        # Attach listener BEFORE navigation so we catch every response
        page.on('response', handle_response)

        page.goto(url, wait_until='networkidle', timeout=60000)

        # Scroll to trigger lazy-loaded assets
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(2000)
        page.evaluate('window.scrollTo(0, 0)')
        page.wait_for_timeout(1000)

        html = page.content()
        browser.close()

    print(f'Captured {len(asset_map)} assets')
    return html, asset_map


# ─── Phase 2: Strip Tracking from HTML ───────────────────────────────────────

def strip_tracking(html):
    """
    Remove tracking scripts and tags from rendered HTML using BeautifulSoup.
    Pattern-based — fast, reliable, no API cost.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Remove <script src="..."> tags pointing to tracking domains
    for tag in soup.find_all('script', src=True):
        src = tag.get('src', '')
        if any(domain in src for domain in TRACKING_DOMAINS):
            tag.decompose()

    # Remove inline <script> blocks containing tracking patterns
    for tag in soup.find_all('script'):
        content = tag.string or ''
        if any(pattern in content for pattern in TRACKING_SCRIPT_PATTERNS):
            tag.decompose()

    # Remove GTM <noscript> iframes
    for tag in soup.find_all('noscript'):
        if 'googletagmanager' in str(tag) or 'GTM-' in str(tag):
            tag.decompose()

    # Remove tracking <link> tags (pixels, preconnects to tracking domains)
    for tag in soup.find_all('link'):
        href = tag.get('href', '')
        if any(domain in href for domain in TRACKING_DOMAINS):
            tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    return str(soup)


# ─── Phase 3: Clean CSS via Claude ───────────────────────────────────────────

def clean_css_files(asset_map, temp_folder):
    """
    Send CSS files to Claude for cleaning.
    JS bundles are intentionally skipped — minified JS can't be meaningfully
    cleaned, and stripping the tracking <script> tags in Phase 2 is sufficient.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    css_entries = [
        (orig_url, local_name)
        for orig_url, local_name in asset_map.items()
        if local_name.endswith('.css')
    ]

    def clean_one(orig_url, local_name):
        full_path = os.path.join(temp_folder, local_name)
        if not os.path.exists(full_path):
            return

        try:
            with open(full_path, 'r', errors='ignore') as f:
                css_content = f.read()

            if not css_content.strip():
                return

            response = call_api_with_retry(
                model='claude-sonnet-4-5',
                system="""You are a code cleaning assistant.
Clean this CSS by:
- Removing duplicate rules
- Removing unused vendor prefixes
- Removing commented out code
- Removing any references to tracking or analytics URLs
Return only the cleaned CSS, nothing else. No explanation, no markdown.""",
                content=css_content,
                client=client,
            )

            cleaned = response.content[0].text

            with open(full_path, 'w') as f:
                f.write(cleaned)

            print(f'CSS cleaned: {local_name}')

        except Exception as e:
            print(f'CSS clean error ({local_name}): {e}')

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(clean_one, orig_url, local_name): local_name
            for orig_url, local_name in css_entries
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f'CSS thread error ({name}): {e}')


# ─── Phase 4: Rewrite Asset Paths ────────────────────────────────────────────

def rewrite_paths(html, asset_map, temp_folder):
    """
    Replace original URLs in HTML and CSS with local filenames.

    Covers:
    - Full URLs:   https://example.com/assets/main.js  → assets_main.js
    - Path only:   /assets/main.js                     → assets_main.js
    - CSS url():   url('../fonts/font.woff2')           → url('font.woff2')
    """
    # Rewrite the HTML in memory
    for orig_url, local_name in asset_map.items():
        original_path = urlparse(orig_url).path     # '/assets/main-C-viK0xx.js'
        html = html.replace(orig_url, local_name)   # full URL replacement
        html = html.replace(original_path, local_name)  # path-only replacement

    # Write final index.html to temp folder
    html_path = os.path.join(temp_folder, 'index.html')
    with open(html_path, 'w') as f:
        f.write(html)

    # Also rewrite paths inside CSS files (fonts, background images, etc.)
    for orig_url, local_name in asset_map.items():
        if not local_name.endswith('.css'):
            continue

        full_path = os.path.join(temp_folder, local_name)
        if not os.path.exists(full_path):
            continue

        try:
            with open(full_path, 'r', errors='ignore') as f:
                css_content = f.read()

            for inner_url, inner_name in asset_map.items():
                inner_path = urlparse(inner_url).path
                css_content = css_content.replace(inner_url, inner_name)
                css_content = css_content.replace(inner_path, inner_name)

            with open(full_path, 'w') as f:
                f.write(css_content)

        except Exception as e:
            print(f'Path rewrite error in CSS ({local_name}): {e}')

    return html


# ─── Phase 5: Zip ─────────────────────────────────────────────────────────────

def zipp(temp_folder, z_name):
    zip_path = os.path.join(temp_folder, z_name)

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, dirs, files in os.walk(temp_folder):
            for file in files:
                if file == z_name:
                    continue
                full_path = os.path.join(root, file)
                zipf.write(full_path, arcname=file)

    return zip_path