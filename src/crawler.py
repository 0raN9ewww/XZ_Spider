import os
import random
import time

from tqdm import tqdm, trange

from config import (
    CRAWLER_HEADERS,
    FILE_SAVE_PATH,
    XIANZHI_CHROME_USER_DATA_DIR,
    XIANZHI_MANUAL_WAF,
    XIANZHI_MAX_CONSECUTIVE_WAF,
    XIANZHI_PAGE_END,
    XIANZHI_PAGE_START,
    XIANZHI_RECORD_FAILURES,
    XIANZHI_SOFT_REFRESH_RETRIES,
    XIANZHI_WAF_COOLDOWN,
    XIANZHI_WAF_RETRIES,
)
from src.browser import init_browser
from src.parser import (
    build_article_markdown,
    contains_waf_text,
    download_images,
    get_markdown_body_length,
    get_rendered_article_context,
    get_visible_page_text,
    is_driver_alive,
    is_waf_challenge_driver,
    preheat_xianzhi_session,
    process_images,
    refresh_xianzhi_page,
    save_markdown,
    sleep_between_xianzhi_pages,
    wait_for_manual_waf_resolution,
    wait_for_xianzhi_resolution,
)
from src.runtime import (
    load_existing_post_ids,
    load_failure_map,
    load_resume_index,
    save_checkpoint,
    save_failure_map,
)
from src.utils import error, info, warn


def run_xianzhi_crawler():
    if not XIANZHI_PAGE_START or not XIANZHI_PAGE_END:
        raise SystemExit(error("请先在 config.py 中设置先知文章的起止编号"))

    failure_map = load_failure_map()
    driver = init_browser(
        disable_images=True,
        page_load_strategy="eager",
        user_data_dir=XIANZHI_CHROME_USER_DATA_DIR,
    )
    try:
        preheat_xianzhi_session(driver)
        crawl_range(driver, failure_map)
    finally:
        save_failure_map(failure_map)
        try:
            driver.quit()
        except Exception:
            pass


def run_xianzhi_failure_replay():
    failure_map = load_failure_map()
    if not failure_map:
        tqdm.write(info("failures.txt 为空，没有需要补跑的页面"))
        return

    driver = init_browser(
        disable_images=True,
        page_load_strategy="eager",
        user_data_dir=XIANZHI_CHROME_USER_DATA_DIR,
    )
    try:
        preheat_xianzhi_session(driver)
        replay_failures(driver, failure_map)
    finally:
        save_failure_map(failure_map)
        try:
            driver.quit()
        except Exception:
            pass


def crawl_range(driver, failure_map):
    existing_post_ids = load_existing_post_ids()
    start_index = load_resume_index()
    cached_title = None
    consecutive_waf_hits = 0

    if existing_post_ids:
        tqdm.write(info(f"本地已索引 {len(existing_post_ids)} 篇先知文章，启用快速跳过"))
    if start_index > XIANZHI_PAGE_START:
        tqdm.write(info(f"从断点 {start_index} 继续爬取"))

    for post_id in trange(start_index, XIANZHI_PAGE_END + 1, desc="[+] 正在爬取先知社区文章"):
        if post_id in existing_post_ids:
            save_checkpoint(post_id, "local-skip")
            continue

        status, cached_title = crawl_single_post(driver, post_id, existing_post_ids, cached_title, failure_map)
        save_failure_map(failure_map)

        if status == "session-lost":
            break
        consecutive_waf_hits = handle_waf_backoff(status, consecutive_waf_hits)
        if consecutive_waf_hits < 0:
            break


def replay_failures(driver, failure_map):
    existing_post_ids = load_existing_post_ids()
    cached_title = None
    consecutive_waf_hits = 0
    failure_ids = list(sorted(failure_map))

    for post_id in tqdm(failure_ids, desc="[+] 正在补跑 failures.txt"):
        status, cached_title = crawl_single_post(driver, post_id, existing_post_ids, cached_title, failure_map)
        save_failure_map(failure_map)

        if status == "session-lost":
            break
        consecutive_waf_hits = handle_waf_backoff(status, consecutive_waf_hits, replay_mode=True)
        if consecutive_waf_hits < 0:
            break


def handle_waf_backoff(status, consecutive_waf_hits, replay_mode=False):
    if status != "waf":
        return 0

    consecutive_waf_hits += 1
    if consecutive_waf_hits >= XIANZHI_MAX_CONSECUTIVE_WAF:
        if replay_mode:
            tqdm.write(error(f"连续 {consecutive_waf_hits} 页命中访问验证，已停止本次 failures 补跑"))
        else:
            tqdm.write(error(f"连续 {consecutive_waf_hits} 页命中访问验证，已停止本次运行"))
        return -1

    cooldown_seconds = max(1, int(XIANZHI_WAF_COOLDOWN * max(1, consecutive_waf_hits)))
    tqdm.write(warn(f"进入 WAF 冷却，休眠 {cooldown_seconds} 秒"))
    time.sleep(cooldown_seconds)
    return consecutive_waf_hits


