# XZ_Spider

`XZ_Spider` is a focused crawler for the Xianzhi community (`xz.aliyun.com`).
It opens article pages with Selenium, waits for the rendered article body,
extracts the main content, restores code blocks, downloads inline images, and
stores each article as a local Markdown file.

This repository has been reduced to a Xianzhi-only codebase. Legacy crawler
code for other sites has been removed.

## Features

- Crawl Xianzhi articles by numeric article ID range
- Support both `Chrome` and `Edge`
- Resume from the last processed article
- Skip articles that already exist locally
- Retry failed article IDs from `runtime/xianzhi/failures.txt`
- Convert rendered article content to Markdown
- Restore Xianzhi code blocks into fenced Markdown blocks
- Download article images and rewrite links to local paths

## Project Layout

```text
XZ_Spider/
├─ xz_spider.py
├─ config.py
├─ requirements.txt
├─ runtime/
│  └─ xianzhi/
│     ├─ checkpoint.txt
│     └─ failures.txt
└─ src/
   ├─ app.py
   ├─ browser.py
   ├─ crawler.py
   ├─ parser.py
   ├─ runtime.py
   └─ utils.py
```

## Requirements

- Python 3.11+ recommended
- Windows environment
- Google Chrome or Microsoft Edge installed
- Matching browser driver if Selenium Manager cannot resolve one automatically

The crawler currently targets a Windows-style local environment and assumes the
browser binaries are in standard installation paths.

## Installation

Using `uv`:

```powershell
uv venv
uv pip install -r requirements.txt
```

Using `pip`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Dependencies

The project depends on:

- `selenium`
- `beautifulsoup4`
- `markdownify`
- `requests`
- `tqdm`
- `colorama`

See [requirements.txt](/e:/spider/XZ_Spider/requirements.txt).

## Configuration

All runtime settings live in [config.py](/e:/spider/XZ_Spider/config.py).

### Core settings

- `BROWSER_TYPE`
  - Valid values: `chrome`, `edge`
  - Selects which Selenium driver to use

- `BROWSER_HEADLESS`
  - `False` by default
  - Keep this disabled if you want to watch what the crawler is doing or solve a manual challenge in the browser window

- `FILE_SAVE_PATH`
  - Output root for generated Markdown files and image downloads
  - The crawler writes Xianzhi articles under `FILE_SAVE_PATH/xianzhi/`

### Browser driver settings

- `CHROME_DRIVER_PATH`
- `EDGE_DRIVER_PATH`

If these are empty, Selenium Manager is allowed to resolve the driver.
If you prefer local drivers, place `chromedriver.exe` or `msedgedriver.exe`
in the project root, or set the explicit path in `config.py`.

### Crawl range

- `XIANZHI_PAGE_START`
- `XIANZHI_PAGE_END`

These define the inclusive numeric article ID range.

Example:

```python
XIANZHI_PAGE_START = 17226
XIANZHI_PAGE_END = 91675
```

### Runtime and recovery settings

- `XIANZHI_RUNTIME_DIR`
  - Stores checkpoint and failure tracking files

- `XIANZHI_ENABLE_LOCAL_SKIP`
  - If enabled, existing Markdown files are indexed by article ID and skipped

- `XIANZHI_RESUME_LAST_INDEX`
  - If enabled, crawling resumes from the value stored in `checkpoint.txt`

- `XIANZHI_RECORD_FAILURES`
  - If enabled, failed article IDs are written to `failures.txt`

### Timing and page handling

- `XIANZHI_READY_TIMEOUT`
  - Main page-ready timeout

- `XIANZHI_WAF_TIMEOUT`
  - Extra wait time after the page appears to be in a challenge state

- `XIANZHI_WAF_RETRIES`
  - Number of fetch retries before a page is marked as failed

- `XIANZHI_SOFT_REFRESH_RETRIES`
  - Number of refresh attempts when the page looks partially rendered but incomplete

- `XIANZHI_RENDER_STABILIZE_WAIT`
  - Delay after refresh before checking the page again

- `XIANZHI_PAGE_INTERVAL`
- `XIANZHI_PAGE_INTERVAL_DELTA`
  - Delay between pages with a small random jitter

- `XIANZHI_WAF_COOLDOWN`
  - Backoff time after a detected challenge/failure state

