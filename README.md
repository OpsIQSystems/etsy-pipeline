# Etsy Competitor Research & Digital Product Pipeline

A local Python pipeline that researches Etsy competitors and Reddit pain
points, then uses Claude to design and build Decision Support System
products (Excel/Google Sheets dashboards + PDF guides + Etsy listing copy)
for small service businesses (property management, HVAC, landscaping, pool
service, cleaning, roofing, pest control, plumbing, contractors).

Every product is built to explain decisions, not just display data —
e.g. "Crew 2 generated 22% more profit than Crew 1" or "Truck 4 has
exceeded replacement economics."

## Files

| File | Purpose |
|---|---|
| `scraper.py` | Scrapes Etsy search results for competitor listings (Playwright + BeautifulSoup) |
| `review_scraper.py` | Scrapes reviews on those listings, flags complaint language |
| `reddit_scraper.py` | Pulls pain-point posts/comments via the official Reddit API (PRAW) |
| `analyzer.py` | Sends research data to Claude, gets top 5 product opportunities |
| `creator.py` | Builds .xlsx dashboards, PDF guides, and Etsy listing copy per opportunity |
| `lister.py` | Human-reviewed posting to Etsy via the official Etsy API |
| `scheduler.py` | Runs the research step weekly and notifies on strong opportunities |
| `.env` | API key template (fill in your own keys, never commit real ones) |
| `requirements.txt` | Pinned dependencies |

## Setup

### 1. Install Python dependencies

```
pip install -r requirements.txt
playwright install chromium
```

### 2. Get your API keys

**Anthropic (Claude) API key** — used by `analyzer.py` and `creator.py`
- Go to https://console.anthropic.com/settings/keys
- Create a key, paste it into `.env` as `ANTHROPIC_API_KEY`
- This pipeline is hardcoded to `claude-sonnet-4-6`. Do not change it to an Opus model.

**Reddit API credentials** — used by `reddit_scraper.py`
- Go to https://www.reddit.com/prefs/apps
- Click "create another app", choose type "script"
- Set redirect URI to `http://localhost:8080` (unused but required)
- Copy the client ID (under the app name) and secret into `.env` as
  `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT` can stay as `etsy-pipeline-bot/1.0` or be customized

**Etsy API credentials** — used by `lister.py` only
- Go to https://www.etsy.com/developers/your-account
- Create an app to get your `ETSY_API_KEY` (keystring)
- You'll also need OAuth setup for write access (creating listings requires
  an OAuth access token in addition to the API key — see Etsy's
  [Authentication docs](https://developer.etsy.com/documentation/essentials/authentication))
  and your shop's numeric `ETSY_SHOP_ID`
- Fill both into `.env`

### 3. Fill in `.env`

Copy your real keys into `.env` in this project folder. Never commit this
file with real keys to version control.

## Run order

Run each step independently, in this order:

```
python scraper.py          # -> listings.csv
python review_scraper.py   # -> reviews.csv
python reddit_scraper.py   # -> reddit_pain_points.csv
python analyzer.py         # -> opportunities.json
python creator.py          # -> /products/*.xlsx, /products/*.pdf, /listings/*.txt
python lister.py           # -> posted_listings.csv (human approval required per listing)
```

Optionally, leave the scheduler running in the background to automate the
research steps weekly:

```
python scheduler.py        # runs scraper.py + analyzer.py every Sunday 2am, logs to pipeline_log.txt
```

## Important notes

- **Etsy scraping (`scraper.py`, `review_scraper.py`) uses an unofficial
  browser-automation approach**, not Etsy's official API, because Etsy's
  public API does not expose competitor listing/review data. This is a
  gray area under Etsy's Terms of Service — use it for your own market
  research, keep request volume reasonable, and expect occasional blocks
  (see Troubleshooting below).
- **Posting to Etsy (`lister.py`) uses Etsy's official Open API v3**, which
  is fully compliant. It will never post without an explicit `y` response
  to the approval prompt for each listing.
- All scraping delays are randomized (3-7 seconds between actions), never
  fixed, to behave more like a human browsing session.

## How the AI insight layer works

Every product `creator.py` builds includes an **AI Insight Summary** banner
at the top of the dashboard (built into the Excel file itself) plus a
matching section in the PDF guide. This isn't static template text — it's
generated per-product by Claude based on the specific opportunity, and it's
written in the voice of an analyst explaining what the numbers *mean* and
what to *do* about them (e.g. "Crew 2 generated 22% more profit than Crew 1
— consider reassigning Crew 1's recurring routes" or "Truck 4 has exceeded
replacement economics — budget for replacement this quarter"). This is the
core differentiator: competitors sell static templates, this pipeline
positions every product as a Decision Support System that tells the buyer
what action to take.

## Troubleshooting common Etsy block issues

- **Empty/near-empty `listings.csv` after running `scraper.py`**: Etsy
  likely served a CAPTCHA or bot-check page instead of real results. Try:
  - Reducing `PAGES_PER_KEYWORD` in `scraper.py`
  - Increasing the delay ranges in `human_delay()`
  - Running during normal browsing hours rather than overnight bursts
  - Waiting a few hours before retrying from the same IP
- **`review_scraper.py` extracts 0 reviews on listings that visibly have
  reviews**: Etsy frequently changes its HTML structure. Open one listing
  URL manually in a regular browser, inspect the review section, and update
  the CSS selectors in `extract_reviews_from_html()` in `review_scraper.py`.
- **Playwright fails to launch with a missing browser error**: re-run
  `playwright install chromium`.
- **Reddit scraper returns 401/403 errors**: double-check your
  `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` and that the app type on
  Reddit's app settings page is "script", not "web app".
- **Claude API errors about the model name**: confirm `.env` doesn't
  override the model — the model is hardcoded to `claude-sonnet-4-6` in
  `analyzer.py` and `creator.py` and should not be changed to an Opus model.
- **Etsy posting fails in `lister.py`**: Etsy listing creation via the API
  also requires an OAuth 2.0 access token (not just the API key) scoped to
  `listings_w`. If you only have the API key, posts will fail with a 401 —
  complete the OAuth flow described in Etsy's developer docs and add the
  access token handling to `post_to_etsy()` before going live.
