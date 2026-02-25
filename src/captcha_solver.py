"""CAPTCHA detection and solver provider abstraction.

Supports 2captcha and capsolver APIs. When provider is "none", all methods are no-ops.
"""

from __future__ import annotations

import asyncio
import logging
import time

import requests

from src.config import CaptchaConfig

logger = logging.getLogger(__name__)


class CaptchaSolver:
    def __init__(self, config: CaptchaConfig):
        self.config = config

    async def detect_and_solve(self, page) -> bool:
        """Inspect page for reCAPTCHA/hCaptcha, solve if found. Returns True if solved."""
        if self.config.provider == "none" or not self.config.api_key:
            return False

        # Try reCAPTCHA v2
        site_key = await self._find_recaptcha(page)
        if site_key:
            token = await self.solve_recaptcha_v2(page, site_key)
            if token:
                await page.evaluate(
                    f'document.querySelector("#g-recaptcha-response").value = "{token}"'
                )
                return True

        # Try hCaptcha
        site_key = await self._find_hcaptcha(page)
        if site_key:
            token = await self.solve_hcaptcha(page, site_key)
            if token:
                await page.evaluate(
                    f'document.querySelector("[name=h-captcha-response]").value = "{token}"'
                )
                return True

        return False

    async def _find_recaptcha(self, page) -> str | None:
        """Extract reCAPTCHA v2 site key from page."""
        try:
            el = await page.query_selector(".g-recaptcha[data-sitekey]")
            if el:
                return await el.get_attribute("data-sitekey")
            # Check for iframe
            frame = await page.query_selector('iframe[src*="recaptcha"]')
            if frame:
                src = await frame.get_attribute("src") or ""
                if "k=" in src:
                    return src.split("k=")[1].split("&")[0]
        except Exception:
            pass
        return None

    async def _find_hcaptcha(self, page) -> str | None:
        """Extract hCaptcha site key from page."""
        try:
            el = await page.query_selector(".h-captcha[data-sitekey]")
            if el:
                return await el.get_attribute("data-sitekey")
        except Exception:
            pass
        return None

    async def solve_recaptcha_v2(self, page, site_key: str) -> str | None:
        """Solve reCAPTCHA v2 using configured provider."""
        page_url = page.url
        if self.config.provider == "2captcha":
            return await self._solve_2captcha("NormalRecaptcha", site_key, page_url)
        elif self.config.provider == "capsolver":
            return await self._solve_capsolver("ReCaptchaV2TaskProxyLess", site_key, page_url)
        return None

    async def solve_hcaptcha(self, page, site_key: str) -> str | None:
        """Solve hCaptcha using configured provider."""
        page_url = page.url
        if self.config.provider == "2captcha":
            return await self._solve_2captcha("HCaptcha", site_key, page_url)
        elif self.config.provider == "capsolver":
            return await self._solve_capsolver("HCaptchaTaskProxyLess", site_key, page_url)
        return None

    async def _solve_2captcha(self, method: str, site_key: str, page_url: str) -> str | None:
        """Submit to 2captcha and poll for result."""
        try:
            # Submit task
            resp = requests.post(
                "https://2captcha.com/in.php",
                data={
                    "key": self.config.api_key,
                    "method": "userrecaptcha" if "Recaptcha" in method else "hcaptcha",
                    "googlekey" if "Recaptcha" in method else "sitekey": site_key,
                    "pageurl": page_url,
                    "json": 1,
                },
                timeout=30,
            )
            data = resp.json()
            if data.get("status") != 1:
                logger.error("2captcha submit failed: %s", data)
                return None
            task_id = data["request"]

            # Poll for result
            deadline = time.time() + self.config.timeout
            while time.time() < deadline:
                await asyncio.sleep(5)
                resp = requests.get(
                    "https://2captcha.com/res.php",
                    params={"key": self.config.api_key, "action": "get", "id": task_id, "json": 1},
                    timeout=10,
                )
                data = resp.json()
                if data.get("status") == 1:
                    return data["request"]
                if "CAPCHA_NOT_READY" not in data.get("request", ""):
                    logger.error("2captcha solve failed: %s", data)
                    return None
        except Exception as e:
            logger.error("2captcha error: %s", e)
        return None

    async def _solve_capsolver(self, task_type: str, site_key: str, page_url: str) -> str | None:
        """Submit to capsolver and poll for result."""
        try:
            resp = requests.post(
                "https://api.capsolver.com/createTask",
                json={
                    "clientKey": self.config.api_key,
                    "task": {
                        "type": task_type,
                        "websiteURL": page_url,
                        "websiteKey": site_key,
                    },
                },
                timeout=30,
            )
            data = resp.json()
            if data.get("errorId", 1) != 0:
                logger.error("capsolver submit failed: %s", data)
                return None
            task_id = data["taskId"]

            deadline = time.time() + self.config.timeout
            while time.time() < deadline:
                await asyncio.sleep(5)
                resp = requests.post(
                    "https://api.capsolver.com/getTaskResult",
                    json={"clientKey": self.config.api_key, "taskId": task_id},
                    timeout=10,
                )
                data = resp.json()
                if data.get("status") == "ready":
                    return data.get("solution", {}).get("gRecaptchaResponse") or data.get("solution", {}).get("token")
                if data.get("status") != "processing":
                    logger.error("capsolver solve failed: %s", data)
                    return None
        except Exception as e:
            logger.error("capsolver error: %s", e)
        return None
