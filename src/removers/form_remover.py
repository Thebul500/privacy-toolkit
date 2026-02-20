"""Playwright-based form automation for data broker opt-outs."""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

from src.config import BrowserConfig, DATA_DIR
from src.db import Database
from src.models import Broker, Profile


class FormRemover:
    def __init__(self, browser_config: BrowserConfig, db: Database):
        self.config = browser_config
        self.db = db
        self.screenshots_dir = DATA_DIR / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def submit_opt_out(
        self,
        broker: Broker,
        profile: Profile,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict:
        method = broker.form_method
        if not method:
            return {"success": False, "error": "No form opt-out method for this broker"}

        if not method.steps:
            return {"success": False, "error": f"No automation steps defined for {broker.name}"}

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed, cannot submit form opt-out for broker=%s", broker.slug)
            return {"success": False, "error": "Playwright not installed. Run: pip install playwright && playwright install chromium"}

        result = {
            "broker": broker.slug,
            "method": "form",
            "url": method.url,
        }

        if dry_run:
            result["dry_run"] = True
            dry_run_steps = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = await context.new_page()
                page.set_default_timeout(self.config.timeout)

                for i, step in enumerate(method.steps):
                    if dry_run:
                        step_desc = self._describe_step(step, profile, broker)
                        logger.info("DRY RUN step %d/%d: %s", i + 1, len(method.steps), step_desc)
                        dry_run_steps.append(step_desc)
                        # Only navigate so we can screenshot the page state
                        if step.action == "goto":
                            await page.goto(step.url or broker.url, wait_until="networkidle")
                        elif step.action == "wait":
                            await page.wait_for_timeout(step.duration or 2000)
                        # Take screenshot of current page state if enabled
                        if self.config.screenshot_on_submit:
                            screenshot_path = self.screenshots_dir / f"{broker.slug}_dryrun_step{i + 1}.png"
                            await page.screenshot(path=str(screenshot_path), full_page=True)
                    else:
                        logger.info("Executing step %d/%d (%s) for broker=%s", i + 1, len(method.steps), step.action, broker.slug)
                        await self._execute_step(page, step, profile, broker)

                # Take final screenshot
                if self.config.screenshot_on_submit:
                    screenshot_path = self.screenshots_dir / f"{broker.slug}_final.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    result["screenshot"] = str(screenshot_path)

                await browser.close()

            if dry_run:
                result["success"] = True
                result["steps"] = dry_run_steps
            else:
                # Track in database
                removal_id = self.db.create_removal(
                    profile=profile.name,
                    broker_slug=broker.slug,
                    broker_name=broker.name,
                    method="form",
                    recheck_days=broker.verification.expected_days,
                    rescan_days=broker.reappearance_days,
                )
                self.db.update_removal_status(
                    removal_id, "submitted",
                    screenshot_path=result.get("screenshot", ""),
                )
                self.db.log("form_submitted", profile.name, {
                    "broker": broker.slug, "url": method.url,
                })

                result["success"] = True
                result["removal_id"] = removal_id

        except Exception as e:
            logger.error("Form submission failed for broker=%s url=%s: %s", broker.slug, method.url, e)
            result["success"] = False
            result["error"] = str(e)
            if not dry_run:
                self.db.log("form_failed", profile.name, {
                    "broker": broker.slug, "error": str(e),
                }, success=False)

        return result

    def _describe_step(self, step, profile: Profile, broker: Broker) -> str:
        """Return a human-readable description of a step for dry-run output."""
        if step.action == "goto":
            url = step.url or broker.url
            return f"DRY RUN: Would navigate to [{url}]"
        elif step.action == "fill":
            value = self._resolve_field(step.field, step.value, profile)
            return f"DRY RUN: Would fill [{step.selector}] with [{value}]"
        elif step.action == "select":
            value = self._resolve_field(step.field, step.value, profile)
            return f"DRY RUN: Would select [{value}] in [{step.selector}]"
        elif step.action == "click":
            return f"DRY RUN: Would click [{step.selector}]"
        elif step.action == "wait":
            duration = step.duration or 2000
            return f"DRY RUN: Would wait [{duration}ms]"
        elif step.action == "screenshot":
            name = step.name or "step"
            return f"DRY RUN: Would take screenshot [{name}]"
        else:
            return f"DRY RUN: Would execute unknown action [{step.action}]"

    async def _execute_step(self, page, step, profile: Profile, broker: Broker) -> None:
        if step.action == "goto":
            await page.goto(step.url or broker.url, wait_until="networkidle")

        elif step.action == "fill":
            value = self._resolve_field(step.field, step.value, profile)
            if value:
                await page.fill(step.selector, value)

        elif step.action == "select":
            value = self._resolve_field(step.field, step.value, profile)
            if value:
                await page.select_option(step.selector, value)

        elif step.action == "click":
            await page.click(step.selector)

        elif step.action == "wait":
            await page.wait_for_timeout(step.duration or 2000)

        elif step.action == "screenshot":
            path = self.screenshots_dir / f"{broker.slug}_{step.name or 'step'}.png"
            await page.screenshot(path=str(path))

    def _resolve_field(self, field: str, static_value: str, profile: Profile) -> str:
        if static_value:
            return static_value
        field_map = {
            "email": profile.primary_email,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "full_name": profile.full_name or f"{profile.first_name} {profile.last_name}".strip(),
            "phone": profile.primary_phone,
            "address": profile.primary_address,
            "city": profile.addresses[0].city if profile.addresses else "",
            "state": profile.addresses[0].state if profile.addresses else "",
            "state_abbr": profile.addresses[0].state_abbr if profile.addresses else "",
            "zip": profile.addresses[0].zip_code if profile.addresses else "",
        }
        return field_map.get(field, "")