def crawl_single_post(driver, post_id, existing_post_ids, cached_title, failure_map):
    fetch_status = fetch_xianzhi_page(driver, f"https://xz.aliyun.com/news/{post_id}", post_id)
    if fetch_status != "ok":
        if not is_driver_alive(driver):
            tqdm.write(error("浏览器会话已断开，请重新启动爬虫后继续"))
            return "session-lost", cached_title
        remember_failure(failure_map, post_id, fetch_status)
        save_checkpoint(post_id, fetch_status)
        return fetch_status, cached_title

    _, article_root, post_title = get_rendered_article_context(driver)
    if not post_title:
        tqdm.write(error(f"{post_id} 未找到有效标题"))
        remember_failure(failure_map, post_id, "missing-title")
        save_checkpoint(post_id, "missing-title")
        sleep_between_xianzhi_pages()
        return "missing-title", cached_title

    if cached_title and post_title == cached_title:
        tqdm.write(warn(f"{post_id}-{post_title} 标题与上一篇相同，跳过"))
        remember_failure(failure_map, post_id, "duplicate-title")
        save_checkpoint(post_id, "duplicate-title")
        sleep_between_xianzhi_pages()
        return "duplicate-title", cached_title

    filename = os.path.join(FILE_SAVE_PATH, "xianzhi", f"{post_id}-{post_title}.md")
    if os.path.exists(filename):
        existing_post_ids.add(post_id)
        failure_map.pop(post_id, None)
        save_checkpoint(post_id, "exists")
        sleep_between_xianzhi_pages()
        return "exists", post_title

    if article_root is None:
        tqdm.write(warn(f"页面 {post_id} 未找到正文容器，跳过"))
        remember_failure(failure_map, post_id, "missing-article-root")
        save_checkpoint(post_id, "missing-article-root")
        sleep_between_xianzhi_pages()
        return "missing-article-root", cached_title

    img_tags = article_root.find_all("img")
    download_images(
        img_tags,
        os.path.join(FILE_SAVE_PATH, "xianzhi", "images"),
        random.choice(CRAWLER_HEADERS),
    )

    md_content = build_article_markdown(article_root, post_title)
    if "请查看其他资讯" in md_content:
        tqdm.write(warn(f"页面 {post_id} 显示“请查看其他资讯”，跳过"))
        remember_failure(failure_map, post_id, "terminal-page")
        save_checkpoint(post_id, "terminal-page")
        sleep_between_xianzhi_pages()
        return "terminal-page", cached_title

    md_content = process_images(md_content, img_tags)
    save_markdown(post_id, post_title, md_content, filename)
    existing_post_ids.add(post_id)
    failure_map.pop(post_id, None)
    save_checkpoint(post_id, "saved")
    sleep_between_xianzhi_pages()
    return "saved", post_title


def remember_failure(failure_map, post_id, reason):
    if XIANZHI_RECORD_FAILURES:
        failure_map[post_id] = reason


def fetch_xianzhi_page(driver, url, post_id):
    last_status = "load-failed"

    for attempt in range(1, XIANZHI_WAF_RETRIES + 2):
        try:
            driver.get(url)
        except Exception:
            if not is_driver_alive(driver):
                return "session-lost"

        wait_for_xianzhi_resolution(driver)
        page_status = classify_xianzhi_page(driver)
        if page_status == "ok":
            return "ok"

        if page_status == "waf" and XIANZHI_MANUAL_WAF and wait_for_manual_waf_resolution(driver, post_id):
            page_status = classify_xianzhi_page(driver)
            if page_status == "ok":
                return "ok"

        if page_status in {"render-pending", "load-failed"}:
            for refresh_index in range(1, XIANZHI_SOFT_REFRESH_RETRIES + 1):
                refresh_xianzhi_page(driver, post_id, refresh_index)
                wait_for_xianzhi_resolution(driver)
                page_status = classify_xianzhi_page(driver)
                if page_status == "ok":
                    return "ok"
                if page_status == "waf":
                    break

        last_status = page_status
        if attempt <= XIANZHI_WAF_RETRIES:
            if page_status == "waf":
                tqdm.write(warn(f"页面 {post_id} 命中 WAF，第 {attempt} 次重试"))
            else:
                tqdm.write(warn(f"页面 {post_id} 加载未完成，第 {attempt} 次重试"))
            time.sleep(min(1.5 * attempt, 3))

    if last_status == "waf":
        tqdm.write(warn(f"页面 {post_id} 连续命中 WAF 或加载失败，跳过"))
    else:
        tqdm.write(warn(f"页面 {post_id} 多次刷新后仍未完成渲染，跳过"))
    return last_status


def classify_xianzhi_page(driver):
    _, article_root, post_title = get_rendered_article_context(driver, retries=3)
    if article_root is not None and post_title:
        return "ok"

    visible_text = get_visible_page_text(driver)
    markdown_length = get_markdown_body_length(driver)

    if markdown_length > 40 and post_title:
        return "render-pending"
    if contains_waf_text(visible_text) and markdown_length <= 40:
        return "waf"
    if is_waf_challenge_driver(driver):
        return "waf"
    if article_root is not None or markdown_length > 0:
        return "render-pending"
    return "load-failed"
