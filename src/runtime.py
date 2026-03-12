import os
import re

from config import (
    FILE_SAVE_PATH,
    XIANZHI_ENABLE_LOCAL_SKIP,
    XIANZHI_PAGE_START,
    XIANZHI_RESUME_LAST_INDEX,
    XIANZHI_RUNTIME_DIR,
)
from src.utils import ensure_dir


def get_runtime_paths():
    checkpoint_path = os.path.join(XIANZHI_RUNTIME_DIR, "checkpoint.txt")
    failures_path = os.path.join(XIANZHI_RUNTIME_DIR, "failures.txt")
    return XIANZHI_RUNTIME_DIR, checkpoint_path, failures_path


def ensure_runtime_dir():
    ensure_dir(XIANZHI_RUNTIME_DIR)


def load_failure_map():
    _, _, failures_path = get_runtime_paths()
    if not os.path.exists(failures_path):
        return {}

    failure_map = {}
    with open(failures_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            try:
                post_id = int(parts[0])
            except ValueError:
                continue
            reason = parts[1] if len(parts) > 1 else "unknown"
            failure_map[post_id] = reason
    return failure_map


def save_failure_map(failure_map):
    ensure_runtime_dir()
    _, _, failures_path = get_runtime_paths()
    with open(failures_path, "w", encoding="utf-8") as handle:
        for post_id in sorted(failure_map):
            handle.write(f"{post_id}\t{failure_map[post_id]}\n")


def load_existing_post_ids():
    if not XIANZHI_ENABLE_LOCAL_SKIP:
        return set()

    articles_dir = os.path.join(FILE_SAVE_PATH, "xianzhi")
    if not os.path.isdir(articles_dir):
        return set()

    existing = set()
    for entry in os.scandir(articles_dir):
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        match = re.match(r"^(\d+)-", entry.name)
        if match:
            existing.add(int(match.group(1)))
    return existing


def load_resume_index():
    if not XIANZHI_RESUME_LAST_INDEX:
        return XIANZHI_PAGE_START

    _, checkpoint_path, _ = get_runtime_paths()
    if not os.path.exists(checkpoint_path):
        return XIANZHI_PAGE_START

    try:
        with open(checkpoint_path, "r", encoding="utf-8") as handle:
            checkpoint = int(handle.read().strip().split("\t", 1)[0])
    except Exception:
        return XIANZHI_PAGE_START

    return max(XIANZHI_PAGE_START, checkpoint + 1)


def save_checkpoint(post_id, reason):
    ensure_runtime_dir()
    _, checkpoint_path, _ = get_runtime_paths()
    with open(checkpoint_path, "w", encoding="utf-8") as handle:
        handle.write(f"{post_id}\t{reason}\n")