- `XIANZHI_MAX_CONSECUTIVE_WAF`
  - Stop the current run after too many consecutive challenge pages

### Session persistence

- `XIANZHI_CHROME_USER_DATA_DIR`

If set to a non-empty path, the crawler will reuse a browser profile directory.
This can help preserve cookies and session state between runs. If left empty,
each run starts with a temporary Selenium session.

### Manual challenge handling

- `XIANZHI_MANUAL_WAF`
  - If enabled, the crawler waits for manual resolution when a visible access verification page is detected

- `XIANZHI_MANUAL_WAF_TIMEOUT`
  - Maximum wait time for manual resolution

## Usage

### 1. Validate browser setup

Start the configured browser once and confirm the driver can create a session:

```powershell
uv run xz_spider.py --init
```

### 2. Run the crawler

```powershell
uv run xz_spider.py -x
```

If no special mode is provided, the application defaults to the normal Xianzhi crawl path.

### 3. Retry failed article IDs

```powershell
uv run xz_spider.py --retry-failures
```

This reads [failures.txt](/e:/spider/XZ_Spider/runtime/xianzhi/failures.txt),
retries those article IDs, removes successful ones, and keeps unresolved ones.

## Output Structure

Generated files are stored under:

```text
FILE_SAVE_PATH/
└─ xianzhi/
   ├─ 18062-Example Title.md
   └─ images/
      ├─ image_1.png
      └─ image_2.jpg
```

Each saved Markdown file is named:

```text
<article_id>-<article_title>.md
```

Image references inside the Markdown are rewritten to local relative paths such as:

```text
images/example.png
```

## Runtime Files

### Checkpoint

[checkpoint.txt](/e:/spider/XZ_Spider/runtime/xianzhi/checkpoint.txt)

Stores the last processed article ID and status. This is used for resume mode.

### Failures

[failures.txt](/e:/spider/XZ_Spider/runtime/xianzhi/failures.txt)

Stores failed article IDs and their last known reason, for example:

```text
18080	waf
18082	missing-article-root
18090	load-failed
```

## Crawl Workflow

For each article ID, the crawler:

1. Opens `https://xz.aliyun.com/news/<id>`
2. Waits for the rendered page state to stabilize
3. Distinguishes between:
   - valid article page
   - likely challenge/access-verification page
   - partially rendered page
   - failed page load
4. Soft-refreshes incomplete pages when appropriate
5. Extracts the live `#markdown-body` content
6. Converts the cleaned DOM into Markdown
7. Downloads article images
8. Saves the Markdown file
9. Updates checkpoint and failure tracking files

## Markdown Conversion Notes

The parser is tuned for Xianzhi article structure:

- Only the rendered article body is converted
- UI elements and decorative nodes are stripped
- Xianzhi code cards are transformed into `pre/code` blocks before Markdown conversion
- Language labels such as `Python` and `Plain Text` are merged into fenced code blocks
- Leading indentation inside fenced code blocks is preserved as much as possible

## Browser Compatibility

The current implementation supports:

- `Chrome`
- `Edge`

Set `BROWSER_TYPE` in [config.py](/e:/spider/XZ_Spider/config.py) accordingly.

## Troubleshooting

### Browser driver version mismatch

If you see a Selenium session creation error mentioning browser and driver version mismatch:

- update your local driver
- or remove the outdated local driver from the project root
- then run `uv run xz_spider.py --init` again

### Articles open manually but fail in Selenium

This usually means the page is rendered differently in an automated session, or the
access verification page is being shown to Selenium. In that case:

- keep `BROWSER_HEADLESS = False`
- consider enabling `XIANZHI_MANUAL_WAF`
- reduce crawl speed if needed
- use the failure replay mode after conditions improve

### Repeated challenge pages

If many consecutive pages are recorded as `waf`:

- stop the current run
- wait before starting again
- preserve your progress with the existing checkpoint and failures files

### Missing article body

Some pages may exist but still fail DOM extraction due to incomplete rendering or
page-specific structure differences. Those pages are written to `failures.txt` for retry.

## Notes

- This project does not guarantee that every Xianzhi page can be fetched successfully.
- Xianzhi pages may include dynamic rendering and access verification flows.
- The crawler is optimized for recovery, repeatability, and Markdown quality rather than maximum raw speed.
