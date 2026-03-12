import os
import re

from colorama import Fore, init


_console_ready = False


def init_console():
    global _console_ready
    if not _console_ready:
        init(autoreset=True)
        _console_ready = True


def info(message):
    return Fore.GREEN + f"[*] Info - {message}" + Fore.RESET


def warn(message):
    return Fore.YELLOW + f"[?] WARN - {message}" + Fore.RESET


def error(message):
    return Fore.RED + f"[!] Error - {message}" + Fore.RESET


def sanitize_filename(name):
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
