"""Email-based CCPA/GDPR removal request sender."""

from __future__ import annotations
import datetime as dt
import html
import logging
import re
import smtplib
import time
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

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

    def _gather_evidence(self, broker: Broker, profile: Profile) -> dict:
        """Look up scan findings for this broker to include in the email."""
        findings = self.db.get_findings_for_broker(profile.name, broker.slug)
        listing_urls = []
        data_types_found = set()

        for f in findings:
            if f.get("site_url") and f["site_url"] not in listing_urls:
                listing_urls.append(f["site_url"])
            if f.get("data_type"):
                dtype = f["data_type"].replace("listing_", "")
                data_types_found.add(dtype)
            details = f.get("details", {})
            if isinstance(details, dict) and details.get("query_type"):
                data_types_found.add(details["query_type"])

        # Also include the broker's own declared data types
        for data_type in broker.data_types:
            data_types_found.add(data_type)

        return {
            "listing_urls": listing_urls[:5],  # cap at 5
            "data_types_found": sorted(data_types_found),
            "privacy_policy_url": broker.privacy_policy_url,
        }

    def _render_template(self, broker: Broker, profile: Profile, evidence: dict,
                         template_name: str = "", **extra_vars: str) -> str:
        """Render an email template and return the HTML body."""
        if not template_name:
            method = broker.email_method
            template_name = f"{method.template}.j2" if method else "ccpa_deletion_request.j2"

        try:
            template = self.env.get_template(template_name)
        except Exception as e:
            logger.warning("Template %s not found for broker=%s, falling back to ccpa_deletion_request.j2: %s", template_name, broker.slug, e)
            template = self.env.get_template("ccpa_deletion_request.j2")

        context = {
            "full_name": profile.full_name or f"{profile.first_name} {profile.last_name}".strip(),
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "email": profile.primary_email,
            "phone": profile.primary_phone,
            "address": profile.primary_address,
            "broker_name": broker.name,
            "broker_url": broker.url,
            "date": time.strftime("%B %d, %Y"),
            "listing_urls": evidence["listing_urls"],
            "data_types_found": evidence["data_types_found"],
            "privacy_policy_url": evidence["privacy_policy_url"],
        }
        context.update(extra_vars)
        return template.render(**context)

    def _send_email(self, to_addr: str, subject: str, html_body: str,
                    from_addr: str = "", from_name: str = "",
                    reply_to: str = "", message_id: str = "",
                    extra_headers: dict[str, str] | None = None) -> str:
        """Open an SMTP connection, send the message, and return the message_id."""
        from_addr = from_addr or self.smtp.from_email or self.smtp.username
        reply_to = reply_to or from_addr
        plain_body = _html_to_plain(html_body)

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Reply-To"] = reply_to
        msg["Message-ID"] = message_id
        msg["Disposition-Notification-To"] = reply_to
        if extra_headers:
            for key, value in extra_headers.items():
                msg[key] = value
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(self.smtp.host, self.smtp.port, timeout=30) as server:
            if self.smtp.use_tls:
                server.starttls()
            server.login(self.smtp.username, self.smtp.password)
            server.send_message(msg)

        return message_id

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
        evidence = self._gather_evidence(broker, profile)
        html_body = self._render_template(
            broker, profile, evidence,
            template_name=f"{method.template}.j2",
            request_id=request_id,
        )
        plain_body = _html_to_plain(html_body)

        subject = method.subject or f"Formal Data Deletion Request Pursuant to CCPA/GDPR \u2014 Ref: {request_id}"
        from_addr = self.smtp.from_email or self.smtp.username
        from_name = profile.full_name or f"{profile.first_name} {profile.last_name}".strip()
        reply_to = profile.primary_email or from_addr
        message_id = f"<{request_id}@privacy-toolkit>"

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
            self._send_email(
                to_addr=method.address,
                subject=subject,
                html_body=html_body,
                from_addr=from_addr,
                from_name=from_name,
                reply_to=reply_to,
                message_id=message_id,
            )

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
            logger.error("SMTP send failed for broker=%s to=%s: %s", broker.slug, method.address, e)
            result["success"] = False
            result["error"] = str(e)
            self.db.log("email_failed", profile.name, {
                "broker": broker.slug, "error": str(e),
            }, success=False)

        return result

    def send_follow_up(
        self,
        removal: dict,
        profile: Profile,
        broker: Broker,
    ) -> dict:
        """Send a follow-up email for an overdue removal request."""
        method = broker.email_method
        if not method:
            return {"success": False, "error": "No email opt-out method"}

        original_ref = (removal.get("email_message_id") or "").strip("<>").split("@")[0]
        follow_up_id = str(uuid.uuid4())[:8]

        evidence = self._gather_evidence(broker, profile)

        days_elapsed = 45
        if removal.get("submitted_at"):
            days_elapsed = (
                dt.datetime.now() - dt.datetime.fromisoformat(removal["submitted_at"])
            ).days

        html_body = self._render_template(
            broker, profile, evidence,
            template_name="follow_up_request.j2",
            original_ref=original_ref,
            follow_up_id=follow_up_id,
            original_date=removal.get("submitted_at", "")[:10],
            days_elapsed=str(days_elapsed),
        )

        subject = f"Second Request \u2014 Data Deletion Follow-Up \u2014 Original Ref: {original_ref}"
        from_addr = self.smtp.from_email or self.smtp.username
        from_name = profile.full_name or f"{profile.first_name} {profile.last_name}".strip()
        reply_to = profile.primary_email or from_addr
        message_id = f"<{follow_up_id}@privacy-toolkit>"

        if not self.smtp.username or not self.smtp.password:
            return {"success": False, "error": "SMTP not configured"}

        try:
            self._send_email(
                to_addr=method.address,
                subject=subject,
                html_body=html_body,
                from_addr=from_addr,
                from_name=from_name,
                reply_to=reply_to,
                message_id=message_id,
                extra_headers={
                    "In-Reply-To": removal.get("email_message_id", ""),
                    "References": removal.get("email_message_id", ""),
                },
            )

            # Mark follow-up sent in notes
            existing_notes = removal.get("notes") or ""
            new_notes = f"{existing_notes}; follow_up_sent:{time.strftime('%Y-%m-%d')}" if existing_notes else f"follow_up_sent:{time.strftime('%Y-%m-%d')}"
            self.db.update_removal_status(
                removal["id"], "submitted",
                notes=new_notes,
            )
            self.db.log("follow_up_sent", removal.get("profile"), {
                "broker": broker.slug, "original_ref": original_ref, "follow_up_id": follow_up_id,
            })

            time.sleep(self.smtp.delay_seconds)
            return {"success": True, "follow_up_id": follow_up_id}

        except Exception as e:
            logger.error("Follow-up SMTP send failed for broker=%s: %s", broker.slug, e)
            self.db.log("follow_up_failed", removal.get("profile"), {
                "broker": broker.slug, "error": str(e),
            }, success=False)
            return {"success": False, "error": str(e)}
