"""LinkedIn post scraping flow.

Public surface: `scrape_linkedin_feed(...)` — a generator that yields one
post dict at a time, browser-restarted per query.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Generator, List, Optional

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from mailrocket.scraper.browser import dump_debug, initialize_and_login, perform_search
from mailrocket.scraper.query_builder import FixedSizeStore, contains_email, read_queries_from_file
from mailrocket.settings import settings
from mailrocket.storage.posts_repo import check_post_exists

logger = logging.getLogger(__name__)


def parse_timestamp(time_str: str) -> datetime:
    """Convert LinkedIn relative time strings (e.g. '3 hours ago') to datetime."""
    now = datetime.now()
    if not time_str:
        return now

    try:
        time_str = time_str.lower()
        numbers = re.findall(r"\d+", time_str)
        if not numbers:
            return now

        value = int(numbers[0])
        if "minute" in time_str:
            return now - timedelta(minutes=value)
        if "hour" in time_str:
            return now - timedelta(hours=value)
        if "day" in time_str:
            return now - timedelta(days=value)
        if "week" in time_str:
            return now - timedelta(weeks=value)
        if "month" in time_str:
            return now - timedelta(days=value * 30)
        if "year" in time_str:
            return now - timedelta(days=value * 365)
        return now
    except Exception:
        logger.exception("Failed to parse timestamp: %s", time_str)
        return now


def is_recent_post(post_date: datetime, max_weeks: int | None = None) -> bool:
    """Soft date filter retained for callers; new search-results DOM doesn't
    expose post timestamps, so the URL-level `&datePosted=...` filter does the
    real work and we always treat scraped posts as recent here.
    """
    if post_date is None:
        return True
    weeks = max_weeks if max_weeks is not None else settings.scraper.max_post_age_weeks
    cutoff = datetime.now() - timedelta(weeks=weeks)
    return post_date >= cutoff


def date_posted_filter_for_weeks(weeks: int) -> Optional[str]:
    """Map our `max_post_age_weeks` to LinkedIn's URL `datePosted` filter.

    LinkedIn only supports past-24h / past-week / past-month server-side, so
    anything older than ~4 weeks falls back to no filter.
    """
    if weeks <= 0:
        return "past-24h"
    if weeks <= 1:
        return "past-week"
    if weeks <= 4:
        return "past-month"
    return None


_PROFILE_ARIA_RE = re.compile(r"^\s*View\s+(.+?)(?:\u2019|')s\s+profile", re.I)
_HASHTAG_RE = re.compile(r"#(\w+)")


def _strip_tracking(href: str) -> str:
    """Drop ?trackingId=... and other noise from a LinkedIn URL."""
    if not href:
        return href
    return href.split("?", 1)[0]


def _post_link_from_listitem(listitem) -> Optional[str]:
    """Build a stable per-post identifier for DB primary-key use.

    Priority:
        1. /jobs/view/<id> if the post links to a specific job.
        2. /feed/update/urn:li:activity:<id> if a urn appears anywhere.
        3. Synthetic /search/results/content/#post=<componentkey> using the
           opaque componentkey on the listitem (stable per-post per-tenant).
    """
    job = listitem.find("a", href=re.compile(r"/jobs/view/\d+"))
    if job and job.get("href"):
        return _strip_tracking(job["href"])

    urn_match = re.search(r"urn:li:(?:activity|share|ugcPost):[\w\-]+", str(listitem))
    if urn_match:
        return f"https://www.linkedin.com/feed/update/{urn_match.group(0)}"

    ck = listitem.get("componentkey") or ""
    inner = ck
    m = re.search(r"expanded([\w\-]+)FeedType", ck)
    if m:
        inner = m.group(1)
    if inner:
        return f"https://www.linkedin.com/search/results/content/#post={inner}"
    return None


def parse_post_html(html: str) -> Optional[Dict]:
    """Parse a single LinkedIn post (`role='listitem'` HTML blob) into a dict.

    Returns None if essential fields are missing. Tuned for the post-2026
    LinkedIn UI rewrite: class names are BEM-hashed and rotate, so we anchor
    on stable role / data-testid / aria-label attributes only.
    """
    soup = BeautifulSoup(html, "html.parser")

    listitem = soup.find(attrs={"role": "listitem"})
    root = listitem if listitem is not None else soup

    data: Dict = {
        "author_name": None,
        "profile_url": None,
        "post_date": datetime.now(),  # search results no longer expose timestamps
        "post_link": None,
        "post_text": None,
        "hashtags": [],
        "reactions": None,
        "comments": None,
        "query": None,
    }

    try:
        text_box = root.find(attrs={"data-testid": "expandable-text-box"})
        if not text_box:
            return None
        text = text_box.get_text(separator="\n", strip=True)
        if text.endswith("…\nmore") or text.endswith("\u2026 more"):
            text = re.sub(r"(?:\u2026|\.\.\.)\s*\n?\s*more$", "", text).strip()
        data["post_text"] = text.encode("utf-8", errors="replace").decode("utf-8")

        for el in root.find_all(attrs={"aria-label": _PROFILE_ARIA_RE}):
            m = _PROFILE_ARIA_RE.match(el.get("aria-label", ""))
            if m:
                data["author_name"] = m.group(1).strip()
                break

        profile_a = root.find("a", href=re.compile(r"/in/[^/?#]+"))
        if profile_a is not None:
            data["profile_url"] = _strip_tracking(profile_a["href"])

        if listitem is not None:
            data["post_link"] = _post_link_from_listitem(listitem)

        data["hashtags"] = list({f"#{tag}" for tag in _HASHTAG_RE.findall(text)})

        for btn in root.find_all("button"):
            al = btn.get("aria-label") or ""
            if "reaction" in al.lower() and not data["reactions"]:
                data["reactions"] = al.strip()
            elif "comment" in al.lower() and not data["comments"]:
                data["comments"] = al.strip()

    except Exception:
        logger.exception("Parsing error")

    return data


def scrape_linkedin_posts_for_query(
    driver, query: str, max_results: int, sort_by_latest: bool = True
) -> Generator[Dict, None, None]:
    """Walk the search-results feed for `query`, yielding parsed post dicts."""
    total = 0
    recent_posts_store = FixedSizeStore(10)
    date_posted = date_posted_filter_for_weeks(settings.scraper.max_post_age_weeks)

    def get_visible_posts() -> List:
        # Post-2026 DOM uses role-based markup; fall back to legacy artdeco-card.
        new_dom = driver.find_elements(
            By.CSS_SELECTOR, "div[role='main'] [role='listitem']"
        )
        if new_dom:
            return new_dom
        return driver.find_elements(
            By.XPATH, "//li[contains(@class, 'artdeco-card mb2')]"
        )

    def trigger_load_more(posts: List) -> None:
        """Try several strategies to nudge the lazy-column into loading more posts.

        New LinkedIn UI uses a virtualized list (`data-testid='lazy-column'`)
        with an IntersectionObserver sentinel near the bottom. A single
        `window.scrollTo(...)` is unreliable because the actual scroll
        container can be the body OR an inner div with overflow:auto.
        """
        try:
            if posts:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'end', behavior: 'instant'});",
                    posts[-1],
                )
        except Exception:
            pass
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        try:
            driver.execute_script(
                """
                const main = document.querySelector("div[role='main']");
                if (main) { main.scrollTop = main.scrollHeight; }
                const lazy = document.querySelector("[data-testid='lazy-column']");
                if (lazy) { lazy.scrollTop = lazy.scrollHeight; }
                """
            )
        except Exception:
            pass
        try:
            from selenium.webdriver.common.keys import Keys
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.END)
        except Exception:
            pass
        time.sleep(2.5)

    try:
        perform_search(driver, query, sort_by_latest=sort_by_latest, date_posted=date_posted)
        time.sleep(2)

        scroll_attempts = 0
        max_attempts = 8
        previous_count = 0
        dumped_stuck = False

        while scroll_attempts < max_attempts and total < max_results:
            current_posts = get_visible_posts()
            current_count = len(current_posts)
            new_count = current_count - previous_count
            logger.info("Visible posts=%d new=%d", current_count, new_count)

            if new_count > 0:
                new_posts = current_posts[-(new_count + 2):]

                for post in new_posts:
                    if total >= max_results:
                        break
                    try:
                        post_html = post.get_attribute("outerHTML")
                        post_data = parse_post_html(post_html)

                        if not post_data or not post_data.get("post_text"):
                            continue
                        if not contains_email(post_data["post_text"]):
                            continue

                        link = post_data.get("post_link")
                        if link and recent_posts_store.find(link):
                            continue
                        if link:
                            recent_posts_store.insert(link)
                            if check_post_exists(link):
                                logger.info("Already in DB: %s", link)
                                continue

                        post_data["query"] = query
                        logger.info("Yielding post: %s", link)
                        yield post_data
                        total += 1

                    except Exception:
                        logger.exception("Error processing a post; continuing")
                        continue

                previous_count = current_count
                scroll_attempts = 0
            else:
                scroll_attempts += 1
                logger.info("Scroll attempts: %d/%d (current=%d)", scroll_attempts, max_attempts, current_count)

                if scroll_attempts == 3 and not dumped_stuck:
                    dump_debug(driver, f"scroll-stuck-{current_count}-posts")
                    dumped_stuck = True

            trigger_load_more(current_posts)

    except Exception:
        logger.exception("Scraping interrupted for query: %s", query)

    logger.info("Finished query '%s' with %d posts", query, total)


def scrape_linkedin_feed(
    queries_file: Path | str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> Generator[Dict, None, None]:
    """Top-level generator: log in once per query, yield parsed posts as they're found."""
    queries_file = Path(queries_file) if queries_file else settings.paths.queries
    username = username or settings.secrets.linkedin_username
    password = password or settings.secrets.linkedin_password

    queries = read_queries_from_file(queries_file)
    logger.info("Loaded %d search queries from %s", len(queries), queries_file)

    for query, max_results, sort_by_latest in queries:
        driver = None
        try:
            logger.info("Processing query: '%s' - opening fresh browser", query)
            driver = initialize_and_login(username, password)
            for post in scrape_linkedin_posts_for_query(driver, query, max_results, sort_by_latest):
                yield post
        except Exception:
            logger.exception("Failed to process query '%s'; moving on", query)
            continue
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("Browser closed for query '%s'", query)
                except Exception:
                    logger.exception("Error closing browser")
