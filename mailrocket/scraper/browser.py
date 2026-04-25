"""Selenium driver bootstrap + LinkedIn auth flow.

Auth strategy (in priority order):
1. Persistent Chrome profile (`paths.chrome_profile`). Once you sign in there
   once, the session persists across runs — no cookies.pkl, no re-login.
2. Cookie pickle (`paths.cookies`). Legacy fallback, populated automatically
   on first successful credentials login.
3. Credentials login (`secrets.linkedin_*`). Tries multiple selector variants
   for the username/password fields.
4. Manual login fallback. If headless is off and auto-login can't find the
   form (LinkedIn UI changed, served authwall, etc.), we hand control to you
   for `scraper.manual_login_timeout_seconds` and watch the URL.

On any failure we dump page HTML + a screenshot to `paths.debug_dir`.
"""
from __future__ import annotations

import logging
import pickle
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Iterable

from selenium import webdriver
from selenium.common.exceptions import (
    InvalidCookieDomainException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from mailrocket.settings import settings

logger = logging.getLogger(__name__)

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"

# Multiple selector variants for the login form. LinkedIn ships the standalone
# `/login` page (id=username/id=password) plus an embedded homepage form
# (name=session_key/name=session_password) and occasionally A/B tests new IDs.
_USERNAME_SELECTORS: tuple[tuple[str, str], ...] = (
    (By.ID, "username"),
    (By.NAME, "session_key"),
    (By.CSS_SELECTOR, "input[autocomplete='username']"),
    (By.CSS_SELECTOR, "input[type='email'][name]"),
)
_PASSWORD_SELECTORS: tuple[tuple[str, str], ...] = (
    (By.ID, "password"),
    (By.NAME, "session_password"),
    (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
    (By.CSS_SELECTOR, "input[type='password'][name]"),
)
_SUBMIT_SELECTORS: tuple[tuple[str, str], ...] = (
    (By.CSS_SELECTOR, "button[data-litms-control-urn='login-submit']"),
    (By.CSS_SELECTOR, "button[aria-label*='Sign in']"),
    (By.XPATH, "//button[@type='submit']"),
)


def setup_driver(headless: bool | None = None):
    """Initialize and configure Chrome WebDriver."""
    is_headless = settings.scraper.headless if headless is None else headless
    try:
        options = webdriver.ChromeOptions()
        if is_headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        profile_dir = settings.paths.chrome_profile
        if profile_dir:
            profile_dir.mkdir(parents=True, exist_ok=True)
            options.add_argument(f"--user-data-dir={profile_dir}")
            logger.info("Using persistent Chrome profile at %s", profile_dir)

        driver = webdriver.Chrome(options=options)
        driver.maximize_window()
        return driver
    except WebDriverException:
        logger.exception("WebDriver initialization failed")
        raise


_LOGGED_IN_URL_PATHS = (
    "/feed",
    "/in/",
    "/jobs/",
    "/messaging",
    "/mynetwork",
    "/notifications",
    "/sales/",
    "/learning",
    "/recruiter",
)
_LOGGED_OUT_URL_FRAGMENTS = (
    "/login",
    "/uas/login",
    "/checkpoint/challenge",
    "/authwall",
)
_LOGGED_IN_SELECTORS = (
    "nav.global-nav",
    "header.global-nav",
    ".global-nav__me",
    ".scaffold-finite-scroll__content",
    "[data-control-name='identity_welcome_message']",
    "input[placeholder*='Search']",
)


def _safe_current_url(driver) -> str:
    try:
        return driver.current_url or ""
    except Exception:
        return ""


def _on_logged_out_page(url: str) -> bool:
    if not url:
        return False
    return any(fragment in url for fragment in _LOGGED_OUT_URL_FRAGMENTS)


def _on_logged_in_url(url: str) -> bool:
    if not url:
        return False
    return any(path in url for path in _LOGGED_IN_URL_PATHS)


def _has_logged_in_dom(driver) -> bool:
    try:
        return any(
            driver.find_elements(By.CSS_SELECTOR, sel) for sel in _LOGGED_IN_SELECTORS
        )
    except Exception:
        return False


def is_logged_in(driver, timeout: int = 15) -> bool:
    """Return True if the current page belongs to a logged-in LinkedIn session.

    Polls for up to `timeout` seconds. URL is the primary signal because
    LinkedIn's CSS class names are BEM-mangled and rotate frequently; DOM
    selectors are a fallback for the rare logged-in URL we don't list.
    """
    deadline = time.time() + timeout
    while True:
        url = _safe_current_url(driver)
        if _on_logged_out_page(url):
            return False
        if _on_logged_in_url(url):
            return True
        if _has_logged_in_dom(driver):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.5)


def _find_first_present(
    driver,
    candidates: Iterable[tuple[str, str]],
    timeout: int = 20,
):
    """Poll until one of the (by, value) candidates appears, or raise TimeoutException."""
    deadline = time.time() + timeout
    last_seen: list[tuple[str, str]] = list(candidates)
    while True:
        for by, value in last_seen:
            try:
                els = driver.find_elements(by, value)
            except WebDriverException:
                els = []
            if els:
                return els[0]
        if time.time() >= deadline:
            raise TimeoutException(
                f"None of these selectors became present within {timeout}s: {last_seen}"
            )
        time.sleep(0.5)


def dump_debug(driver, label: str) -> Path | None:
    """Save current page HTML + screenshot + meta under `paths.debug_dir`.

    Public helper — call from anywhere we want a postmortem snapshot. Returns
    the stem path the artifacts were written to, or None on failure.
    """
    debug_dir = settings.paths.debug_dir
    if not debug_dir:
        return None
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = debug_dir / f"{ts}-{label}"
        try:
            html = driver.page_source
            (stem.with_suffix(".html")).write_text(html, encoding="utf-8")
        except Exception as e:
            logger.debug("Could not save HTML dump: %s", e)
        try:
            driver.save_screenshot(str(stem.with_suffix(".png")))
        except Exception as e:
            logger.debug("Could not save screenshot: %s", e)
        try:
            url = _safe_current_url(driver)
            (stem.with_suffix(".meta.txt")).write_text(
                f"url={url}\ntitle={driver.title!r}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        logger.info("Saved debug dump to %s.{html,png,meta.txt}", stem)
        return stem
    except Exception as e:
        logger.warning("Failed to write debug dump: %s", e)
        return None


_dump_debug = dump_debug  # backward-compat alias for any external imports


def _wait_for_manual_login(driver, cookies_path: Path, timeout: int) -> None:
    """Block until the user signs in manually in the visible browser, or time out."""
    logger.warning(
        "==> Auto-login could not complete. Please sign in manually in the open "
        "Chrome window. Waiting up to %ds for the URL to indicate success...",
        timeout,
    )
    deadline = time.time() + timeout
    last_logged_url = None
    while time.time() < deadline:
        url = _safe_current_url(driver)
        if url != last_logged_url:
            logger.info("Current URL while waiting: %s", url)
            last_logged_url = url
        if _on_logged_in_url(url) or _has_logged_in_dom(driver):
            cookies_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with cookies_path.open("wb") as f:
                    pickle.dump(driver.get_cookies(), f)
                logger.info("Manual login detected; cookies saved to %s", cookies_path)
            except Exception as e:
                logger.warning("Could not save cookies after manual login: %s", e)
            return
        time.sleep(2)
    dump_debug(driver, "manual-login-timeout")
    raise RuntimeError(
        f"Manual login timed out after {timeout}s. Current URL: {_safe_current_url(driver)!r}. "
        "Bump `scraper.manual_login_timeout_seconds` in config or finish signing in faster."
    )


def perform_credentials_login(driver, username: str, password: str) -> bool:
    """Try to fill the LinkedIn login form. Returns True if we got past submit.

    Does NOT raise if the form fields aren't found — returns False so the caller
    can decide whether to fall back to manual login.
    """
    driver.get(LINKEDIN_LOGIN_URL)
    try:
        username_field = _find_first_present(driver, _USERNAME_SELECTORS, timeout=20)
    except TimeoutException:
        logger.warning(
            "Login form not detected at %s (URL=%s, title=%r). LinkedIn may have "
            "served an authwall, captcha, or A/B'd the form selectors.",
            LINKEDIN_LOGIN_URL,
            _safe_current_url(driver),
            driver.title,
        )
        dump_debug(driver, "login-form-missing")
        return False

    try:
        password_field = _find_first_present(driver, _PASSWORD_SELECTORS, timeout=5)
    except TimeoutException:
        logger.warning("Username field found but password field missing.")
        dump_debug(driver, "password-field-missing")
        return False

    username_field.clear()
    username_field.send_keys(username)
    password_field.clear()
    password_field.send_keys(password)

    pre_submit_url = driver.current_url
    try:
        submit_btn = _find_first_present(driver, _SUBMIT_SELECTORS, timeout=5)
        submit_btn.click()
    except TimeoutException:
        logger.warning("Submit button not found; trying password ENTER as fallback.")
        password_field.send_keys(Keys.RETURN)

    try:
        WebDriverWait(driver, 30).until(
            lambda d: d.current_url != pre_submit_url and "/login" not in d.current_url
        )
    except TimeoutException:
        logger.warning(
            "Login form did not navigate within 30s. Current URL still: %s",
            _safe_current_url(driver),
        )
    return True


def login_to_linkedin(driver, username: str, password: str, cookies_path: Path | None = None) -> bool:
    """Auth strategy: profile session > cookies > credentials > manual fallback."""
    cookies_path = cookies_path or settings.paths.cookies

    driver.get(LINKEDIN_FEED_URL)
    if is_logged_in(driver, timeout=10):
        logger.info("Already signed in via persistent Chrome profile (url=%s)", _safe_current_url(driver))
        return True

    try:
        driver.get(LINKEDIN_LOGIN_URL)
        if cookies_path.exists():
            try:
                with cookies_path.open("rb") as f:
                    for cookie in pickle.load(f):
                        try:
                            driver.add_cookie(cookie)
                        except InvalidCookieDomainException:
                            pass
                logger.info("Cookies loaded from %s", cookies_path)
            except Exception as e:
                logger.warning("Failed to load cookies: %s", e)
        else:
            logger.info("No cookies file at %s; will log in with credentials", cookies_path)
    except Exception as e:
        logger.warning("Initial cookie-load step failed: %s", e)

    driver.get(LINKEDIN_FEED_URL)
    time.sleep(2)
    if is_logged_in(driver, timeout=5):
        logger.info("Signed in via cookies (url=%s)", _safe_current_url(driver))
        return True

    have_creds = bool(username and password)
    headless = settings.scraper.headless

    if have_creds:
        logger.info("Session expired or no valid cookies; logging in with credentials")
        form_filled = perform_credentials_login(driver, username, password)

        if handle_2fa(driver):
            if headless:
                dump_debug(driver, "2fa-headless")
                raise RuntimeError(
                    "LinkedIn is asking for 2FA. Run with `MAILROCKET_HEADLESS=0 make scrape`, "
                    "complete the verification in the browser, then retry."
                )
            _wait_for_manual_login(driver, cookies_path, settings.scraper.manual_login_timeout_seconds)
            return True
        if handle_captcha(driver):
            if headless:
                dump_debug(driver, "captcha-headless")
                raise RuntimeError(
                    "LinkedIn served a CAPTCHA. Run with `MAILROCKET_HEADLESS=0 make scrape`, "
                    "solve it once, and the saved cookies will keep subsequent runs unblocked."
                )
            _wait_for_manual_login(driver, cookies_path, settings.scraper.manual_login_timeout_seconds)
            return True

        if is_logged_in(driver, timeout=30):
            cookies_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with cookies_path.open("wb") as f:
                    pickle.dump(driver.get_cookies(), f)
                logger.info("New cookies saved to %s", cookies_path)
            except Exception as e:
                logger.warning("Could not save cookies after login: %s", e)
            return True

        logger.warning(
            "Credentials login did not result in a logged-in URL (current=%s). "
            "form_filled=%s",
            _safe_current_url(driver),
            form_filled,
        )

    if not headless:
        dump_debug(driver, "pre-manual-login")
        _wait_for_manual_login(driver, cookies_path, settings.scraper.manual_login_timeout_seconds)
        return True

    dump_debug(driver, "credentials-login-failed")
    raise RuntimeError(
        f"Credentials login failed. Browser is at url={_safe_current_url(driver)!r} "
        f"title={driver.title!r}. Set `headless: false` in config (or "
        f"`MAILROCKET_HEADLESS=0 make scrape`) to sign in by hand once; the persistent "
        f"Chrome profile at {settings.paths.chrome_profile} will keep the session afterward."
    )


def handle_2fa(driver) -> bool:
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "input__phone_verification_pin"))
        )
        logger.warning("2FA authentication required")
        return True
    except (TimeoutException, NoSuchElementException):
        return False


