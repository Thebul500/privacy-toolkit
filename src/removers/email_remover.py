"""Email-based CCPA/GDPR removal request sender."""

from __future__ import annotations
import datetime as dt
import email as email_lib
import html
import imaplib
import logging
import re
import smtplib
import time
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

from jinja2 import FileSystemLoader, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from src.config import TEMPLATES_DIR, SmtpConfig
from src.db import Database
from src.models import Broker, Profile

# SMTP error codes indicating permanent recipient failure
PERMANENT_FAILURE_CODES = {550, 551, 552, 553, 554}


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
        self.env = SandboxedEnvironment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(default=True, default_for_string=True),
        )

    def _discover_listing_url(self, profile: Profile, broker_slug: str) -> list[str]:
        """Try to find profile listing URL on the broker's site.

        Checks DB first; if no URLs found there and a scanner config
        exists for this broker, runs a targeted single-site scan and
        persists the results.
        """
        from src.scanners.people_search_scanner import has_scanner_config, scan_single

        existing = self.db.get_findings_for_broker(profile.name, broker_slug)
        urls = [f["site_url"] for f in existing if f.get("site_url")]
        if urls:
            return urls

        if not has_scanner_config(broker_slug):
            return []

        # Run targeted scan for this single broker
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Already in an async context — can't use run_until_complete
                logger.debug("Skipping live scan for %s (already in async loop)", broker_slug)
                return []

            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                findings = new_loop.run_until_complete(scan_single(profile, broker_slug))
            finally:
                new_loop.close()

            # Persist findings for future use
            if findings:
                scan_id = self.db.create_scan(profile.name, "people_search", "verify", broker_slug)
                for f in findings:
                    self.db.add_finding(
                        scan_id, profile.name, f.scanner, f.site_name,
                        f.site_url, f.data_type, f.details, f.confidence,
                    )
                self.db.complete_scan(scan_id, len(findings))
                return [f.site_url for f in findings if f.site_url]

        except Exception as e:
            logger.warning("URL discovery failed for broker=%s: %s", broker_slug, e)

        return []

    def _gather_evidence(self, broker: Broker, profile: Profile) -> dict:
        """Look up scan findings for this broker to include in the email."""
        # Try to discover listing URLs if none exist in DB
        discovered_urls = self._discover_listing_url(profile, broker.slug)

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

        # Add any discovered URLs not already in the list
        for url in discovered_urls:
            if url not in listing_urls:
                listing_urls.append(url)

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
            "region": profile.region,
            "jurisdiction": profile.jurisdiction,
            "applicable_laws": profile.applicable_laws,
        }
        context.update(extra_vars)
        return template.render(**context)

    def _send_email(self, to_addr: str, subject: str, html_body: str,
                    from_addr: str = "", from_name: str = "",
                    reply_to: str = "", message_id: str = "",
                    extra_headers: dict[str, str] | None = None) -> str:
        """Open an SMTP connection, send the message, and return the message_id.

        Raises ``smtplib.SMTPRecipientsRefused`` if the server immediately
        rejects the recipient address (permanent failure).
        """
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
            refused = server.send_message(msg)

        if refused:
            for addr, (code, _msg) in refused.items():
                logger.warning("SMTP refused recipient %s: %s %s", addr, code, _msg)
                if code in PERMANENT_FAILURE_CODES:
                    raise smtplib.SMTPRecipientsRefused(refused)

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

        subject = method.subject or f"Formal Data Deletion Request Pursuant to Applicable Privacy Laws \u2014 Ref: {request_id}"
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

        except smtplib.SMTPRecipientsRefused as e:
            logger.error("Recipient bounced for broker=%s to=%s: %s", broker.slug, method.address, e)
            result["success"] = False
            result["error"] = f"Address bounced: {method.address}"
            result["bounced"] = True
            self.db.log("email_bounced", profile.name, {
                "broker": broker.slug, "to": method.address, "error": str(e),
            }, success=False)

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

    def check_bounces(self, imap_host: str = "imap.gmail.com") -> list[dict]:
        """Check Gmail IMAP for bounce-back messages and update removal records.

        Connects to IMAP using the same credentials as SMTP, searches for
        delivery failure notifications from mailer-daemon, extracts the
        bounced recipient addresses, and marks matching removal_requests
        as rejected.

        Returns a list of dicts with bounce details.
        """
        if not self.smtp.username or not self.smtp.password:
            logger.warning("SMTP credentials not configured, cannot check bounces")
            return []

        bounces: list[dict] = []

        try:
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(self.smtp.username, self.smtp.password)
            mail.select("INBOX")

            # Search for delivery failure messages
            status, msg_ids = mail.search(
                None,
                '(OR (FROM "mailer-daemon") (FROM "postmaster"))',
            )
            if status != "OK" or not msg_ids[0]:
                mail.logout()
                return []

            for mid in msg_ids[0].split():
                try:
                    status, data = mail.fetch(mid, "(RFC822)")
                    if status != "OK":
                        continue
                    msg = email_lib.message_from_bytes(data[0][1])

                    # Extract bounced address from body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body = payload.decode("utf-8", errors="replace")
                                break
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")

                    # Find the bounced email address in the body
                    addr_match = re.search(
                        r"wasn't delivered to\s+(\S+@\S+)", body
                    )
                    if not addr_match:
                        # Try alternative bounce format
                        addr_match = re.search(
                            r"<(\S+@\S+)>.*(?:rejected|unknown|not found|does not exist)",
                            body,
                            re.IGNORECASE | re.DOTALL,
                        )
                    if not addr_match:
                        continue

                    bounced_addr = addr_match.group(1).strip("<>").lower()
                    bounce_date = msg.get("Date", "")

                    # Extract SMTP error code
                    error_match = re.search(r"(\d{3}\s+\d\.\d\.\d\s+\S.*)", body)
                    error_detail = error_match.group(1).strip() if error_match else "delivery failed"

                    bounces.append({
                        "address": bounced_addr,
                        "date": bounce_date,
                        "error": error_detail,
                    })

                except Exception as e:
                    logger.debug("Failed to parse bounce message %s: %s", mid, e)

            mail.logout()

        except imaplib.IMAP4.error as e:
            logger.error("IMAP connection failed: %s", e)
            return []
        except Exception as e:
            logger.error("Bounce check failed: %s", e)
            return []

        # Deduplicate by address
        seen = set()
        unique_bounces = []
        for b in bounces:
            if b["address"] not in seen:
                seen.add(b["address"])
                unique_bounces.append(b)

        # Cross-reference with removal_requests and mark as rejected
        updated = 0
        removals = self.db.get_removals(status="submitted")
        bounced_addrs = {b["address"] for b in unique_bounces}
        bounce_errors = {b["address"]: b["error"] for b in unique_bounces}

        from src.config import load_all_brokers
        broker_emails: dict[str, str] = {}
        for broker in load_all_brokers():
            method = broker.email_method
            if method:
                broker_emails[broker.slug] = method.address.lower()

        for removal in removals:
            broker_slug = removal.get("broker_slug", "")
            broker_addr = broker_emails.get(broker_slug, "").lower()
            if broker_addr and broker_addr in bounced_addrs:
                try:
                    error = bounce_errors.get(broker_addr, "address bounced")
                    notes = removal.get("notes") or ""
                    bounce_note = f"bounced:{time.strftime('%Y-%m-%d')} {error}"
                    new_notes = f"{notes}; {bounce_note}" if notes else bounce_note
                    self.db.update_removal_status(
                        removal["id"], "rejected", notes=new_notes,
                    )
                    self.db.log("email_bounced", removal.get("profile"), {
                        "broker": broker_slug, "address": broker_addr,
                        "error": error, "removal_id": removal["id"],
                    }, success=False)
                    updated += 1
                except ValueError:
                    # Already transitioned or invalid state
                    pass

        logger.info(
            "Bounce check complete: %d bounced addresses found, %d removals updated",
            len(unique_bounces), updated,
        )
        return unique_bounces

    # Keywords that indicate the broker wants form/website/CAPTCHA action
    _FORM_KEYWORDS = re.compile(
        r"click\s+here|opt[\s-]?out\s+(?:page|form|link|request)|"
        r"visit\s+(?:our|the|this)\s+(?:website|page|link|portal)|"
        r"fill\s+(?:out|in)\s+(?:the|a|our)\s+form|"
        r"captcha|complete\s+(?:the|our|this)\s+(?:form|process|verification)|"
        r"submit\s+(?:a|your|the)\s+(?:request|form)|"
        r"go\s+to\s+(?:our|the|this)\s+(?:website|page|url)|"
        r"use\s+(?:our|the|this)\s+(?:online|web)\s+(?:form|tool|portal)",
        re.IGNORECASE,
    )

    # Keywords that indicate identity verification is required
    _VERIFY_KEYWORDS = re.compile(
        r"proof\s+of\s+identity|verify\s+(?:your|the)\s+identity|"
        r"provide\s+(?:a\s+)?(?:copy\s+of\s+)?(?:your\s+)?(?:photo\s+)?id|"
        r"government[\s-]issued\s+id|driver.s?\s+license|"
        r"identity\s+verification|confirm\s+(?:your\s+)?identity|"
        r"notarized|identification\s+document",
        re.IGNORECASE,
    )

    # Keywords that indicate no records found
    _NO_RECORDS_KEYWORDS = re.compile(
        r"unable\s+to\s+locate|no\s+records?\s+(?:found|matching|located)|"
        r"could\s+not\s+(?:find|locate)|not\s+(?:found|in\s+our)\s+(?:system|database|records)|"
        r"no\s+(?:matching\s+)?(?:data|information|profile|listing)\s+(?:found|located)|"
        r"were\s+unable\s+to\s+(?:find|locate)",
        re.IGNORECASE,
    )

    # Keywords that indicate the request was completed
    _COMPLETED_KEYWORDS = re.compile(
        r"has\s+been\s+(?:completed|processed|fulfilled|removed|deleted)|"
        r"successfully\s+(?:removed|deleted|opted[\s-]?out)|"
        r"your\s+(?:data|information|records?|profile|listing)\s+(?:has|have)\s+been\s+(?:removed|deleted)|"
        r"removal\s+(?:is\s+)?(?:complete|confirmed)|"
        r"opt[\s-]?out\s+(?:is\s+)?(?:complete|confirmed|processed)",
        re.IGNORECASE,
    )

    def _classify_response(self, body: str) -> tuple[str, str]:
        """Classify a broker response into a category and extract key detail.

        Returns (category, detail) where category is one of:
        - needs_form: broker wants you to use a website/form/CAPTCHA
        - needs_verification: broker wants identity proof
        - no_records: broker says they have no data on you
        - completed: broker confirms deletion
        - acknowledged: auto-reply or ticket created, waiting
        """
        # Strip HTML tags for keyword matching
        text = re.sub(r"<[^>]+>", " ", body)
        text = re.sub(r"\s+", " ", text)

        # Check in priority order (most actionable first)
        m = self._VERIFY_KEYWORDS.search(text)
        if m:
            # Extract surrounding context
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            return "needs_verification", text[start:end].strip()

        m = self._FORM_KEYWORDS.search(text)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            # Try to extract URL near the keyword
            url_match = re.search(r"https?://\S+", text[max(0, m.start() - 100):m.end() + 200])
            detail = text[start:end].strip()
            if url_match:
                detail += f" — URL: {url_match.group(0).rstrip('.,)>')}"
            return "needs_form", detail

        m = self._COMPLETED_KEYWORDS.search(text)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            return "completed", text[start:end].strip()

        m = self._NO_RECORDS_KEYWORDS.search(text)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            return "no_records", text[start:end].strip()

        return "acknowledged", ""

    def check_responses(self, imap_host: str = "imap.gmail.com") -> list[dict]:
        """Check Gmail IMAP for broker replies to removal requests.

        Finds emails that reply to privacy-toolkit message IDs, classifies
        them (needs_form, needs_verification, completed, no_records,
        acknowledged), and updates removal_request notes.

        Returns a list of dicts with response details.
        """
        if not self.smtp.username or not self.smtp.password:
            logger.warning("SMTP credentials not configured, cannot check responses")
            return []

        responses: list[dict] = []

        try:
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(self.smtp.username, self.smtp.password)
            mail.select("INBOX")

            # Search for replies referencing privacy-toolkit
            searches = [
                '(HEADER In-Reply-To "privacy-toolkit")',
                '(SUBJECT "deletion request")',
                '(SUBJECT "opt-out")',
            ]

            seen_ids: set[bytes] = set()
            raw_messages = []

            for query in searches:
                status, data = mail.search(None, query)
                if status != "OK" or not data[0]:
                    continue
                for mid in data[0].split():
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                    status2, msg_data = mail.fetch(mid, "(RFC822)")
                    if status2 != "OK":
                        continue
                    raw_messages.append(msg_data[0][1])

            mail.logout()

        except imaplib.IMAP4.error as e:
            logger.error("IMAP connection failed: %s", e)
            return []
        except Exception as e:
            logger.error("Response check failed: %s", e)
            return []

        # Build lookup of our message IDs to removal requests
        removals = self.db.get_removals(status="submitted")
        msgid_to_removal: dict[str, dict] = {}
        for r in removals:
            mid = r.get("email_message_id", "")
            if mid:
                msgid_to_removal[mid] = r

        # Also build broker email → removal lookup
        from src.config import load_all_brokers
        broker_email_to_slug: dict[str, str] = {}
        for broker in load_all_brokers():
            method = broker.email_method
            if method:
                broker_email_to_slug[method.address.lower()] = broker.slug

        slug_to_removal: dict[str, dict] = {}
        for r in removals:
            slug_to_removal.setdefault(r.get("broker_slug", ""), r)

        for raw in raw_messages:
            try:
                msg = email_lib.message_from_bytes(raw)
                from_addr = msg.get("From", "")
                subject = msg.get("Subject", "")
                date = msg.get("Date", "")
                in_reply_to = msg.get("In-Reply-To", "")

                # Skip our own sent messages
                if self.smtp.username and self.smtp.username in from_addr:
                    continue
                # Skip bounce messages (handled by check_bounces)
                from_lower = from_addr.lower()
                if "mailer-daemon" in from_lower or "postmaster" in from_lower:
                    continue

                # Extract body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")
                                break
                        elif ct == "text/html" and not body:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")

                if not body:
                    continue

                # Match to a removal request
                matched_removal = None
                # Try In-Reply-To match first
                if in_reply_to and in_reply_to in msgid_to_removal:
                    matched_removal = msgid_to_removal[in_reply_to]
                else:
                    # Try matching sender domain to broker
                    sender_match = re.search(r"[\w.-]+@[\w.-]+", from_addr)
                    if sender_match:
                        sender_email = sender_match.group(0).lower()
                        # Check sender domain against broker domains
                        sender_domain = sender_email.split("@")[1]
                        for broker_email, slug in broker_email_to_slug.items():
                            broker_domain = broker_email.split("@")[1]
                            # Match if domains share a root (e.g., spokeo.zendesk.com → spokeo)
                            if (broker_domain in sender_domain
                                    or sender_domain in broker_domain
                                    or slug in sender_domain):
                                if slug in slug_to_removal:
                                    matched_removal = slug_to_removal[slug]
                                    break

                category, detail = self._classify_response(body)

                response = {
                    "from": from_addr,
                    "date": date,
                    "subject": subject,
                    "category": category,
                    "detail": detail,
                    "broker": matched_removal.get("broker_name", "Unknown") if matched_removal else "Unknown",
                    "broker_slug": matched_removal.get("broker_slug", "") if matched_removal else "",
                    "removal_id": matched_removal.get("id") if matched_removal else None,
                }
                responses.append(response)

                # Update removal notes if matched
                if matched_removal and category != "acknowledged":
                    try:
                        notes = matched_removal.get("notes") or ""
                        tag = f"response:{category}:{time.strftime('%Y-%m-%d')}"
                        if tag not in notes:
                            new_notes = f"{notes}; {tag}" if notes else tag
                            self.db.update_removal_status(
                                matched_removal["id"], "submitted",
                                notes=new_notes,
                            )
                    except ValueError:
                        pass

            except Exception as e:
                logger.debug("Failed to parse response message: %s", e)

        logger.info("Response check: %d responses found", len(responses))
        return responses
