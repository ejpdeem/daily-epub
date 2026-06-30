import uuid
from datetime import datetime

from ebooklib import epub

from models import Article


def build_epub(articles, output_path="daily_digest.epub"):
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title("Daily Digest — " + datetime.now().strftime("%Y-%m-%d"))
    book.set_language("en")
    book.add_author("Daily Digest Bot")

    style = """
    body { font-family: Georgia, serif; line-height: 1.6; margin: 1em; color: #222; }
    h1 { font-size: 1.6em; border-bottom: 2px solid #333; padding-bottom: 0.3em; }
    h2 { font-size: 1.3em; margin-top: 1.5em; color: #111; page-break-before: always; }
    h3 { font-size: 1.1em; color: #444; }
    a { color: #0645ad; word-break: break-all; }
    .meta { color: #666; font-size: 0.9em; margin-bottom: 1.2em; }
    .site { text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.75em; color: #888; }
    img { max-width: 100%; height: auto; }
    figure { margin: 1em 0; }
    """
    nav_css = epub.EpubItem(
        uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style
    )
    book.add_item(nav_css)

    chapters = []

    intro = epub.EpubHtml(title="Introduction", file_name="intro.xhtml")
    intro.content = (
        "<h1>Daily Digest</h1>"
        "<p class='meta'>" + datetime.now().strftime("%A, %B %d, %Y") + "</p>"
        "<p>" + str(len(articles)) + " articles</p>"
    )
    book.add_item(intro)
    chapters.append(intro)

    for i, article in enumerate(articles, 1):
        chapter = epub.EpubHtml(
            title=article.title[:80],
            file_name="article_" + str(i) + ".xhtml",
            lang="en",
        )

        content = article.content_html or article.summary or ""
        if not content.strip():
            content = "<p><a href='" + article.url + "'>Read original article</a></p>"

        tags = ", ".join(article.tags) if article.tags else ""

        meta_parts = []
        if article.author:
            meta_parts.append("<p>By " + article.author + "</p>")
        meta_parts.append("<p>" + article.published.strftime("%Y-%m-%d %H:%M UTC") + "</p>")
        meta_parts.append("<p><a href='" + article.url + "'>Original source</a></p>")
        if tags:
            meta_parts.append("<p>Tags: " + tags + "</p>")

        chapter.content = (
            "<div class='site'>" + (article.site_name or "Unknown Source") + "</div>"
            "<h2>" + article.title + "</h2>"
            "<div class='meta'>" + "".join(meta_parts) + "</div>"
            + content
        )
        chapter.add_item(nav_css)
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = chapters[1:]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    epub.write_epub(output_path, book, {})
    return output_path
