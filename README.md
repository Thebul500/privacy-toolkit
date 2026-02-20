# Privacy Toolkit

[![CI](https://github.com/Thebul500/privacy-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Thebul500/privacy-toolkit/actions/workflows/ci.yml)

Automated personal data discovery and removal across 78 data brokers and people-search sites. Scans for your digital footprint, generates legally-compliant CCPA/GDPR deletion requests, and tracks removal progress over time.

## Features

- **Multi-vector discovery** — scan emails, usernames, phone numbers, and addresses across data brokers, breach databases, and social platforms
- **Account discovery** — find accounts linked to your email, phone, or username with interactive removal guidance
- **Breach exposure reports** — aggregate breach data across all your emails with risk assessment (HIGH/MEDIUM/LOW)
- **78 pre-configured data brokers** — Whitepages, Spokeo, BeenVerified, Intelius, and 74 more with documented opt-out methods
- **40 service deletion guides** — step-by-step account deletion instructions for Facebook, Google, LinkedIn, Steam, and more
- **Automated removal requests** — SMTP email with legal templates (CCPA, GDPR, CPRA, VCDPA) and Playwright-based form submissions
- **Removal tracking** — full lifecycle management: pending, submitted, confirmed, reappeared
- **Periodic re-scanning** — cron-based scheduling to detect re-listed data (configurable intervals)
- **Web dashboard** — FastAPI + HTMX interface with account discovery, scan management, and audit log
- **CLI with progress bars** — full-featured Click CLI with Rich progress indicators
- **CSV and HTML export** — export findings and removal status in multiple formats
- **Signal notifications** — scan completion alerts via Signal REST API
- **Environment variable secrets** — `${ENV_VAR}` syntax and auto-fallback for SMTP, HIBP, Signal credentials
- **94 tests** — pytest suite covering db, config, models, scanners, notifications, and reporting

## Scanners

| Scanner | What it finds | Source |
|---------|---------------|--------|
| HaveIBeenPwned | Data breaches and pastes | HIBP API |
| Holehe | Email registrations across services | holehe |
| Sherlock | Username presence on 300+ sites | sherlock-project |
| Maigret | Advanced username OSINT | maigret |
| PhoneInfoga | Phone number intelligence | phoneinfoga binary |
| People Search | Data broker listings | Playwright + headless Chromium |
| SpiderFoot | Full OSINT framework | Docker container |

## Quick Start

### Local Install

```bash
git clone https://github.com/Thebul500/privacy-toolkit.git
cd privacy-toolkit
bash install.sh
```

The installer creates a virtualenv, installs dependencies, downloads PhoneInfoga, installs Playwright Chromium, and creates a `privacy-toolkit` CLI entry point.

### Docker

```bash
docker-compose up -d
# Web UI at http://localhost:8384
```

### Configuration

```bash
cp config/config.yaml.example config/config.yaml
```

Edit `config/config.yaml` with your settings:

- **SMTP** — Gmail app password for sending deletion request emails (or set `SMTP_PASSWORD` env var)
- **HIBP API key** — optional, for breach detection (or set `HIBP_API_KEY` env var)
- **Signal** — optional, for scan completion notifications (or set `SIGNAL_SENDER` env var)
- **Browser** — headless mode, timeouts, rate limiting, screenshot preferences

Secrets support three formats:
```yaml
password: "literal-value"         # Used as-is
password: "${SMTP_PASSWORD}"      # Resolved from env var
password: ""                      # Auto-fallback to SMTP_PASSWORD env var
```

## Usage

### Check Dependencies

```bash
privacy-toolkit doctor
```

Reports status of all 12 dependencies: Python, Playwright, Holehe, Sherlock, Maigret, PhoneInfoga, SpiderFoot, SMTP, HIBP API, Signal, Database, Brokers.

### Create a Profile

```bash
privacy-toolkit profile create myname
# Interactive prompts for name, emails, phones, usernames, addresses
```

### Run Scans

```bash
# Full scan (all scanners) with progress bar
privacy-toolkit scan full -p myname

# Individual scanners
privacy-toolkit scan email user@example.com
privacy-toolkit scan username johndoe
privacy-toolkit scan phone +15551234567
privacy-toolkit scan people "John Doe" --type name
```

### Discover Accounts

```bash
# Find accounts linked to an email (Holehe + HIBP)
privacy-toolkit accounts find-by-email user@example.com

# Find accounts linked to a phone number
privacy-toolkit accounts find-by-phone +15551234567

# Find accounts by username (Sherlock + Maigret, deduplicated)
privacy-toolkit accounts find-by-username johndoe

# Breach exposure report across all profile emails
privacy-toolkit accounts exposure-report -p myname
```

Each command shows results in a Rich table and offers interactive removal guidance with links to deletion guides.

### Submit Removal Requests

```bash
# Preview what would be sent
privacy-toolkit remove email-request -p myname --dry-run

# Send CCPA/GDPR deletion emails to all brokers with findings
privacy-toolkit remove email-request -p myname

# Target a specific broker
privacy-toolkit remove email-request -p myname -b whitepages

# Automated form submission (Playwright)
privacy-toolkit remove form-request -p myname -b spokeo

# Preview form steps without submitting
privacy-toolkit remove form-request -p myname -b spokeo --dry-run

# Show manual removal instructions
privacy-toolkit remove manual -p myname
```

### Track Removals

```bash
privacy-toolkit track status -p myname     # All removal requests
privacy-toolkit track pending -p myname    # Due for recheck
privacy-toolkit track history -p myname    # Scan history
privacy-toolkit track confirm 42           # Mark removal confirmed
privacy-toolkit track reappeared 42        # Mark re-listed
```

### Schedule Re-scans

```bash
privacy-toolkit schedule enable -p myname   # Install cron jobs
privacy-toolkit schedule status             # Show scheduled jobs
privacy-toolkit schedule disable            # Remove cron jobs
```

Default schedule: full re-scan every Sunday at 3 AM, pending recheck daily at 9 AM.

### Reports

```bash
privacy-toolkit report -p myname                        # Terminal table
privacy-toolkit report -p myname -f json -o report.json # JSON
privacy-toolkit report -p myname -f csv -o report.csv   # CSV
privacy-toolkit report -p myname -f html -o report.html # HTML
privacy-toolkit report -p myname -f csv -t removals     # Removal status CSV
```

### Validate Brokers

```bash
privacy-toolkit brokers                    # List all 78
privacy-toolkit brokers -P critical        # Filter by priority
privacy-toolkit brokers validate           # Validate all YAML schemas
```

## Web Dashboard

The web UI runs on port 8080 (or 8384 via Docker) and provides:

- **Dashboard** — stats overview, recent activity, active background tasks
- **Profiles** — create and manage identity profiles
- **Scans** — trigger scans with live status updates
- **Accounts** — discover linked accounts by email/phone/username with risk assessment
- **Removals** — track all requests, mark confirmed/reappeared, submit new batches
- **Brokers** — browse the 78 configured brokers by priority
- **Activity** — audit log of all actions

## Service Deletion Guides

40 YAML guides in `guides/` with step-by-step account deletion instructions:

| Category | Services |
|----------|----------|
| Social | Facebook, Instagram, Twitter/X, LinkedIn, TikTok, Snapchat, Reddit, Pinterest, Tumblr, Discord |
| Email | Gmail, Outlook, Yahoo, WhatsApp |
| Cloud | Dropbox, iCloud |
| Shopping | Amazon, eBay, Etsy, Walmart |
| Streaming | Netflix, Spotify, Hulu, Disney+, Twitch, YouTube |
| Gaming | Steam, Epic Games, PlayStation, Xbox |
| Finance | PayPal, Venmo, Cash App |
| Productivity | Slack, Zoom, Adobe, Canva |
| Developer | GitHub, StackOverflow, npm |

## Email Templates

Three Jinja2 legal templates in `templates/`:

| Template | Purpose |
|----------|---------|
| `ccpa_deletion_request.j2` | Formal deletion request citing CCPA, CPRA, VCDPA, CPA, CTDPA, TDPSA, OCPA, FCRA |
| `gdpr_deletion_request.j2` | EU GDPR Article 17 right to erasure |
| `follow_up_request.j2` | Follow-up for non-responsive brokers |

## Adding Brokers

Create a YAML file in `brokers/`:

```yaml
slug: example-broker
name: Example Broker
url: https://example-broker.com
category: people_search
priority: medium
data_types: [name, phone, email, address]

opt_out:
  methods:
    - type: email
      address: privacy@example-broker.com
      template: ccpa_deletion_request
      subject: "Data Deletion Request"

    - type: form
      url: https://example-broker.com/opt-out
      steps:
        - action: goto
          url: https://example-broker.com/opt-out
        - action: fill
          selector: "input[name=email]"
          field: email
        - action: click
          selector: "button[type=submit]"
        - action: screenshot
          name: example_submission

  verification:
    type: check_listing
    expected_days: 14

  reappearance:
    frequency_days: 90

privacy_policy_url: https://example-broker.com/privacy
```

Validate with `privacy-toolkit brokers validate`.

## Project Structure

```
privacy-toolkit/
├── src/
│   ├── app.py                 # FastAPI web application
│   ├── cli.py                 # Click CLI with Rich progress bars
│   ├── config.py              # YAML config loader + env var support
│   ├── db.py                  # SQLite database layer
│   ├── models.py              # Pydantic data models
│   ├── tasks.py               # Background task manager
│   ├── scheduler.py           # Cron + APScheduler
│   ├── notifications.py       # Signal API integration
│   ├── scanners/              # 8 scanner implementations
│   ├── removers/              # Email, form, and manual removal
│   ├── reporting/             # Terminal, JSON, CSV, HTML export
│   └── web/                   # Jinja2 templates + static assets
├── brokers/                   # 78 broker YAML definitions
├── guides/                    # 40 service deletion guides
├── templates/                 # Legal email templates
├── config/                    # Configuration files
├── tests/                     # 94 pytest tests
├── data/                      # SQLite DB, logs, screenshots
├── bin/                       # PhoneInfoga binary
├── .github/workflows/ci.yml   # GitHub Actions CI
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── install.sh
```

## Requirements

- Python 3.12+
- Chromium (installed automatically by Playwright)
- Docker (optional, for SpiderFoot scanner and containerized deployment)
- SMTP credentials (for sending deletion request emails)

## License

Private repository. All rights reserved.
