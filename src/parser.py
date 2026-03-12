import os
import random
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import markdownify
import requests
from bs4 import BeautifulSoup
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from selenium.common import InvalidSessionIdException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm

from config import (
    CRAWLER_HEADERS,
    THREADS_NUM,
    XIANZHI_MANUAL_WAF_TIMEOUT,
    XIANZHI_PAGE_INTERVAL,
    XIANZHI_PAGE_INTERVAL_DELTA,
    XIANZHI_PIC_BLACKLIST,
    XIANZHI_READY_TIMEOUT,
    XIANZHI_RENDER_STABILIZE_WAIT,
    XIANZHI_WAF_TIMEOUT,
)
from src.utils import ensure_parent_dir, sanitize_filename, warn


requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


def preheat_xianzhi_session(driver):
    try:
        driver.get("https://xz.aliyun.com/")
        wait_for_xianzhi_resolution(driver, allow_missing_markdown=True)
    except Exception:
        pass


def sleep_between_xianzhi_pages():
    actual_sleep = XIANZHI_PAGE_INTERVAL + random.uniform(-XIANZHI_PAGE_INTERVAL_DELTA, XIANZHI_PAGE_INTERVAL_DELTA)
    time.sleep(max(0.3, actual_sleep))


def refresh_xianzhi_page(driver, post_id, refresh_index):
    tqdm.write(warn(f"页面 {post_id} 疑似未渲染完成，执行第 {refresh_index} 次刷新复检"))
    try:
        driver.refresh()
    except Exception:
        return
    time.sleep(max(0.8, XIANZHI_RENDER_STABILIZE_WAIT))


def get_visible_page_text(driver):
    try:
        return driver.execute_script(
            "return (document.body && (document.body.innerText || document.body.textContent) || '').trim();"
        ) or ""
    except Exception:
        return safe_page_source(driver)


def preload_xianzhi_article(driver, max_passes=4):
    if not is_driver_alive(driver):
        return

    previous_length = 0
    for _ in range(max_passes):
        scan_xianzhi_page(driver)
        current_length = get_markdown_body_length(driver)
        if current_length <= previous_length:
            break
        previous_length = current_length


def scan_xianzhi_page(driver):
    try:
        total_height = driver.execute_script(
            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
        )
        viewport_height = driver.execute_script(
            "return window.innerHeight || document.documentElement.clientHeight || 900;"
        )
    except (InvalidSessionIdException, WebDriverException):
        return

    step = max(500, int(viewport_height * 0.8))
    position = 0
    while position <= total_height + step:
        try:
            driver.execute_script("window.scrollTo(0, arguments[0]);", position)
        except (InvalidSessionIdException, WebDriverException):
            return
        time.sleep(0.12)
        position += step

    time.sleep(0.4)
    try:
        driver.execute_script("window.scrollTo(0, 0);")
    except (InvalidSessionIdException, WebDriverException):
        return
    time.sleep(0.15)


def get_markdown_body_length(driver):
    try:
        markdown_nodes = driver.find_elements(By.CSS_SELECTOR, "#markdown-body")
    except (InvalidSessionIdException, WebDriverException):
        return 0
    if not markdown_nodes:
        return 0
    return len(markdown_nodes[0].text)


def get_rendered_article_html(driver):
    try:
        article_html = driver.execute_script(
            "const el=document.querySelector('#markdown-body'); return el ? el.outerHTML : '';"
        )
    except (InvalidSessionIdException, WebDriverException):
        return ""
    return article_html or ""


def get_rendered_article_context(driver, retries=3):
    article_soup = None
    article_root = None
    post_title = None

    for attempt in range(retries):
        preload_xianzhi_article(driver, max_passes=2 if attempt else 4)
        article_html = get_rendered_article_html(driver)
        article_soup = BeautifulSoup(article_html, "html.parser") if article_html else None
        article_root = article_soup.select_one("#markdown-body") if article_soup else None
        post_title = build_xianzhi_post_title(safe_driver_title(driver))

        if article_root is not None and has_visible_article_content(article_root) and post_title:
            return article_soup, article_root, post_title

        time.sleep(0.6)

    return article_soup, article_root, post_title


