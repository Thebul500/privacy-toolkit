"""People-search site scanner - check if personal data appears on data broker sites."""

from __future__ import annotations
import asyncio
import re
from datetime import datetime
from typing import Optional

from src.models import ScanResult
from src.scanners.base import BaseScanner

# Each broker entry: (name, search_url_template, result_indicator_selector, listing_url_pattern)
PEOPLE_SEARCH_SITES = [
    {
        "name": "FastPeopleSearch",
        "slug": "fastpeoplesearch",
        "base_url": "https://www.fastpeoplesearch.com",
        "search_by_name": "/name/{first}-{last}_{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": "/email/{email}",
        "search_by_address": "/address/{street}_{city}-{state}-{zip}",
        "result_selector": "a.btn-primary[href*='/address/'], .card-block .detail-box-name",
        "no_result_text": "did not return any results",
    },
    {
        "name": "TruePeopleSearch",
        "slug": "truepeoplesearch",
        "base_url": "https://www.truepeoplesearch.com",
        "search_by_name": "/results?name={first}+{last}&citystatezip={state}",
        "search_by_phone": "/results?phoneno={phone}",
        "search_by_email": None,
        "search_by_address": "/results?streetaddress={street}&citystatezip={city}+{state}+{zip}",
        "result_selector": ".card-summary .h4, .card-summary a[href*='/find/person/']",
        "no_result_text": "No results found",
    },
    {
        "name": "Whitepages",
        "slug": "whitepages",
        "base_url": "https://www.whitepages.com",
        "search_by_name": "/name/{first}-{last}/{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": None,
        "search_by_address": "/address/{street}/{city}-{state}-{zip}",
        "result_selector": "a[href*='/person/'], .serp-results .person-name",
        "no_result_text": "We couldn't find",
    },
    {
        "name": "Spokeo",
        "slug": "spokeo",
        "base_url": "https://www.spokeo.com",
        "search_by_name": "/{first}-{last}?loaded=1&q={first}+{last}+{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": "/email-search/search?q={email}",
        "search_by_address": "/address-search/search?q={street}+{city}+{state}+{zip}",
        "result_selector": "a[data-link*='search-result'], .result-item .result-name",
        "no_result_text": "We could not find results",
    },
    # --- Additional people-search sites ---
    {
        "name": "ThatsThem",
        "slug": "thatsthem",
        "base_url": "https://thatsthem.com",
        "search_by_name": "/name/{first}-{last}/{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": "/email/{email}",
        "search_by_address": "/address/{street}/{city}/{state}/{zip}",
        "result_selector": ".ThatsThem-people-record, .record-name a",
        "no_result_text": "did not match any records",
    },
    {
        "name": "Nuwber",
        "slug": "nuwber",
        "base_url": "https://nuwber.com",
        "search_by_name": "/search?name={first}+{last}&where={state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": "/search?name={email}",
        "search_by_address": "/search?address={street}+{city}+{state}+{zip}",
        "result_selector": ".person-card, a[href*='/person/']",
        "no_result_text": "No results found",
    },
    {
        "name": "BeenVerified",
        "slug": "beenverified",
        "base_url": "https://www.beenverified.com",
        "search_by_name": "/app/search?fn={first}&ln={last}&state={state}",
        "search_by_phone": "/app/search/phone?phone={phone}",
        "search_by_email": "/app/search/email?email={email}",
        "search_by_address": "/app/search/address?street={street}&city={city}&state={state}&zip={zip}",
        "result_selector": ".search-results-list .card, a[href*='/people/']",
        "no_result_text": "No results found",
    },
    {
        "name": "Radaris",
        "slug": "radaris",
        "base_url": "https://radaris.com",
        "search_by_name": "/p/{first}-{last}/",
        "search_by_phone": "/p/{phone}/",
        "search_by_email": None,
        "search_by_address": None,
        "result_selector": ".card-block a[href*='/p/'], .person-info",
        "no_result_text": "No results found",
    },
    {
        "name": "PeopleFinders",
        "slug": "peoplefinders",
        "base_url": "https://www.peoplefinders.com",
        "search_by_name": "/people/{first}-{last}/{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": None,
        "search_by_address": "/address/{street}/{city}-{state}-{zip}",
        "result_selector": "a[href*='/people/'], .results-list .result-item",
        "no_result_text": "No results found",
    },
    {
        "name": "USPhoneBook",
        "slug": "usphonebook",
        "base_url": "https://www.usphonebook.com",
        "search_by_name": "/{first}-{last}/{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": None,
        "search_by_address": None,
        "result_selector": ".result-list a[href*='/person/'], .fla-result-name",
        "no_result_text": "No results found",
    },
    {
        "name": "CyberBackgroundChecks",
        "slug": "cyberbackgroundchecks",
        "base_url": "https://www.cyberbackgroundchecks.com",
        "search_by_name": "/people/{first}-{last}/{state}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": "/address/{street}/{city}-{state}-{zip}",
        "result_selector": "a[href*='/detail/'], .record-item",
        "no_result_text": "No results found",
    },
    {
        "name": "SearchPeopleFree",
        "slug": "searchpeoplefree",
        "base_url": "https://www.searchpeoplefree.com",
        "search_by_name": "/find/{first}-{last}/{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": "/email/{email}",
        "search_by_address": "/address/{street}/{city}-{state}-{zip}",
        "result_selector": "a[href*='/find/'], .result-name",
        "no_result_text": "No results found",
    },
    {
        "name": "Intelius",
        "slug": "intelius",
        "base_url": "https://www.intelius.com",
        "search_by_name": "/people-search/{first}-{last}/{state}",
        "search_by_phone": "/reverse-phone/{phone}",
        "search_by_email": None,
        "search_by_address": "/reverse-address/{street}/{city}-{state}-{zip}",
        "result_selector": "a[href*='/people/'], .record-list .record-card",
        "no_result_text": "No results found",
    },
    {
        "name": "FamilyTreeNow",
        "slug": "familytreenow",
        "base_url": "https://www.familytreenow.com",
        "search_by_name": "/search/people/?first={first}&last={last}&state={state}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": "/search/people/?street={street}&city={city}&state={state}&zip={zip}",
        "result_selector": ".person-item a, .search-result a[href*='/records/']",
        "no_result_text": "No results found",
    },
    {
        "name": "AdvancedBackgroundChecks",
        "slug": "advancedbackgroundchecks",
        "base_url": "https://www.advancedbackgroundchecks.com",
        "search_by_name": "/name/{first}-{last}/{state}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": "/address/{street}/{city}-{state}-{zip}",
        "result_selector": "a[href*='/name/'], .record-primary",
        "no_result_text": "No results found",
    },
    {
        "name": "SmartBackgroundChecks",
        "slug": "smartbackgroundchecks",
        "base_url": "https://www.smartbackgroundchecks.com",
        "search_by_name": "/people/{first}-{last}/{state}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": "/address/{street}/{city}-{state}",
        "result_selector": "a[href*='/detail/'], .record-item",
        "no_result_text": "No results found",
    },
    {
        "name": "Veripages",
        "slug": "veripages",
        "base_url": "https://veripages.com",
        "search_by_name": "/people/{first}-{last}/{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": None,
        "search_by_address": None,
        "result_selector": "a[href*='/profile/'], .search-result-item",
        "no_result_text": "No results found",
    },
    {
        "name": "ClustrMaps",
        "slug": "clustrmaps",
        "base_url": "https://clustrmaps.com",
        "search_by_name": "/persons/{first}-{last}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": None,
        "result_selector": "a[href*='/person/'], .panel-body .media",
        "no_result_text": "No results found",
    },
    {
        "name": "PublicDataUSA",
        "slug": "publicdatausa",
        "base_url": "https://www.publicdatausa.com",
        "search_by_name": "/{first}-{last}/{state}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": None,
        "result_selector": "a[href*='/detail/'], .person-result",
        "no_result_text": "No results found",
    },
    {
        "name": "VoterRecords",
        "slug": "voterrecords",
        "base_url": "https://voterrecords.com",
        "search_by_name": "/voters/{first}-{last}/{state}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": None,
        "result_selector": "a[href*='/voter/'], .voter-record",
        "no_result_text": "No results found",
    },
    {
        "name": "CocoFinder",
        "slug": "cocofinder",
        "base_url": "https://www.cocofinder.com",
        "search_by_name": "/person/?first={first}&last={last}&state={state}",
        "search_by_phone": "/phone/?phone={phone}",
        "search_by_email": "/email/?email={email}",
        "search_by_address": "/address/?street={street}&city={city}&state={state}&zip={zip}",
        "result_selector": "a[href*='/person/'], .search-result-card",
        "no_result_text": "No results found",
    },
    {
        "name": "IDCrawl",
        "slug": "idcrawl",
        "base_url": "https://www.idcrawl.com",
        "search_by_name": "/{first}-{last}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": None,
        "result_selector": ".result a, .profile-card",
        "no_result_text": "No results found",
    },
    {
        "name": "USA People Search",
        "slug": "usa-people-search",
        "base_url": "https://www.usa-people-search.com",
        "search_by_name": "/name/{first}-{last}/{state}",
        "search_by_phone": "/phone/{phone}",
        "search_by_email": None,
        "search_by_address": "/address/{street}/{city}-{state}",
        "result_selector": "a[href*='/person/'], .card .name",
        "no_result_text": "No results found",
    },
    {
        "name": "NeighborWho",
        "slug": "neighbor-who",
        "base_url": "https://www.neighborwho.com",
        "search_by_name": "/people/{first}-{last}/{state}",
        "search_by_phone": None,
        "search_by_email": None,
        "search_by_address": "/address/{street}/{city}-{state}-{zip}",
        "result_selector": "a[href*='/people/'], .result-item",
        "no_result_text": "No results found",
    },
]

