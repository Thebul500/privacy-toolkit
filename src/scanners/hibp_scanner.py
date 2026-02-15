"""HaveIBeenPwned scanner - check if email appears in known data breaches."""

from __future__ import annotations
import time
from datetime import datetime

import requests

from src.models import ScanResult
from src.scanners.base import BaseScanner

HIBP_API = "https://haveibeenpwned.com/api/v3"
USER_AGENT = "PrivacyToolkit-PersonalUse"
# HIBP rate limit: 1 request per 1.5 seconds (free tier)
RATE_LIMIT_DELAY = 1.6


class HIBPScanner(BaseScanner):
    name = "hibp"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        if self.api_key:
            self.session.headers["hibp-api-key"] = self.api_key

    def is_available(self) -> bool:
        return True

    def scan(self, query: str, query_type: str = "email") -> list[ScanResult]:
        results = []
        results.extend(self._check_breaches(query))
        time.sleep(RATE_LIMIT_DELAY)
        results.extend(self._check_pastes(query))
        return results

    def _check_breaches(self, email: str) -> list[ScanResult]:
        """Check email against known breaches."""
        url = f"{HIBP_API}/breachedaccount/{requests.utils.quote(email)}"
        params = {"truncateResponse": "false"}

        try:
            resp = self.session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            raise RuntimeError(f"HIBP API request failed: {e}")

        if resp.status_code == 404:
            return []
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2))
            time.sleep(retry_after)
            try:
                resp = self.session.get(url, params=params, timeout=15)
            except requests.RequestException:
                return []
            if resp.status_code != 200:
                return []
        if resp.status_code == 401:
            # API key required for this endpoint - fall back to unverified check
            return self._check_breaches_free(email)
        if resp.status_code != 200:
            return []

        results = []
        for breach in resp.json():
            results.append(ScanResult(
                scanner=self.name,
                site_name=breach.get("Name", "Unknown"),
                site_url=breach.get("Domain", ""),
                data_type="breach",
                details={
                    "email": email,
                    "breach_date": breach.get("BreachDate", ""),
                    "added_date": breach.get("AddedDate", ""),
                    "pwn_count": breach.get("PwnCount", 0),
                    "data_classes": breach.get("DataClasses", []),
                    "is_verified": breach.get("IsVerified", False),
                    "is_sensitive": breach.get("IsSensitive", False),
                    "description": breach.get("Description", ""),
                },
                confidence="high" if breach.get("IsVerified") else "medium",
                found_at=datetime.now(),
            ))
        return results

    def _check_breaches_free(self, email: str) -> list[ScanResult]:
        """Fallback: check all known breaches (no API key needed)."""
        url = f"{HIBP_API}/breaches"
        try:
            resp = self.session.get(url, timeout=15)
        except requests.RequestException:
            return []

        if resp.status_code != 200:
            return []

        # Without API key we can only list all breaches, not check a specific email.
        # Return empty - user needs an API key for per-email checks.
        return []

    def _check_pastes(self, email: str) -> list[ScanResult]:
        """Check if email appears in paste dumps."""
        url = f"{HIBP_API}/pasteaccount/{requests.utils.quote(email)}"

        try:
            resp = self.session.get(url, timeout=15)
        except requests.RequestException:
            return []

        if resp.status_code == 404:
            return []
        if resp.status_code == 401:
            # API key required for paste search
            return []
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2))
            time.sleep(retry_after)
            try:
                resp = self.session.get(url, timeout=15)
            except requests.RequestException:
                return []
            if resp.status_code != 200:
                return []
        if resp.status_code != 200:
            return []

        results = []
        for paste in resp.json():
            source = paste.get("Source", "Unknown Paste")
            paste_id = paste.get("Id", "")
            title = paste.get("Title") or f"{source} paste"
            results.append(ScanResult(
                scanner=self.name,
                site_name=f"{source}: {title}",
                site_url=f"https://pastebin.com/{paste_id}" if source == "Pastebin" else "",
                data_type="paste",
                details={
                    "email": email,
                    "source": source,
                    "paste_id": paste_id,
                    "title": title,
                    "date": paste.get("Date", ""),
                    "email_count": paste.get("EmailCount", 0),
                },
                confidence="high",
                found_at=datetime.now(),
            ))
        return results