def wait_for_manual_waf_resolution(driver, post_id):
    if not is_waf_challenge_driver(driver):
        return False

    tqdm.write(warn(f"页面 {post_id} 触发访问验证，请在浏览器窗口内手动完成验证，最多等待 {XIANZHI_MANUAL_WAF_TIMEOUT} 秒"))
    try:
        WebDriverWait(driver, XIANZHI_MANUAL_WAF_TIMEOUT, poll_frequency=0.5).until(
            lambda current: is_xianzhi_article_ready(current) or is_xianzhi_terminal_page(current)
        )
        return True
    except TimeoutException:
        tqdm.write(warn(f"页面 {post_id} 手动验证超时"))
        return False
    except (InvalidSessionIdException, WebDriverException):
        return False


def wait_for_xianzhi_resolution(driver, allow_missing_markdown=False):
    try:
        WebDriverWait(driver, XIANZHI_READY_TIMEOUT, poll_frequency=0.2).until(
            lambda current: is_xianzhi_article_ready(current)
            or is_xianzhi_terminal_page(current, allow_missing_markdown)
        )
    except TimeoutException:
        return False

    if is_waf_challenge_driver(driver):
        try:
            WebDriverWait(driver, XIANZHI_WAF_TIMEOUT, poll_frequency=0.2).until(
                lambda current: is_xianzhi_article_ready(current)
                or is_xianzhi_terminal_page(current, allow_missing_markdown)
            )
        except TimeoutException:
            return False

    return True


def is_xianzhi_article_ready(driver):
    if not is_driver_alive(driver):
        return False

    try:
        markdown_nodes = driver.find_elements(By.CSS_SELECTOR, "#markdown-body")
    except (InvalidSessionIdException, WebDriverException):
        return False

    if not markdown_nodes:
        return False
    if len(markdown_nodes[0].text.strip()) == 0:
        return False
    return are_xianzhi_codeblocks_ready(driver)


def are_xianzhi_codeblocks_ready(driver):
    try:
        code_cards = driver.find_elements(By.CSS_SELECTOR, '#markdown-body ne-card[data-card-name="codeblock"]')
        if not code_cards:
            return True
        code_lines = driver.find_elements(By.CSS_SELECTOR, "#markdown-body .cm-line")
        return len(code_lines) > 0
    except (InvalidSessionIdException, WebDriverException):
        return False


def is_xianzhi_terminal_page(driver, allow_missing_markdown=False):
    title_text = safe_driver_title(driver)
    page_source = safe_page_source(driver)

    if contains_waf_text(page_source):
        return False
    if "400 -" in title_text or "请查看其他资讯" in page_source:
        return True
    if allow_missing_markdown and "renderData" not in page_source:
        return True
    return False


def safe_driver_title(driver):
    try:
        return driver.title or ""
    except Exception:
        return ""


def safe_page_source(driver):
    try:
        return driver.page_source or ""
    except Exception:
        return ""


def is_driver_alive(driver):
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def contains_waf_text(page_text):
    normalized = (page_text or "").replace(" ", "")
    if not normalized:
        return False

    markers = [
        "访问验证",
        "验证失败，请刷新重试",
        "通过后即可继续访问网页",
        "别离开，为了更好的访问体验，请进行验证",
        "滑动验证页面",
    ]
    return any(marker in normalized for marker in markers)


def is_waf_challenge_driver(driver):
    title_text = safe_driver_title(driver)
    if "滑动验证页面" in title_text:
        return True

    page_source = safe_page_source(driver)
    if contains_waf_text(page_source):
        return True
    return 'id="renderData"' in page_source and 'id="markdown-body"' not in page_source


def build_xianzhi_post_title(raw_title):
    title = (raw_title or "").strip()
    title = title.replace(" - 先知社区", "").replace("-先知社区", "").strip()
    title = " ".join(title.split())
    if title in {"", "-", "--", "400"}:
        return None
    return sanitize_filename(title)


def has_visible_article_content(article_root):
    text_length = len(article_root.get_text(" ", strip=True))
    code_blocks = article_root.find_all(["pre", "code"])
    paragraphs = article_root.find_all(["p", "li", "blockquote", "h1", "h2", "h3", "h4"])
    return text_length > 20 or bool(code_blocks) or len(paragraphs) > 2