# US state name to abbreviation mapping
STATE_ABBREVS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def _normalize_phone(phone: str) -> str:
    """Strip phone to digits only."""
    digits = re.sub(r"[^\d]", "", phone)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    return digits


def _normalize_state(state: str) -> str:
    """Convert state to abbreviation if needed."""
    if len(state) == 2:
        return state.upper()
    return STATE_ABBREVS.get(state.lower(), state.upper()[:2])


class PeopleSearchScanner(BaseScanner):
    name = "people_search"

    def is_available(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def scan(self, query: str, query_type: str = "name") -> list[ScanResult]:
        """Synchronous wrapper for async scan.

        query_type can be: name, phone, email, address
        For name queries, format as "first last state" (e.g. "John Doe IL")
        For address queries, format as "street|city|state|zip" (e.g. "123 Main St|Chicago|IL|60601")
        """
        try:
            return asyncio.get_event_loop().run_until_complete(
                self._async_scan(query, query_type)
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_scan(query, query_type))
            finally:
                loop.close()

    async def _async_scan(self, query: str, query_type: str) -> list[ScanResult]:
        from playwright.async_api import async_playwright

        results = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )

            for site in PEOPLE_SEARCH_SITES:
                try:
                    result = await self._check_site(context, site, query, query_type)
                    if result:
                        results.append(result)
                except Exception:
                    continue

            await browser.close()

        return results

    async def _check_site(
        self,
        context,
        site: dict,
        query: str,
        query_type: str,
    ) -> Optional[ScanResult]:
        """Check a single people-search site for a listing."""
        url = self._build_url(site, query, query_type)
        if not url:
            return None

        page = await context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if not response or response.status >= 400:
                return None

            # Wait for content to render
            await page.wait_for_timeout(2000)

            page_text = await page.inner_text("body")

            # Check for "no results" indicators
            no_result = site.get("no_result_text", "")
            if no_result and no_result.lower() in page_text.lower():
                return None

            # Check for positive result indicators
            found = False
            listing_url = url
            try:
                elements = await page.query_selector_all(site["result_selector"])
                if elements:
                    found = True
                    # Try to get a direct listing link
                    first = elements[0]
                    href = await first.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            listing_url = site["base_url"] + href
                        elif href.startswith("http"):
                            listing_url = href
            except Exception:
                pass

            if not found:
                return None

            return ScanResult(
                scanner=self.name,
                site_name=site["name"],
                site_url=listing_url,
                data_type=f"listing_{query_type}",
                details={
                    "query": query,
                    "query_type": query_type,
                    "search_url": url,
                    "broker_slug": site["slug"],
                },
                confidence="high",
                found_at=datetime.now(),
            )
        finally:
            await page.close()

    def _build_url(self, site: dict, query: str, query_type: str) -> Optional[str]:
        """Build the search URL for a given site and query type."""
        base = site["base_url"]

        if query_type == "name":
            template = site.get("search_by_name")
            if not template:
                return None
            parts = query.strip().split()
            if len(parts) < 2:
                return None
            first = parts[0].lower()
            last = parts[1].lower()
            state = _normalize_state(parts[2]) if len(parts) > 2 else ""
            path = template.format(first=first, last=last, state=state)
            return base + path

        elif query_type == "phone":
            template = site.get("search_by_phone")
            if not template:
                return None
            phone = _normalize_phone(query)
            path = template.format(phone=phone)
            return base + path

        elif query_type == "email":
            template = site.get("search_by_email")
            if not template:
                return None
            path = template.format(email=query)
            return base + path

        elif query_type == "address":
            template = site.get("search_by_address")
            if not template:
                return None
            parts = query.split("|")
            if len(parts) < 4:
                return None
            street = parts[0].strip().replace(" ", "-")
            city = parts[1].strip()
            state = _normalize_state(parts[2].strip())
            zip_code = parts[3].strip()
            # Some templates use URL-encoded spaces (+), others use dashes
            street_plus = parts[0].strip().replace(" ", "+")
            street_slash = parts[0].strip().replace(" ", "-")
            path = template.format(
                street=street_slash, city=city, state=state, zip=zip_code,
            )
            # Re-format with + for query-string style URLs
            if "?" in template:
                street_encoded = parts[0].strip().replace(" ", "+")
                path = template.format(
                    street=street_encoded, city=city, state=state, zip=zip_code,
                )
            return base + path

        return None
