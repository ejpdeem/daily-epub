import json
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from config import config
from models import Article


class ArticleCache:
    def __init__(self, db_path: str = "articles_cache.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    url TEXT PRIMARY KEY,
                    extracted_at TEXT NOT NULL,
                    title TEXT,
                    author TEXT,
                    published TEXT,
                    content_html TEXT,
                    summary TEXT,
                    site_name TEXT,
                    tags TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_extracted_at ON articles(extracted_at)
            """)

    def get(self, url: str) -> Optional[Article]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM articles WHERE url = ?", (url,)
            ).fetchone()

        if not row:
            return None

        extracted_at = datetime.fromisoformat(row["extracted_at"])
        if datetime.now(timezone.utc) - extracted_at > timedelta(hours=24):
            self.delete(url)
            return None

        return Article(
            title=row["title"] or "",
            url=row["url"],
            published=datetime.fromisoformat(row["published"]) if row["published"] else datetime.now(timezone.utc),
            author=row["author"] or "",
            summary=row["summary"] or "",
            content_html=row["content_html"] or "",
            site_name=row["site_name"] or "",
            tags=json.loads(row["tags"]) if row["tags"] else [],
        )

    def set(self, article: Article):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO articles (
                    url, extracted_at, title, author, published,
                    content_html, summary, site_name, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    extracted_at=excluded.extracted_at,
                    title=excluded.title,
                    author=excluded.author,
                    published=excluded.published,
                    content_html=excluded.content_html,
                    summary=excluded.summary,
                    site_name=excluded.site_name,
                    tags=excluded.tags
                """,
                (
                    article.url,
                    datetime.now(timezone.utc).isoformat(),
                    article.title,
                    article.author,
                    article.published.isoformat(),
                    article.content_html,
                    article.summary,
                    article.site_name,
                    json.dumps(article.tags),
                ),
            )

    def delete(self, url: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM articles WHERE url = ?", (url,))

    def clear_old(self, max_age_hours: int = 72):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM articles WHERE extracted_at < ?", (cutoff,))


_cache = None

def get_cache() -> ArticleCache:
    global _cache
    if _cache is None:
        _cache = ArticleCache(config.CACHE_PATH)
    return _cache


class BaseScraper(ABC):
    @abstractmethod
    def fetch_articles(self) -> List[Article]:
        pass


class RssScraper(BaseScraper):
    def __init__(self, feed_url: str, delay_seconds: float = 0.5):
        self.feed_url = feed_url
        self.delay_seconds = delay_seconds

    def fetch_articles(self) -> List[Article]:
        feed = feedparser.parse(self.feed_url)
        site = feed.feed.get("title", "")
        articles = []

        for entry in feed.entries:
            url = entry.get("link", "")
            published = self._parse_date(entry.get("published") or entry.get("updated"))
            summary = entry.get("summary", "")
            title = entry.get("title", "Untitled")

            article = Article(
                title=title,
                url=url,
                published=published,
                author=entry.get("author", ""),
                summary=summary,
                site_name=site,
            )

            if article.is_from_today():
                article = extract_full_article(article, delay=self.delay_seconds)

            articles.append(article)
        return articles

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> datetime:
        if not date_str:
            return datetime.now(timezone.utc)
        try:
            return date_parser.parse(date_str).astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)


