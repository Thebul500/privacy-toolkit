"""Email-based CCPA/GDPR removal request sender."""

from __future__ import annotations
import html
import re
import smtplib
import time
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.config import TEMPLATES_DIR, SmtpConfig
from src.db import Database
from src.models import Broker, Profile


def _html_to_plain(html_body: str) -> str:
    """Convert HTML email body to plain text fallback."""
    text = html_body
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class EmailRemover:
    def __init__(self, smtp_config: SmtpConfig, db: Database):
        self.smtp = smtp_config
        self.db = db
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    def send_removal_request(
        self,
        broker: Broker,
        profile: Profile,
        dry_run: bool = False,
    ) -> dict:
        method = broker.email_method
        if not method:
            return {"success": False, "error": "No email opt-out method for this broker"}

        request_id = str(uuid.uuid4())[:8]
        template_name = f"{method.template}.j2"

        try:
            template = self.env.get_template(template_name)
        except Exception:
            template = self.env.get_template("ccpa_deletion_request.j2")

        html_body = template.render(
            full_name=profile.full_name or f"{profile.first_name} {profile.last_name}".strip(),
            first_name=profile.first_name,
            last_name=profile.last_name,
            email=profile.primary_email,
            phone=profile.primary_phone,
            address=profile.primary_address,
            request_id=request_id,
            broker_name=broker.name,
            date=time.strftime("%B %d, %Y"),
        )
        plain_body = _html_to_plain(html_body)

        subject = method.subject or f"Formal Data Deletion Request Pursuant to CCPA/GDPR \u2014 Ref: {request_id}"
        from_addr = self.smtp.from_email or self.smtp.username
        from_name = profile.full_name or f"{profile.first_name} {profile.last_name}".strip()
        message_id = f"<{request_id}@privacy-toolkit>"

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_addr}>"
        msg["To"] = method.address
        msg["Subject"] = subject
        msg["Reply-To"] = profile.primary_email or from_addr
        msg["Message-ID"] = message_id
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        result = {
            "broker": broker.slug,
            "to": method.address,
            "subject": subject,
            "message_id": message_id,
            "request_id": request_id,
            "body_preview": plain_body[:200] + "..." if len(plain_body) > 200 else plain_body,
        }

        if dry_run:
            result["dry_run"] = True
            result["success"] = True
            result["full_body"] = plain_body
            return result

        if not self.smtp.username or not self.smtp.password:
            return {"success": False, "error": "SMTP not configured. Edit config/config.yaml"}

        try:
            with smtplib.SMTP(self.smtp.host, self.smtp.port) as server:
                if self.smtp.use_tls:
                    server.starttls()
                server.login(self.smtp.username, self.smtp.password)
                server.send_message(msg)

            # Track in database
            removal_id = self.db.create_removal(
                profile=profile.name,
                broker_slug=broker.slug,
                broker_name=broker.name,
                method="email",
                recheck_days=broker.verification.expected_days,
                rescan_days=broker.reappearance_days,
            )
            self.db.update_removal_status(
                removal_id, "submitted",
                email_message_id=message_id,
            )
            self.db.log("email_sent", profile.name, {
                "broker": broker.slug, "to": method.address, "message_id": message_id,
            })

            result["success"] = True
            result["removal_id"] = removal_id

            # Rate limit
            time.sleep(self.smtp.delay_seconds)

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            self.db.log("email_failed", profile.name, {
                "broker": broker.slug, "error": str(e),
            }, success=False)

        return result