def build_article_markdown(article_root, post_title):
    article_soup = BeautifulSoup(str(article_root), "html.parser")
    article_root = article_soup.select_one("#markdown-body") or article_soup
    sanitize_article_dom(article_soup, article_root)
    md_content = markdownify.markdownify(str(article_root), heading_style="ATX")
    return normalize_markdown(md_content, post_title)


def sanitize_article_dom(article_soup, article_root):
    replace_xianzhi_codeblocks(article_soup, article_root)

    for selector in [
        ".ne-viewer-header",
        ".cm-announced",
        ".cm-gutters",
        ".cm-layer",
        ".cm-tooltip",
        ".cm-selectionLayer",
        ".cm-cursorLayer",
        "button",
        "style",
        "svg",
        "use",
        "ne-heading-ext",
        "ne-heading-fold",
    ]:
        for tag in article_root.select(selector):
            tag.decompose()

    for source_name, target_name in (
        ("ne-h1", "h1"),
        ("ne-h2", "h2"),
        ("ne-h3", "h3"),
        ("ne-h4", "h4"),
        ("ne-h5", "h5"),
        ("ne-h6", "h6"),
        ("ne-p", "p"),
    ):
        for tag in article_root.find_all(source_name):
            tag.name = target_name

    for tag_name in ("ne-text", "ne-heading-content", "ne-hole"):
        for tag in article_root.find_all(tag_name):
            tag.unwrap()

    for tag in list(article_root.find_all(["span", "div"])):
        if getattr(tag, "attrs", None) is None or tag.name is None:
            continue
        classes = tag.attrs.get("class", [])
        if any(cls.startswith(("ne-icon", "cm-")) for cls in classes):
            tag.decompose()
            continue
        if tag.name == "span" and not tag.get_text(strip=True) and not tag.find(["img", "a", "code", "pre"]):
            tag.decompose()


def replace_xianzhi_codeblocks(article_soup, article_root):
    for card in list(article_root.select('ne-card[data-card-name="codeblock"]')):
        code_lines = [line.get_text("", strip=False).rstrip() for line in card.select(".cm-line")]
        code_text = "\n".join(line for line in code_lines if line.strip()).strip()
        if not code_text:
            continue

        language = ""
        mode_tag = card.select_one(".ne-codeblock-mode-name")
        if mode_tag:
            language = mode_tag.get_text(" ", strip=True)

        replacement_nodes = []
        if language:
            lang_tag = article_soup.new_tag("p")
            lang_tag.string = language
            replacement_nodes.append(lang_tag)

        pre_tag = article_soup.new_tag("pre")
        code_tag = article_soup.new_tag("code")
        code_tag.string = code_text
        pre_tag.append(code_tag)
        replacement_nodes.append(pre_tag)

        container = card.parent if card.parent and card.parent.name == "ne-hole" else card
        container.replace_with(*replacement_nodes)


def normalize_markdown(md_content, post_title):
    md_content = md_content.replace("\u200b", "").replace("\ufeff", "")
    md_content = md_content.replace("返回文档", "")
    md_content = normalize_markdown_whitespace(md_content)

    lines = md_content.splitlines()
    published_at = ""
    clean_title = post_title.strip()

    if lines and len(lines[0]) == 16 and lines[0][4] == "-" and lines[0][7] == "-":
        published_at = lines[0]
        lines = lines[1:]

    while lines and not lines[0].strip():
        lines = lines[1:]

    if lines and lines[0].lstrip("#").strip() == clean_title:
        lines = lines[1:]

    lines = merge_codeblock_language_labels(lines)
    body = "\n".join(lines).strip()

    header = [f"# {clean_title}"]
    if published_at:
        header.append(f"> 发布于：{published_at}")
    if body:
        header.append(body)
    return "\n\n".join(header).strip() + "\n"


