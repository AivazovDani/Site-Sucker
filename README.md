# SiteSucker 🕷️

A Django web application that scrapes, cleans, and packages website assets for download. Users submit a URL and receive a cleaned, self-contained ZIP file of the site's HTML, CSS, and JavaScript — with tracking scripts removed and code optimized.

---

## How It Works

```
User submits URL
      ↓
Django pushes task to Redis
      ↓
Celery worker picks up task
      ↓
Playwright renders the full page (JavaScript included)
      ↓
BeautifulSoup extracts asset URLs (CSS, JS, images)
      ↓
Threaded HTTP downloads (parallel via threading)
      ↓
Anthropic API cleans CSS and JS files (parallel via threading)
      ↓
Anthropic API cleans HTML (removes trackers, cookie banners, comments)
      ↓
Asset paths rewritten for local use
      ↓
ZIP file created and saved to project
      ↓
User downloads cleaned site
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Django |
| Task queue | Celery |
| Message broker | Redis |
| Page rendering | Playwright (Chromium, headless) |
| HTML parsing | BeautifulSoup4 |
| HTTP client | httpx |
| AI code cleaning | Anthropic API (Claude Sonnet) |
| Concurrency | Python threading |

---

## Features

- **Full page rendering** — uses Playwright to render JavaScript-heavy pages before scraping
- **Asset extraction** — downloads all CSS, JS, and image files
- **AI-powered cleaning** — uses Claude to:
  - Remove duplicate CSS rules and unused vendor prefixes
  - Remove `console.log`, analytics, and dead JavaScript code
  - Strip tracking scripts (Google Analytics, GTM, Meta Pixel, Hotjar)
  - Remove cookie banners, GDPR popups, and HTML comments
- **Parallel processing** — CSS and JS files are cleaned simultaneously using threads, reducing task time significantly
- **Parallel downloads** — assets are downloaded in parallel with thread-safe dict writes using a Lock
- **Rate limit handling** — exponential backoff retry on Anthropic API rate limit errors
- **Self-contained output** — asset paths are rewritten so the ZIP works offline out of the box

---

## Project Structure

```
projects/
└── tasks.py
    ├── scrape()              # Celery task entry point
    ├── render_page()         # Playwright page rendering
    ├── extract_assets()      # BeautifulSoup asset URL extraction
    ├── download_assets()     # Parallel asset downloading with threading
    ├── clean_code()          # Parallel AI cleaning of CSS/JS + HTML
    ├── rewrites_paths()      # Rewrite asset paths in HTML
    └── zipp()                # Create final ZIP file
```

---

## Setup

### Prerequisites

- Python 3.10+
- Redis running locally or via Docker
- Anthropic API key

### Installation

```bash
# Clone the repo
git clone https://github.com/yourname/sitesucker.git
cd sitesucker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Set environment variables
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

### Running the App

```bash
# Terminal 1 — Django server
python manage.py runserver

# Terminal 2 — Redis (if not already running)
redis-server

# Terminal 3 — Celery worker
celery -A your_app worker --pool=eventlet --concurrency=100 --loglevel=info
```

---

## Performance

The scraper uses threading to parallelize the two most expensive steps:

| Step | Before threading | After threading |
|---|---|---|
| CSS/JS cleaning (Anthropic API) | Sequential — one file at a time | Parallel — all files at once |
| Asset downloading (HTTP) | Sequential — one URL at a time | Parallel — all URLs at once |

Both steps are I/O bound (waiting for network responses), making threading the ideal tool — the GIL is released during I/O so all threads wait simultaneously.

Rate limiting is handled with exponential backoff:
```
Attempt 1 → rate limit hit → wait 1s
Attempt 2 → rate limit hit → wait 2s
Attempt 3 → rate limit hit → wait 4s
Attempt 4 → success ✅
```

---

## Scaling

For high concurrency (hundreds of users simultaneously):

```bash
# Use eventlet pool for I/O-bound tasks
celery -A your_app worker --pool=eventlet --concurrency=100

# Run multiple workers
celery -A your_app worker -n worker1@%h --concurrency=50
celery -A your_app worker -n worker2@%h --concurrency=50
```

Each user's scrape task runs on its own Celery worker process, while threading handles parallelism inside each task.

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `REDIS_URL` | Redis broker URL (default: `redis://localhost:6379`) |
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Django debug mode |

---






