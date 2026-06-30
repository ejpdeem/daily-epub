import sys
from datetime import datetime, timezone

from config import config
from epub_builder import build_epub
from mailer import send_digest
from models import Article
from scrapers import build_registry, get_cache


def fetch_all_today():
    if not config.SITE_FEEDS:
        raise ValueError("No SITE_FEEDS configured")

    registry = build_registry()
    articles = []

    for feed in config.SITE_FEEDS:
        try:
            print("Fetching: " + feed)
            scraper = registry.get_scraper(feed, delay=config.DEFAULT_DELAY)
            for article in scraper.fetch_articles():
                if article.is_from_today():
                    articles.append(article)
        except Exception as e:
            print("Error fetching " + feed + ": " + str(e), file=sys.stderr)

    seen = set()
    unique = []
    for a in articles:
        if a.url not in seen:
            seen.add(a.url)
            unique.append(a)

    unique.sort(key=lambda x: (x.site_name, x.published))
    return unique


def run():
    print("Starting digest at " + str(datetime.now(timezone.utc)))

    get_cache().clear_old(max_age_hours=72)

    articles = fetch_all_today()
    print("Found " + str(len(articles)) + " articles from today")

    if not articles:
        print("No articles today; skipping EPUB generation.")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    base_name = "daily_digest_" + date_str

    epub_path = build_epub(articles, base_name + ".epub")
    print("Built EPUB: " + epub_path)

    send_digest(epub_path)
    print("Email sent.")


if __name__ == "__main__":
    run()
