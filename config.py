import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Browser
BROWSER_TYPE = "chrome"
BROWSER_HEADLESS = False
CHROME_DRIVER_PATH = (
    os.path.join(BASE_DIR, "chromedriver.exe")
    if os.path.exists(os.path.join(BASE_DIR, "chromedriver.exe"))
    else ""
)
EDGE_DRIVER_PATH = (
    os.path.join(BASE_DIR, "msedgedriver.exe")
    if os.path.exists(os.path.join(BASE_DIR, "msedgedriver.exe"))
    else ""
)


# Output
FILE_SAVE_PATH = r"F:\arcitle"
XIANZHI_RUNTIME_DIR = os.path.join(BASE_DIR, "runtime", "xianzhi")
XIANZHI_CHROME_USER_DATA_DIR = ""


# Requests
CRAWLER_HEADERS = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        )
    }
]
THREADS_NUM = 4


# Crawl range
XIANZHI_PAGE_START = 90664
XIANZHI_PAGE_END = 91700


# Page loading
XIANZHI_READY_TIMEOUT = 12
XIANZHI_WAF_TIMEOUT = 8
XIANZHI_WAF_RETRIES = 2
XIANZHI_SOFT_REFRESH_RETRIES = 1
XIANZHI_RENDER_STABILIZE_WAIT = 2.5


# Rate limiting
XIANZHI_PAGE_INTERVAL = 1.6
XIANZHI_PAGE_INTERVAL_DELTA = 0.6
XIANZHI_WAF_COOLDOWN = 20
XIANZHI_MAX_CONSECUTIVE_WAF = 2


# Runtime behavior
XIANZHI_MANUAL_WAF = True
XIANZHI_MANUAL_WAF_TIMEOUT = 180
XIANZHI_ENABLE_LOCAL_SKIP = True
XIANZHI_RESUME_LAST_INDEX = True
XIANZHI_RECORD_FAILURES = True


# Content filters
XIANZHI_PIC_BLACKLIST = [
    "default_avatar.png",
    "/avatars/",
]