def handle_captcha(driver) -> bool:
    try:
        driver.find_element(By.ID, "captcha-internal")
        logger.warning("CAPTCHA challenge detected")
        return True
    except NoSuchElementException:
        return False


def check_login_errors(driver) -> bool:
    try:
        error = driver.find_element(By.XPATH, "//div[contains(@class, 'alert-error')]")
        if error:
            logger.error("Login failed: %s", error.text)
            return True
    except NoSuchElementException:
        return False
    return False


def dismiss_popups(driver) -> None:
    try:
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Later')]"))
        ).click()
        logger.info("Dismissed popup")
    except TimeoutException:
        pass


_SEARCH_RESULTS_SELECTORS: tuple[tuple[str, str], ...] = (
    # New (server-driven) DOM, post-2026 LinkedIn rewrite. Class names are
    # BEM-hashed and rotate, so we lean on stable role/data-* attributes.
    (By.CSS_SELECTOR, "div[role='main'][data-sdui-screen*='SearchResultsContent']"),
    (By.CSS_SELECTOR, "div[role='main'] [role='listitem']"),
    # Older DOM fallbacks (kept in case LinkedIn A/B tests bring them back).
    (By.CSS_SELECTOR, "div.feed-shared-update-v2"),
    (By.CSS_SELECTOR, "li.artdeco-card.mb2"),
    (By.CSS_SELECTOR, "div.search-results-container"),
    # Empty-results indicator.
    (By.XPATH, "//*[contains(text(), 'No results found')]"),
)

