import argparse

from src.browser import smoke_test_browser
from src.crawler import run_xianzhi_crawler, run_xianzhi_failure_replay
from src.utils import init_console, info


def build_parser():
    parser = argparse.ArgumentParser(
        prog="xz_spider.py",
        description="XZ_Spider: Xianzhi article crawler",
    )
    parser.add_argument(
        "-x",
        "--xianzhi",
        action="store_true",
        help="crawl Xianzhi articles",
    )
    parser.add_argument(
        "-rf",
        "--retry-failures",
        action="store_true",
        help="retry article ids recorded in runtime/xianzhi/failures.txt",
    )
    parser.add_argument(
        "-i",
        "--init",
        action="store_true",
        help="start the configured browser once to validate driver setup",
    )
    return parser


def main():
    init_console()
    parser = build_parser()
    args = parser.parse_args()

    if args.init:
        print(info("初始化浏览器驱动..."))
        smoke_test_browser()
        return

    if args.retry_failures:
        print(info("补跑 failures.txt 里的先知文章..."))
        run_xianzhi_failure_replay()
        return

    print(info("启动 XZ_Spider，爬取先知社区文章..."))
    run_xianzhi_crawler()
