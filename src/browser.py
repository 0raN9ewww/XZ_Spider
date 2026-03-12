import os
import re
import shutil
import subprocess

from selenium import webdriver
from selenium.common import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from config import (
    BROWSER_HEADLESS,
    BROWSER_TYPE,
    CHROME_DRIVER_PATH,
    CRAWLER_HEADERS,
    EDGE_DRIVER_PATH,
    XIANZHI_READY_TIMEOUT,
    XIANZHI_WAF_TIMEOUT,
)
from src.utils import info, warn


SUPPORTED_BROWSERS = {"chrome", "edge"}


def smoke_test_browser():
    driver = None
    browser_type = get_browser_type()
    try:
        driver = init_browser()
        print(info(f"已成功初始化本机 {browser_type} 浏览器"))
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def init_browser(disable_images=False, page_load_strategy="normal", user_data_dir=None):
    browser_type = get_browser_type()
    options = build_browser_options(browser_type, disable_images, page_load_strategy, user_data_dir)
    service = build_browser_service(browser_type)

    try:
        if browser_type == "chrome":
            driver = webdriver.Chrome(options=options, service=service)
        else:
            driver = webdriver.Edge(options=options, service=service)
    except SessionNotCreatedException as exc:
        raise RuntimeError(build_driver_mismatch_message(browser_type, service, exc)) from exc

    configure_stealth(driver, browser_type)
    print(info(f"已成功初始化本机 {browser_type} 浏览器"))
    return driver


def get_browser_type():
    browser_type = str(BROWSER_TYPE).strip().lower()
    if browser_type not in SUPPORTED_BROWSERS:
        raise ValueError(f"不支持的浏览器类型: {BROWSER_TYPE}")
    return browser_type


def build_browser_options(browser_type, disable_images, page_load_strategy, user_data_dir):
    options = ChromeOptions() if browser_type == "chrome" else EdgeOptions()
    options.page_load_strategy = page_load_strategy
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--window-size=1440,2200")
    options.add_argument(f"--user-agent={get_browser_user_agent(browser_type)}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if BROWSER_HEADLESS:
        options.add_argument("--headless=new")

    if user_data_dir:
        profile_path = os.path.abspath(user_data_dir)
        os.makedirs(profile_path, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_path}")

    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    if disable_images:
        prefs["profile.managed_default_content_settings.images"] = 2
        prefs["profile.default_content_setting_values.images"] = 2
    options.add_experimental_option("prefs", prefs)
    return options


def build_browser_service(browser_type):
    if browser_type == "chrome":
        driver_path = resolve_driver_path(browser_type, CHROME_DRIVER_PATH, "chromedriver.exe")
        return ChromeService(executable_path=driver_path) if driver_path else ChromeService()

    driver_path = resolve_driver_path(browser_type, EDGE_DRIVER_PATH, "msedgedriver.exe")
    return EdgeService(executable_path=driver_path) if driver_path else EdgeService()


def resolve_driver_path(browser_type, configured_path, executable_name):
    driver_path = str(configured_path).strip()
    if driver_path and os.path.exists(driver_path):
        if is_driver_compatible(browser_type, driver_path):
            return driver_path
        print(warn(f"{browser_type} driver 与浏览器主版本不匹配，已跳过 {driver_path}"))
        return ""

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in (
        os.path.join(os.getcwd(), executable_name),
        os.path.join(project_root, executable_name),
    ):
        if candidate and os.path.exists(candidate) and is_driver_compatible(browser_type, candidate):
            return candidate
    return ""


def is_driver_compatible(browser_type, driver_path):
    driver_major = get_driver_major_version(driver_path)
    browser_major = get_browser_major_version(browser_type)
    if not driver_major or not browser_major:
        return True
    return driver_major == browser_major


def get_driver_major_version(driver_path):
    return extract_major_version(get_command_version_output([driver_path, "--version"]))


def get_browser_major_version(browser_type):
    for candidate in get_browser_binary_candidates(browser_type):
        if not candidate or not os.path.exists(candidate):
            continue
        major = extract_major_version(get_command_version_output([candidate, "--version"]))
        if major:
            return major
    return None


def get_browser_binary_candidates(browser_type):
    if browser_type == "edge":
        return [
            shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]

    return [
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]


def get_command_version_output(command):
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def extract_major_version(version_text):
    match = re.search(r"(\d+)\.", version_text or "")
    return int(match.group(1)) if match else None


def build_driver_mismatch_message(browser_type, service, exc):
    service_path = getattr(service, "path", "") or getattr(service, "_path", "") or ""
    driver_major = get_driver_major_version(service_path) if service_path and os.path.exists(service_path) else None
    browser_major = get_browser_major_version(browser_type)

    parts = [str(exc).strip()]
    if driver_major and browser_major and driver_major != browser_major:
        parts.append(f"检测到 {browser_type} driver 主版本为 {driver_major}，浏览器主版本为 {browser_major}。")
        parts.append("请更新对应 driver，或删除项目内的旧 driver 后重试。")
    if service_path:
        parts.append(f"当前 driver 路径: {service_path}")
    return " ".join(parts)


def get_browser_user_agent(browser_type):
    configured_user_agent = CRAWLER_HEADERS[0].get("User-Agent", "").strip()
    if browser_type == "edge":
        if configured_user_agent and "Edg/" in configured_user_agent:
            return configured_user_agent
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
        )
    if configured_user_agent:
        return configured_user_agent
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )


def configure_stealth(driver, browser_type):
    stealth_script = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);
"""
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": get_browser_user_agent(browser_type),
                "acceptLanguage": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "platform": "Windows",
            },
        )
    except Exception:
        pass

    try:
        driver.set_page_load_timeout(XIANZHI_READY_TIMEOUT + XIANZHI_WAF_TIMEOUT)
    except Exception:
        pass
