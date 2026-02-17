# Privacy Toolkit — Improvement Backlog

## Priority 1: Critical (reliability & correctness)

- [x] **Add logging across all modules** — replaced silent exceptions with proper logging in all 10 modules
- [x] **Add error handling with context** — all exceptions now log broker/scanner/site context
- [x] **Fix CLI crash bugs** — address bounds check, format validation, empty profile guards
- [x] **Input validation** — email/phone/username validation in CLI and web form
- [x] **Add retry logic to scanners** — HIBP has retry on 429; Sherlock/Maigret have timeouts

## Priority 2: High (security & testing)

- [x] **Create test suite** — 94 tests across 7 test files (db, config, models, scanners, notifications, reporting)
- [x] **Environment variable support for secrets** — `${ENV_VAR}` syntax + auto-fallback for SMTP, HIBP, Signal
- [x] **Sanitize profile data** — HTML-escaped in templates, validated in CLI
- [x] **Add request timeouts everywhere** — HIBP 30s, SMTP 30s, Signal 10s, Playwright 30s, subprocesses 120-600s

## Priority 3: Medium (features & UX)

- [x] **Add CSV/HTML export** — `report -f csv/html -t findings/removals`
- [x] **Add `--dry-run` to form remover** — previews Playwright steps without submitting
- [x] **Broker YAML schema validation** — `brokers validate` CLI command + validation on load
- [x] **Add scan progress reporting** — Rich progress bars/spinners on all CLI commands
- [x] **Rate limiting for people-search scanner** — configurable delay (default 2s) between site checks
- [x] **Add `privacy-toolkit doctor` command** — checks all 12 dependencies and reports status
- [x] **Accounts discovery workflow** — `accounts find-by-email/phone/username` + `exposure-report`
- [x] **Web UI accounts page** — HTMX-powered search with results table and risk assessment
- [x] **Service deletion guides** — 40 YAML guides for common services (social, email, shopping, etc.)

## Priority 4: Low (polish & maintenance)

- [x] **Add type hints to all functions** — return types added to tasks.py, scheduler.py; rest already had them
- [x] **Refactor long functions** — extracted _render_template/_send_email, URL builders, _build_url dispatcher
- [x] **Move hardcoded values to config** — rate_limit_delay added to BrowserConfig
- [x] **Remove dead code** — replaced inline `__import__("datetime")`, verified holehe/STATE_ABBREVS are used
- [x] **Add CI/CD** — GitHub Actions: pytest + ruff lint + broker/guide YAML validation

## All items complete!
