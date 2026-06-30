from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class Article:
    title: str
    url: str
    published: datetime
    author: str = ""
    summary: str = ""
    content_html: str = ""
    site_name: str = ""
    tags: list = field(default_factory=list)

    def is_from_today(self) -> bool:
        now = datetime.now(timezone.utc)
        return now - self.published <= timedelta(hours=24)