class HackerNewsScraper(BaseScraper):
    URL = "https://news.ycombinator.com/"

    def __init__(self, delay_seconds: float = 0.5):
        self.delay_seconds = delay_seconds

    def fetch_articles(self) -> List[Article]:
        resp = requests.get(self.URL, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        today = datetime.now(timezone.utc)

        for item in soup.select(".athing"):
            title_tag = item.select_one(".titleline > a")
            if not title_tag:
                continue

            url = title_tag.get("href", "")
            if url.startswith("item?"):
                url = urljoin(self.URL, url)

            article = Article(
                title=title_tag.get_text(strip=True),
                url=url,
                published=today,
                site_name="Hacker News",
            )
            article = extract_full_article(article, delay=self.delay_seconds)
            articles.append(article)

        return articles


def _fetch_html(url: str, delay: float = 0.5) -> str:
    time.sleep(delay)
    try:
        from curl_cffi import requests as curl_requests
        response = curl_requests.get(url, impersonate="chrome110", timeout=20)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print("curl_cffi failed: " + str(e))

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print("requests failed: " + str(e))

    return ""


def _extract_with_bs4(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "iframe", "embed", "object", "noscript"]):
        tag.decompose()

    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    author = ""
    for meta in soup.find_all("meta"):
        if meta.get("name", "").lower() in ["author", "article:author"]:
            author = meta.get("content", "")
            break

    published = ""
    for meta in soup.find_all("meta"):
        if meta.get("property", "").lower() in ["article:published_time", "og:article:published_time"] or meta.get("name", "").lower() in ["published_time", "date"]:
            published = meta.get("content", "")
            break

    main = soup.find("main") or soup.find("article") or soup.find("div", role="main")
    if not main:
        main = soup.find("body")

    if main:
        for tag in main.find_all(["div", "section"]):
            text = tag.get_text(strip=True)
            if len(text) < 20:
                classes = " ".join(tag.get("class", [])).lower()
                if any(bad in classes for bad in ["ad", "sidebar", "related", "share", "comment", "widget", "newsletter", "subscribe", "promo"]):
                    tag.decompose()

    content_html = ""
    text = ""
    if main:
        text = main.get_text("\n", strip=True)
        content_html = str(main)

    return {
        "title": title,
        "author": author,
        "date": published,
        "text": text,
        "raw_html": content_html,
    }


def extract_full_article(article: Article, delay: float = 0.5) -> Article:
    if not article.url:
        print("No URL for article: " + article.title)
        return article

    cache = get_cache()

    cached = cache.get(article.url)
    if cached and cached.content_html and len(cached.content_html.strip()) > 100:
        print("Cache hit: " + article.url)
        return Article(
            title=cached.title or article.title,
            url=cached.url,
            published=cached.published,
            author=cached.author or article.author,
            summary=cached.summary or article.summary,
            content_html=cached.content_html,
            site_name=cached.site_name or article.site_name,
            tags=cached.tags or article.tags,
        )
    elif cached:
        print("Cache hit but content empty, re-extracting: " + article.url)

    print("Extracting: " + article.url)
    downloaded = _fetch_html(article.url, delay=delay)

    if not downloaded:
        print("Failed to download: " + article.url)
        cache.set(article)
        return article

    try:
        result = _extract_with_bs4(downloaded, article.url)
    except Exception as e:
        print("Extraction failed for " + article.url + ": " + str(e))
        cache.set(article)
        return article

    text = result.get("text", "")
    raw_html = result.get("raw_html", "")

    if raw_html:
        article.content_html = raw_html
    elif text:
        article.content_html = "<p>" + text.replace("\n", "</p><p>") + "</p>"

    article.title = result.get("title") or article.title
    article.author = result.get("author") or article.author

    date_str = result.get("date")
    if date_str:
        try:
            article.published = date_parser.parse(date_str).astimezone(timezone.utc)
        except Exception:
            pass

    print("Extracted " + str(len(article.content_html or "")) + " chars from: " + article.url)

    if article.content_html and len(article.content_html.strip()) > 100:
        cache.set(article)
    else:
        print("Skipping cache for empty article: " + article.url)

    return article


class SiteRegistry:
    def __init__(self):
        self._scrapers = {}

    def register(self, url_or_name: str, scraper: BaseScraper):
        self._scrapers[url_or_name] = scraper

    def get_scraper(self, url: str, delay: float = 0.5) -> BaseScraper:
        if url in self._scrapers:
            scraper = self._scrapers[url]
            if isinstance(scraper, (RssScraper, HackerNewsScraper)):
                scraper.delay_seconds = delay
            return scraper
        return RssScraper(url, delay_seconds=delay)


def build_registry() -> SiteRegistry:
    registry = SiteRegistry()
    registry.register("https://news.ycombinator.com/rss", HackerNewsScraper())
    return registry
