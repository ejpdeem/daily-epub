import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SITE_FEEDS = [u.strip() for u in os.getenv("SITE_FEEDS", "").split(",") if u.strip()]
    DEFAULT_DELAY = float(os.getenv("DEFAULT_DELAY", "0.5"))
    CACHE_PATH = os.getenv("CACHE_PATH", "articles_cache.db")

    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASS = os.getenv("SMTP_PASS")
    FROM_EMAIL = os.getenv("FROM_EMAIL", os.getenv("SMTP_USER", ""))
    TO_EMAIL = os.getenv("TO_EMAIL", os.getenv("FROM_EMAIL", os.getenv("SMTP_USER", "")))


config = Config()