def normalize_markdown_whitespace(md_content):
    normalized = []
    in_code_block = False
    blank_count = 0

    for raw_line in md_content.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            if blank_count:
                normalized.append("")
                blank_count = 0
            normalized.append(stripped)
            in_code_block = not in_code_block
            continue

        if in_code_block:
            normalized.append(raw_line.rstrip())
            continue

        if not stripped:
            blank_count += 1
            continue

        if blank_count:
            normalized.append("")
            blank_count = 0
        normalized.append(stripped)

    return "\n".join(normalized).strip()


def merge_codeblock_language_labels(lines):
    merged = []
    index = 0

    while index < len(lines):
        line = lines[index]
        language = canonicalize_code_language(line)
        if not language:
            merged.append(line)
            index += 1
            continue

        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1

        if next_index < len(lines) and lines[next_index].strip() == "```":
            merged.append(f"```{language}")
            index = next_index + 1
            continue

        merged.append(line)
        index += 1

    return merged


def canonicalize_code_language(line):
    normalized = (line or "").strip().replace("复制代码", "").strip().lower()
    language_map = {
        "python": "python",
        "py": "python",
        "plain text": "text",
        "plaintext": "text",
        "text": "text",
        "bash": "bash",
        "shell": "bash",
        "sh": "bash",
        "javascript": "javascript",
        "js": "javascript",
        "java": "java",
        "c": "c",
        "c++": "cpp",
        "cpp": "cpp",
        "go": "go",
        "php": "php",
        "ruby": "ruby",
        "rust": "rust",
        "sql": "sql",
        "html": "html",
        "xml": "xml",
        "json": "json",
        "yaml": "yaml",
        "toml": "toml",
        "sage": "python",
    }
    return language_map.get(normalized)


def process_images(md_content, img_tags):
    for img_tag in img_tags:
        img_src = img_tag.get("src")
        if not img_src:
            continue
        img_name = os.path.basename(img_src).replace("!small", "").split("?")[0].split("#")[0]
        md_content = md_content.replace(img_src, f"images/{img_name}")
    return md_content


def save_markdown(post_id, post_title, md_content, filename):
    ensure_parent_dir(filename)
    with open(filename, "w", encoding="utf-8") as handle:
        handle.write(md_content)
    tqdm.write(f"[*] Info - {post_id}-{post_title} 爬取完成")


def is_valid_remote_url(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if hostname in {"localhost", "127.0.0.1"}:
            return False
        if hostname.startswith(("192.168.", "10.", "172.")):
            return False
        if parsed.port == 7541:
            return False
        if hostname:
            socket.gethostbyname(hostname)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except (socket.gaierror, ValueError, AttributeError):
        return False


def download_images(img_tags, images_path, crawler_headers, max_threads=THREADS_NUM):
    session = requests.Session()
    session.headers.update(crawler_headers)
    image_sources = []
    seen_sources = set()

    for img_tag in img_tags:
        img_src = img_tag.get("src")
        if not img_src or img_src in seen_sources:
            continue
        seen_sources.add(img_src)
        image_sources.append(img_src)

    if not image_sources:
        return

    os.makedirs(images_path, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, max_threads)) as executor:
        futures = [
            executor.submit(download_image_with_session, img_src, images_path, session)
            for img_src in image_sources
        ]
        for future in futures:
            future.result()


def download_image_with_session(img_src, images_path, session):
    try:
        if not img_src:
            return
        if any(blacklisted in img_src for blacklisted in XIANZHI_PIC_BLACKLIST):
            return

        if img_src.startswith("/"):
            img_src = "https://xz.aliyun.com" + img_src
        if not is_valid_remote_url(img_src):
            return

        img_name = os.path.basename(img_src).replace("!small", "").split("?")[0].split("#")[0]
        image_path = os.path.join(images_path, img_name)
        if os.path.exists(image_path):
            return

        response = session.get(
            img_src,
            headers={
                "Referer": "https://xz.aliyun.com/",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "User-Agent": session.headers.get("User-Agent", CRAWLER_HEADERS[0]["User-Agent"]),
            },
            timeout=(5, 15),
            verify=False,
            allow_redirects=True,
        )
        if response.status_code != 200:
            return
        if not response.headers.get("content-type", "").startswith("image/"):
            return

        with open(image_path, "wb") as handle:
            handle.write(response.content)
    except requests.RequestException:
        return