# LinkedIn's date-posted URL filter only supports these three values. Anything
# longer than ~4 weeks needs to be filtered post-hoc.
_VALID_DATE_POSTED = ("past-24h", "past-week", "past-month")


def perform_search(
    driver,
    query: str,
    sort_by_latest: bool = False,
    date_posted: str | None = None,
) -> None:
    """Navigate directly to the LinkedIn posts-search URL for `query`.

    This bypasses the global search-box widget, which is brittle (LinkedIn
    rewrites its `aria-label` and class names regularly). We hit the canonical
    posts-search URL and wait for ANY known results-container to appear.

    `date_posted` may be one of "past-24h", "past-week", "past-month".
    """
    encoded = urllib.parse.quote(query)
    url = (
        f"https://www.linkedin.com/search/results/content/?keywords={encoded}"
        f"&origin=GLOBAL_SEARCH_HEADER"
    )
    if sort_by_latest:
        url += "&sortBy=%22date_posted%22"
    if date_posted in _VALID_DATE_POSTED:
        url += f"&datePosted=%22{date_posted}%22"
    elif date_posted:
        logger.warning("Ignoring unsupported date_posted=%r (allowed: %s)", date_posted, _VALID_DATE_POSTED)

    logger.info("Navigating to search URL: %s", url)
    driver.get(url)

    try:
        _find_first_present(driver, _SEARCH_RESULTS_SELECTORS, timeout=20)
    except TimeoutException:
        logger.warning(
            "Search results did not render within 20s. URL=%s title=%r",
            _safe_current_url(driver),
            driver.title,
        )
        dump_debug(driver, f"search-results-missing-{_safe_filename(query)}")
        raise

    time.sleep(1)


