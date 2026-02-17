# Privacy Toolkit — Improvement Backlog

## Priority 1: Critical (reliability & correctness)

- [ ] **Add logging across all modules** — replace silent `except: pass` with proper logging in scanners, removers, config loader, notifications, db
- [ ] **Add error handling with context** — log which broker/scanner/site failed and why, not just swallow exceptions
- [ ] **Fix CLI crash bugs** — `scan_people` address format assumption, `scan_full` missing address bounds check (Line 287), empty profile fields
- [ ] **Input validation** — validate emails, phones, usernames before passing to scanners; reject empty/malformed input in CLI and web form
- [ ] **Add retry logic to scanners** — Sherlock/Maigret timeout silently; add configurable retry with backoff for transient failures

## Priority 2: High (security & testing)

- [ ] **Create test suite** — `tests/` directory with pytest; unit tests for db, config, models, scanners (mocked), removers (mocked), CLI commands
- [ ] **Environment variable support for secrets** — SMTP password, HIBP API key, Signal config should support `${ENV_VAR}` syntax or env var fallback
- [ ] **Sanitize profile data** — validate/escape profile fields before use in email templates and form automation
- [ ] **Add request timeouts everywhere** — HIBP API, Signal API, SMTP connections, Playwright operations all need explicit timeouts

## Priority 3: Medium (features & UX)

- [ ] **Add CSV/PDF export** — extend reporting module beyond JSON and terminal tables
- [ ] **Add `--dry-run` to form remover** — preview what Playwright would do without submitting
- [ ] **Broker YAML schema validation** — validate broker files on load, report specific errors (missing fields, bad types)
- [ ] **Add scan progress reporting** — CLI progress bars (Rich), web SSE/WebSocket for live scanner status
- [ ] **Rate limiting for people-search scanner** — configurable delay between Playwright site checks to avoid IP blocks
- [ ] **Add `privacy-toolkit doctor` command** — check all dependencies (Playwright, PhoneInfoga, SpiderFoot, SMTP, Signal) and report status

## Priority 4: Low (polish & maintenance)

- [ ] **Add type hints to all functions** — ~15+ functions missing return types
- [ ] **Refactor long functions** — `send_removal_request` (109 lines), `scan_full` (62 lines), `_build_url` (57 lines)
- [ ] **Move hardcoded values to config** — HIBP rate limit, Playwright user-agent, SpiderFoot port/image, PhoneInfoga binary path
- [ ] **Remove dead code** — unused imports in holehe_scanner, inline `__import__` in email_remover, unused STATE_ABBREVS reverse lookup
- [ ] **Add CI/CD** — GitHub Actions workflow for pytest + linting on push
