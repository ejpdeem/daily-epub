import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import config


def _attach_file(msg, file_path):
    with open(file_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        "attachment; filename=" + os.path.basename(file_path),
    )
    msg.attach(part)


def send_digest(epub_path, subject=None):
    if not all([config.SMTP_HOST, config.SMTP_USER, config.SMTP_PASS]):
        raise ValueError("SMTP_HOST, SMTP_USER, and SMTP_PASS must be set")

    msg = MIMEMultipart()
    msg["From"] = config.FROM_EMAIL
    msg["To"] = config.TO_EMAIL
    msg["Subject"] = subject or "Daily Digest — " + os.path.basename(epub_path)

    body = "Your daily digest is attached as an EPUB."
    msg.attach(MIMEText(body, "plain"))

    if epub_path and os.path.exists(epub_path):
        _attach_file(msg, epub_path)

    with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
        server.login(config.SMTP_USER, config.SMTP_PASS)
        server.sendmail(config.FROM_EMAIL, config.TO_EMAIL.split(","), msg.as_string())