def _safe_filename(s: str, max_len: int = 60) -> str:
    """Make a string safe to embed in a filename."""
    out = "".join(c if c.isalnum() or c in "-_" else "-" for c in s)
    return out[:max_len].strip("-") or "query"


def initialize_and_login(username: str, password: str, headless: bool | None = None):
    """Spin up a driver and complete login, raising on auth failures.

    `username`/`password` are optional now: if the persistent profile already
    holds a LinkedIn session, we skip credentials. If headless is False and
    no creds are provided, the user is prompted to sign in manually.
    """
    driver = setup_driver(headless=headless)
    logger.info(
        "Browser initialized (headless=%s)",
        settings.scraper.headless if headless is None else headless,
    )

    try:
        login_to_linkedin(driver, username, password)
        time.sleep(2)

        if check_login_errors(driver):
            raise RuntimeError("Login failed - invalid credentials detected")
        if handle_2fa(driver):
            raise RuntimeError("2FA authentication required - please authenticate manually")
        if handle_captcha(driver):
            logger.warning("CAPTCHA challenge detected, sleeping briefly for manual intervention")
            time.sleep(15)

        dismiss_popups(driver)

        if settings.scraper.dump_after_login:
            dump_debug(driver, "post-login-feed")

        return driver
    except Exception:
        driver.quit()
        raise
