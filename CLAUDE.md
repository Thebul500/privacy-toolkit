# Privacy Toolkit — Developer Guide

## Architecture

FastAPI web app + Click CLI for discovering and removing personal data from 78 data brokers.

```
src/
├── app.py              # FastAPI web app (port 8080), Jinja2 templates, HTMX
│                       # Routes: /, /profiles, /scans, /accounts, /removals, /brokers, /activity
├── cli.py              # Click CLI — scan, remove, track, profile, schedule, report, brokers, accounts, doctor
├── config.py           # YAML config loader + env var support (_resolve_env), broker validation
├── db.py               # SQLite — scans, findings, removal_requests, audit_log tables
├── models.py           # Pydantic models — Profile, Broker, ScanResult, OptOutMethod, FormStep
├── tasks.py            # ThreadPoolExecutor background task manager (2 workers)
├── scheduler.py        # Cron job installer + APScheduler for web app
├── notifications.py    # Signal REST API integration
├── scanners/           # 8 scanners — each extends BaseScanner
│   ├── base.py                 # Abstract base with scan() method
│   ├── hibp_scanner.py         # HaveIBeenPwned breach/paste lookup
│   ├── holehe_scanner.py       # Email service registration check
│   ├── sherlock_scanner.py     # Username search (subprocess)
│   ├── maigret_scanner.py      # Username OSINT (subprocess)
│   ├── phoneinfoga_scanner.py  # Phone OSINT (binary at bin/phoneinfoga)
│   ├── people_search_scanner.py # Data broker search (Playwright headless)
│   └── spiderfoot_scanner.py   # Full OSINT framework (Docker container)
├── removers/           # 3 removal methods
│   ├── email_remover.py        # SMTP + Jinja2 legal templates (CCPA/GDPR), _render_template/_send_email helpers
│   ├── form_remover.py         # Playwright browser form automation + --dry-run support
│   └── manual_remover.py       # Display manual instructions
├── reporting/          # Output formatting
│   ├── terminal.py             # Rich CLI tables
│   ├── json_export.py          # JSON export
│   ├── csv_export.py           # CSV export (stdlib csv module)
│   └── html_export.py          # HTML report export (dark theme, no deps)
└── web/                # Web interface
    ├── templates/              # 10 Jinja2 HTML templates (dark theme)
    │   ├── accounts.html       # Account discovery page
    │   └── accounts_results.html # HTMX results fragment
    └── static/style.css
```

## Key Patterns

- **Config**: YAML at `config/config.yaml`, loaded into dataclasses in `config.py`
- **Env vars**: Secrets support `${ENV_VAR}` syntax or auto-fallback (SMTP_PASSWORD, HIBP_API_KEY, etc.)
- **Database**: SQLite via raw SQL in `db.py`, parameterized queries
- **Profiles**: YAML files in `config/profiles/<name>.yaml`
- **Brokers**: YAML files in `brokers/<slug>.yaml` — 78 total, validated on load
- **Guides**: YAML files in `guides/<service>.yaml` — 40 service deletion guides
- **Templates**: Jinja2 email templates in `templates/` (CCPA, GDPR, follow-up)
- **Background tasks**: `TaskManager` in `tasks.py` uses ThreadPoolExecutor
- **Web**: FastAPI + Jinja2 + HTMX for live updates, no JS framework
- **Logging**: `logging.getLogger(__name__)` in every module
- **Progress**: Rich Progress bars on all CLI scan/accounts commands

## Running

```bash
# CLI
./privacy-toolkit --help
./privacy-toolkit doctor                    # Check dependencies
./privacy-toolkit scan full -p <profile>    # Full scan with progress bar
./privacy-toolkit accounts find-by-email <email>
./privacy-toolkit remove email-request -p <profile>
./privacy-toolkit report -f csv -t findings -o report.csv

# Web (local)
.venv/bin/python -m src

# Docker
docker-compose up -d  # port 8384 -> 8080
```

## Testing

```bash
cd /home/ghost/Documents/privacy-toolkit
.venv/bin/pytest tests/ -v
```

94 tests across 7 files: test_db, test_config, test_models, test_scanners, test_notifications, test_reporting.

## CI/CD

GitHub Actions at `.github/workflows/ci.yml`:
- pytest + ruff lint on push/PR
- Broker YAML validation (78 files)
- Guide YAML validation (40 files)

## Conventions

- Use `logging` module (not print) — `logger = logging.getLogger(__name__)`
- Scanners extend `BaseScanner` and implement `scan()` returning `list[ScanResult]`
- All database queries use parameterized SQL (never f-strings)
- Broker YAML schema: slug, name, url, category, priority, data_types, opt_out.methods[], verification, reappearance
- Config secrets should use environment variable fallbacks
- Type hints on all new/modified functions
- Tests in `tests/` using pytest, mock external APIs
- Rich Progress bars for CLI scan/accounts commands
- HTML templates escaped via `html.escape()` to prevent XSS
