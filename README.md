# XZ_Spider

`XZ_Spider` is a crawler for Xianzhi articles on `xz.aliyun.com`.
It loads article pages with Selenium, extracts the rendered article body,
converts the content to Markdown, and downloads inline images.

## Features

- Crawl articles by numeric ID range
- Support `Chrome` and `Edge`
- Save articles as Markdown
- Restore code blocks from rendered page content
- Download article images to local storage
- Resume from a checkpoint
- Retry failed article IDs from a failure list

## Structure

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

## Installation

```powershell
uv venv
uv pip install -r requirements.txt
```

Or:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Edit [config.py](/e:/spider/XZ_Spider/config.py).

Main settings:

- `BROWSER_TYPE`: `chrome` or `edge`
- `FILE_SAVE_PATH`: output directory for Markdown and images
- `XIANZHI_PAGE_START`: first article ID
- `XIANZHI_PAGE_END`: last article ID
- `XIANZHI_CHROME_USER_DATA_DIR`: optional browser profile directory

Optional local drivers:

- `chromedriver.exe`
- `msedgedriver.exe`

## Usage

Validate browser setup:

```powershell
uv run xz_spider.py --init
```

Run the crawler:

```powershell
uv run xz_spider.py -x
```

Retry failed article IDs:

```powershell
uv run xz_spider.py --retry-failures
```

## Output

Articles are saved under:

```text
FILE_SAVE_PATH/xianzhi/
```

Images are saved under:

```text
FILE_SAVE_PATH/xianzhi/images/
```

## Runtime Files

- [checkpoint.txt](/e:/spider/XZ_Spider/runtime/xianzhi/checkpoint.txt): last processed article ID
- [failures.txt](/e:/spider/XZ_Spider/runtime/xianzhi/failures.txt): failed article IDs and reasons

## Notes

- Some pages may require manual verification in the browser window.
- Browser and driver versions must be compatible.
- Existing Markdown files are skipped automatically when local skip is enabled.
