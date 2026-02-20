"""Tests for src.removers.form_remover — FormRemover dry-run and step descriptions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import BrowserConfig
from src.models import (
    Broker,
    FormStep,
    OptOutMethod,
    OptOutMethodType,
    Priority,
    Verification,
)
from src.removers.form_remover import FormRemover


@pytest.fixture
def browser_config():
    """Return a BrowserConfig with screenshots disabled for fast tests."""
    return BrowserConfig(
        headless=True,
        timeout=5000,
        screenshot_on_submit=False,
        rate_limit_delay=0.0,
    )


@pytest.fixture
def form_broker():
    """Return a Broker with form opt-out steps for testing."""
    return Broker(
        slug="testformbroker",
        name="Test Form Broker",
        url="https://testformbroker.example.com",
        category="people_search",
        priority=Priority.HIGH,
        data_types=["name", "email"],
        methods=[
            OptOutMethod(
                type=OptOutMethodType.FORM,
                url="https://testformbroker.example.com/optout",
                steps=[
                    FormStep(action="goto", url="https://testformbroker.example.com/optout"),
                    FormStep(action="fill", selector="#email", field="email"),
                    FormStep(action="fill", selector="#name", value="Static Name"),
                    FormStep(action="click", selector="#submit-btn"),
                    FormStep(action="wait", duration=2000),
                ],
            ),
        ],
        verification=Verification(type="manual", expected_days=14),
        reappearance_days=90,
    )


@pytest.fixture
def test_profile(sample_profile):
    """Alias for the shared sample_profile fixture from conftest."""
    return sample_profile


def _build_mock_playwright():
    """Build a fully mocked async Playwright context manager.

    Returns (mock_playwright_cm, mock_page) so tests can inspect
    whether page.fill/page.click/etc. were called.
    """
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.fill = AsyncMock()
    mock_page.click = AsyncMock()
    mock_page.select_option = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.screenshot = AsyncMock()
    mock_page.set_default_timeout = MagicMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = AsyncMock()
    mock_pw.chromium = mock_chromium

    # async context manager: async with async_playwright() as p: ...
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

    mock_async_playwright = MagicMock(return_value=mock_pw_cm)

    return mock_async_playwright, mock_page


class TestDryRunReturnsSteps:
    """Test that dry_run=True returns a steps list and dry_run flag."""

    def test_dry_run_returns_steps(self, browser_config, form_broker, test_profile, tmp_db):
        """Mock Playwright, call submit_opt_out with dry_run=True,
        verify result has 'steps' list and 'dry_run' flag."""
        mock_async_pw, mock_page = _build_mock_playwright()
        remover = FormRemover(browser_config, tmp_db)

        with patch("playwright.async_api.async_playwright", mock_async_pw):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    remover.submit_opt_out(form_broker, test_profile, dry_run=True)
                )
            finally:
                loop.close()

        assert result["success"] is True
        assert result["dry_run"] is True
        assert "steps" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) == 5  # goto, fill, fill, click, wait


class TestDryRunDoesNotSubmit:
    """Test that dry_run=True does NOT call fill or click on the page."""

    def test_dry_run_does_not_submit(self, browser_config, form_broker, test_profile, tmp_db):
        """Verify that click/fill actions are NOT called during dry_run."""
        mock_async_pw, mock_page = _build_mock_playwright()
        remover = FormRemover(browser_config, tmp_db)

        with patch("playwright.async_api.async_playwright", mock_async_pw):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    remover.submit_opt_out(form_broker, test_profile, dry_run=True)
                )
            finally:
                loop.close()

        assert result["success"] is True
        # fill and click should NOT have been called in dry_run
        mock_page.fill.assert_not_called()
        mock_page.click.assert_not_called()
        mock_page.select_option.assert_not_called()


class TestDescribeStep:
    """Test the _describe_step method for various action types."""

    @pytest.fixture
    def remover(self, browser_config, tmp_db):
        return FormRemover(browser_config, tmp_db)

    def test_describe_step_fill(self, remover, form_broker, test_profile):
        """Test _describe_step for fill actions."""
        step = FormStep(action="fill", selector="#email", field="email")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "fill" in desc.lower() or "Would fill" in desc
        assert "#email" in desc
        # Should resolve the email field from profile
        assert test_profile.primary_email in desc

    def test_describe_step_fill_static_value(self, remover, form_broker, test_profile):
        """Test _describe_step for fill with a static value."""
        step = FormStep(action="fill", selector="#name", value="John Doe")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "John Doe" in desc
        assert "#name" in desc

    def test_describe_step_click(self, remover, form_broker, test_profile):
        """Test _describe_step for click actions."""
        step = FormStep(action="click", selector="#submit-btn")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "click" in desc.lower() or "Would click" in desc
        assert "#submit-btn" in desc

    def test_describe_step_goto(self, remover, form_broker, test_profile):
        """Test _describe_step for goto actions."""
        step = FormStep(action="goto", url="https://example.com/optout")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "navigate" in desc.lower() or "goto" in desc.lower()
        assert "https://example.com/optout" in desc

    def test_describe_step_goto_fallback_to_broker_url(self, remover, form_broker, test_profile):
        """Test _describe_step for goto with no url falls back to broker.url."""
        step = FormStep(action="goto")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert form_broker.url in desc

    def test_describe_step_wait(self, remover, form_broker, test_profile):
        """Test _describe_step for wait actions."""
        step = FormStep(action="wait", duration=3000)
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "wait" in desc.lower()
        assert "3000" in desc

    def test_describe_step_select(self, remover, form_broker, test_profile):
        """Test _describe_step for select actions."""
        step = FormStep(action="select", selector="#state", field="state")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "select" in desc.lower()
        assert "#state" in desc

    def test_describe_step_screenshot(self, remover, form_broker, test_profile):
        """Test _describe_step for screenshot actions."""
        step = FormStep(action="screenshot", name="after_submit")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "screenshot" in desc.lower()
        assert "after_submit" in desc

    def test_describe_step_unknown(self, remover, form_broker, test_profile):
        """Test _describe_step for an unknown action type."""
        step = FormStep(action="custom_action")
        desc = remover._describe_step(step, test_profile, form_broker)
        assert "DRY RUN" in desc
        assert "custom_action" in desc


class TestNoFormMethod:
    """Test submit_opt_out when broker has no form method."""

    def test_no_form_method_returns_error(self, browser_config, test_profile, tmp_db):
        """A broker without form method should return error."""
        broker_no_form = Broker(
            slug="noform",
            name="No Form Broker",
            url="https://noform.example.com",
            category="people_search",
            priority=Priority.LOW,
            methods=[],
        )
        remover = FormRemover(browser_config, tmp_db)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                remover.submit_opt_out(broker_no_form, test_profile, dry_run=True)
            )
        finally:
            loop.close()

        assert result["success"] is False
        assert "error" in result
