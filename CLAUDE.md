# Privacy Toolkit — Developer Guide

## Architecture

FastAPI web app + Click CLI for discovering and removing personal data from 78 data brokers.

```
src/
├── app.py              # FastAPI web app (port 8080), Jinja2 templates, HTMX
├── cli.py              # Click CLI — scan, remove, track, profile, schedule, report, brokers
├── config.py           # YAML config loader, dataclasses for each section
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
│   ├── email_remover.py        # SMTP + Jinja2 legal templates (CCPA/GDPR)
│   ├── form_remover.py         # Playwright browser form automation
│   └── manual_remover.py       # Display manual instructions
├── reporting/          # Output formatting
│   ├── terminal.py             # Rich CLI tables
│   └── json_export.py          # JSON export
└── web/                # Web interface
    ├── templates/              # 8 Jinja2 HTML templates (dark theme)
    └── static/style.css
```

## Key Patterns

- **Config**: YAML at `config/config.yaml`, loaded into dataclasses in `config.py`
- **Database**: SQLite via raw SQL in `db.py`, parameterized queries
- **Profiles**: YAML files in `config/profiles/<name>.yaml`
- **Brokers**: YAML files in `brokers/<slug>.yaml` — 78 total
- **Templates**: Jinja2 email templates in `templates/` (CCPA, GDPR, follow-up)
- **Background tasks**: `TaskManager` in `tasks.py` uses ThreadPoolExecutor
- **Web**: FastAPI + Jinja2 + HTMX for live updates, no JS framework

## Running

```bash
# CLI
./privacy-toolkit --help
./privacy-toolkit scan full -p <profile>
./privacy-toolkit remove email-request -p <profile>

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

## Conventions

- Use `logging` module (not print) — `logger = logging.getLogger(__name__)`
- Scanners extend `BaseScanner` and implement `scan()` returning `list[ScanResult]`
- All database queries use parameterized SQL (never f-strings)
- Broker YAML schema: slug, name, url, category, priority, data_types, opt_out.methods[], verification, reappearance
- Config secrets should use environment variable fallbacks
- Type hints on all new/modified functions
- Tests in `tests/` using pytest, mock external APIs
