"""Shared browser helpers for JS-rendered recruitment pages."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BROWSER_PROFILE_ROOT = PROJECT_ROOT / "data" / ".browser_profiles"


def find_chromium_path() -> str | None:
    """Find a local Chrome/Edge executable for DrissionPage."""
    env_candidates = [
        os.getenv("CHROME_PATH"),
        os.getenv("EDGE_PATH"),
        os.getenv("CHROMIUM_PATH"),
    ]
    path_candidates = [
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]

    for candidate in [*env_candidates, *path_candidates]:
        if candidate and Path(candidate).exists():
            return str(candidate)

    return None


def build_chromium_options(profile_name: str, *, headless: bool = True):
    """Create ChromiumOptions using the installed browser, or return None."""
    try:
        from DrissionPage import ChromiumOptions
    except ImportError:
        logger.warning("DrissionPage is not installed; browser crawling disabled.")
        return None

    browser_path = find_chromium_path()
    if not browser_path:
        logger.warning("No Chrome/Edge executable found; browser crawling disabled.")
        return None

    profile_dir = BROWSER_PROFILE_ROOT / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    options = ChromiumOptions()
    options.set_browser_path(browser_path)
    options.set_user_data_path(str(profile_dir))
    if hasattr(options, "auto_port"):
        options.auto_port(True)
    options.headless(headless)
    apply_browser_hardening(options)
    return options


def apply_browser_hardening(options):
    """Apply browser flags that reduce noisy startup and extension side effects."""
    options.set_argument("--disable-blink-features=AutomationControlled")
    # Windows Chrome does not support --no-sandbox, so skip it there.
    if os.name != "nt":
        options.set_argument("--no-sandbox")
    options.set_argument("--disable-gpu")
    options.set_argument("--disable-dev-shm-usage")
    options.set_argument("--no-first-run")
    options.set_argument("--no-default-browser-check")
    options.set_argument("--disable-extensions")
    options.set_argument("--disable-component-extensions-with-background-pages")
    options.set_argument("--disable-popup-blocking")
    options.set_argument("--disable-background-networking")
    options.set_argument("--disable-sync")
    options.set_argument("--disable-notifications")
    return options


def create_page(profile_name: str, *, headless: bool = True):
    """Return a DrissionPage ChromiumPage, or None when unavailable."""
    options = build_chromium_options(profile_name, headless=headless)
    if options is None:
        return None

    try:
        from DrissionPage import ChromiumPage

        return ChromiumPage(options)
    except Exception as exc:
        logger.warning("Failed to start browser crawler: %s", exc)
        return None
